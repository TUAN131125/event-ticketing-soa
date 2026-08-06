from __future__ import annotations

import asyncio
import json
from contextlib import contextmanager
import sqlite3
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.models import OutboxMessage, PaymentStatus, Workflow, WorkflowStatus


def _serialize_workflow(workflow: Workflow) -> dict[str, Any]:
    workflow.updated_at = datetime.now(timezone.utc)
    payload = asdict(workflow)
    payload["status"] = workflow.status.value
    payload["payment_status"] = workflow.payment_status.value
    payload["updated_at"] = workflow.updated_at.isoformat()
    return payload


def _deserialize_workflow(payload: dict[str, Any]) -> Workflow:
    data = dict(payload)
    data["status"] = WorkflowStatus(data["status"])
    data["payment_status"] = PaymentStatus(data["payment_status"])
    if isinstance(data.get("updated_at"), str):
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
    return Workflow(**data)


class SqliteRepository:
    """Durable local repository used in development and tests."""

    def __init__(self, database_url: str) -> None:
        self.path = self._path_from_url(database_url)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._initialize()

    @staticmethod
    def _path_from_url(database_url: str) -> str:
        for prefix in ("sqlite+aiosqlite:///", "sqlite:///"):
            if database_url.startswith(prefix):
                value = database_url.removeprefix(prefix)
                return "/" + value.lstrip("/") if database_url.startswith(prefix + "/") else value
        return "/tmp/esb_workflows.db"

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self):
        """Commit or roll back and always close a short-lived SQLite connection."""
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            # Create base tables first, then run additive compatibility migrations.
            # Older local ESB databases used the same table name without the
            # status column, so CREATE TABLE IF NOT EXISTS alone is insufficient.
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    idempotency_key TEXT UNIQUE NOT NULL,
                    correlation_id TEXT,
                    status TEXT NOT NULL DEFAULT 'STARTED',
                    body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS outbox (
                    message_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    next_attempt_at REAL NOT NULL,
                    body TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ws_tickets (
                    cache_key TEXT PRIMARY KEY,
                    expires_at INTEGER NOT NULL,
                    body TEXT NOT NULL
                );
                """
            )

            workflow_columns = {
                str(row[1])
                for row in connection.execute("PRAGMA table_info(workflows)").fetchall()
            }
            if "correlation_id" not in workflow_columns:
                connection.execute("ALTER TABLE workflows ADD COLUMN correlation_id TEXT")
            if "status" not in workflow_columns:
                connection.execute(
                    "ALTER TABLE workflows ADD COLUMN status TEXT NOT NULL DEFAULT 'STARTED'"
                )

            connection.executescript(
                """
                CREATE INDEX IF NOT EXISTS ix_workflows_correlation
                    ON workflows(correlation_id);
                CREATE INDEX IF NOT EXISTS ix_workflows_status
                    ON workflows(status);
                CREATE INDEX IF NOT EXISTS ix_outbox_due
                    ON outbox(state, next_attempt_at);
                """
            )

    async def initialize(self) -> None:
        return None

    async def dispose(self) -> None:
        return None

    async def find_by_idempotency(self, key: str) -> Workflow | None:
        async with self._lock:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT body FROM workflows WHERE idempotency_key = ?",
                    (key,),
                ).fetchone()
        return _deserialize_workflow(json.loads(row["body"])) if row else None

    async def get(self, workflow_id: str) -> Workflow | None:
        async with self._lock:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT body FROM workflows WHERE workflow_id = ?",
                    (workflow_id,),
                ).fetchone()
        return _deserialize_workflow(json.loads(row["body"])) if row else None

    async def find_by_correlation(self, correlation_id: str) -> Workflow | None:
        async with self._lock:
            with self._connection() as connection:
                row = connection.execute(
                    """
                    SELECT body
                    FROM workflows
                    WHERE correlation_id = ?
                    ORDER BY rowid DESC
                    LIMIT 1
                    """,
                    (correlation_id,),
                ).fetchone()
        return _deserialize_workflow(json.loads(row["body"])) if row else None

    async def save(self, workflow: Workflow) -> None:
        payload = _serialize_workflow(workflow)
        body = json.dumps(payload, separators=(",", ":"))
        correlation_id = workflow.evidence.get("correlationId")
        async with self._lock:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO workflows(
                        workflow_id,
                        idempotency_key,
                        correlation_id,
                        status,
                        body
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(workflow_id) DO UPDATE SET
                        correlation_id = excluded.correlation_id,
                        status = excluded.status,
                        body = excluded.body
                    """,
                    (
                        workflow.workflow_id,
                        workflow.idempotency_key,
                        correlation_id,
                        workflow.status.value,
                        body,
                    ),
                )

    async def list_by_status(self, status: str, limit: int = 100) -> list[Workflow]:
        async with self._lock:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT body
                    FROM workflows
                    WHERE status = ?
                    ORDER BY rowid
                    LIMIT ?
                    """,
                    (status, limit),
                ).fetchall()
        return [_deserialize_workflow(json.loads(row["body"])) for row in rows]

    async def save_with_outbox(
        self,
        workflow: Workflow,
        messages: list[OutboxMessage],
    ) -> None:
        payload = _serialize_workflow(workflow)
        workflow_body = json.dumps(payload, separators=(",", ":"))
        async with self._lock:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO workflows(
                        workflow_id,
                        idempotency_key,
                        correlation_id,
                        status,
                        body
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(workflow_id) DO UPDATE SET
                        correlation_id = excluded.correlation_id,
                        status = excluded.status,
                        body = excluded.body
                    """,
                    (
                        workflow.workflow_id,
                        workflow.idempotency_key,
                        workflow.evidence.get("correlationId"),
                        workflow.status.value,
                        workflow_body,
                    ),
                )
                for message in messages:
                    message_body = json.dumps(asdict(message), separators=(",", ":"))
                    connection.execute(
                        """
                        INSERT INTO outbox(message_id, state, next_attempt_at, body)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(message_id) DO UPDATE SET
                            state = excluded.state,
                            next_attempt_at = excluded.next_attempt_at,
                            body = excluded.body
                        """,
                        (
                            message.message_id,
                            message.state,
                            message.next_attempt_at,
                            message_body,
                        ),
                    )

    async def add(self, message: OutboxMessage) -> None:
        await self.save_message(message)

    async def due(self, limit: int) -> list[OutboxMessage]:
        async with self._lock:
            with self._connection() as connection:
                rows = connection.execute(
                    """
                    SELECT body
                    FROM outbox
                    WHERE state = 'PENDING' AND next_attempt_at <= ?
                    ORDER BY next_attempt_at
                    LIMIT ?
                    """,
                    (time.time(), limit),
                ).fetchall()
        return [OutboxMessage(**json.loads(row["body"])) for row in rows]

    async def save_message(self, message: OutboxMessage) -> None:
        body = json.dumps(asdict(message), separators=(",", ":"))
        async with self._lock:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO outbox(message_id, state, next_attempt_at, body)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(message_id) DO UPDATE SET
                        state = excluded.state,
                        next_attempt_at = excluded.next_attempt_at,
                        body = excluded.body
                    """,
                    (
                        message.message_id,
                        message.state,
                        message.next_attempt_at,
                        body,
                    ),
                )

    async def get_ws_ticket(self, key: str) -> dict[str, Any] | None:
        async with self._lock:
            with self._connection() as connection:
                row = connection.execute(
                    "SELECT expires_at, body FROM ws_tickets WHERE cache_key = ?",
                    (key,),
                ).fetchone()
        if row is None or int(row["expires_at"]) <= int(time.time()):
            return None
        return json.loads(row["body"])

    async def save_ws_ticket(
        self,
        key: str,
        expires_at: int,
        body: dict[str, Any],
    ) -> None:
        async with self._lock:
            with self._connection() as connection:
                connection.execute(
                    """
                    INSERT INTO ws_tickets(cache_key, expires_at, body)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET
                        expires_at = excluded.expires_at,
                        body = excluded.body
                    """,
                    (key, expires_at, json.dumps(body, separators=(",", ":"))),
                )


class PostgresRepository:
    """Multi-replica repository for production PostgreSQL deployments."""

    def __init__(self, database_url: str) -> None:
        try:
            from sqlalchemy.ext.asyncio import create_async_engine
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError("SQLAlchemy is required for PostgreSQL persistence") from exc

        self._engine = create_async_engine(database_url, pool_pre_ping=True)
        self._metadata = self._build_metadata()

    @staticmethod
    def _build_metadata():
        from sqlalchemy import JSON, BigInteger, Column, Float, MetaData, String, Table

        metadata = MetaData()
        Table(
            "esb_workflows_v2",
            metadata,
            Column("workflow_id", String(64), primary_key=True),
            Column("idempotency_key", String(128), unique=True, nullable=False),
            Column("correlation_id", String(128), index=True),
            Column("status", String(40), index=True, nullable=False),
            Column("body", JSON, nullable=False),
        )
        Table(
            "esb_outbox_v2",
            metadata,
            Column("message_id", String(64), primary_key=True),
            Column("state", String(32), index=True, nullable=False),
            Column("next_attempt_at", Float, index=True, nullable=False),
            Column("body", JSON, nullable=False),
        )
        Table(
            "esb_ws_ticket_v2",
            metadata,
            Column("cache_key", String(256), primary_key=True),
            Column("expires_at", BigInteger, index=True, nullable=False),
            Column("body", JSON, nullable=False),
        )
        return metadata

    @property
    def workflows(self):
        return self._metadata.tables["esb_workflows_v2"]

    @property
    def outbox(self):
        return self._metadata.tables["esb_outbox_v2"]

    @property
    def ws_tickets(self):
        return self._metadata.tables["esb_ws_ticket_v2"]

    async def initialize(self) -> None:
        """Fail fast when the migration-managed production schema is missing."""
        from sqlalchemy import text

        required = {
            "esb_workflows_v2",
            "esb_outbox_v2",
            "esb_ws_ticket_v2",
        }
        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    text(
                        """
                        SELECT table_name
                        FROM information_schema.tables
                        WHERE table_schema = current_schema()
                          AND table_name IN (
                            'esb_workflows_v2',
                            'esb_outbox_v2',
                            'esb_ws_ticket_v2'
                          )
                        """
                    )
                )
            ).all()
        present = {str(row[0]) for row in rows}
        missing = sorted(required - present)
        if missing:
            raise RuntimeError(
                "ESB database schema is not migrated; missing tables: "
                + ", ".join(missing)
            )

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def find_by_idempotency(self, key: str) -> Workflow | None:
        from sqlalchemy import select

        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    select(self.workflows.c.body).where(
                        self.workflows.c.idempotency_key == key
                    )
                )
            ).first()
        return _deserialize_workflow(row[0]) if row else None

    async def get(self, workflow_id: str) -> Workflow | None:
        from sqlalchemy import select

        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    select(self.workflows.c.body).where(
                        self.workflows.c.workflow_id == workflow_id
                    )
                )
            ).first()
        return _deserialize_workflow(row[0]) if row else None

    async def find_by_correlation(self, correlation_id: str) -> Workflow | None:
        from sqlalchemy import select

        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    select(self.workflows.c.body)
                    .where(self.workflows.c.correlation_id == correlation_id)
                    .limit(1)
                )
            ).first()
        return _deserialize_workflow(row[0]) if row else None

    async def save(self, workflow: Workflow) -> None:
        from sqlalchemy.dialects.postgresql import insert

        payload = _serialize_workflow(workflow)
        statement = insert(self.workflows).values(
            workflow_id=workflow.workflow_id,
            idempotency_key=workflow.idempotency_key,
            correlation_id=workflow.evidence.get("correlationId"),
            status=workflow.status.value,
            body=payload,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[self.workflows.c.workflow_id],
            set_={
                "correlation_id": statement.excluded.correlation_id,
                "status": statement.excluded.status,
                "body": statement.excluded.body,
            },
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def list_by_status(self, status: str, limit: int = 100) -> list[Workflow]:
        from sqlalchemy import select

        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(self.workflows.c.body)
                    .where(self.workflows.c.status == status)
                    .limit(limit)
                )
            ).all()
        return [_deserialize_workflow(row[0]) for row in rows]

    async def save_with_outbox(
        self,
        workflow: Workflow,
        messages: list[OutboxMessage],
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert

        workflow_payload = _serialize_workflow(workflow)
        workflow_statement = insert(self.workflows).values(
            workflow_id=workflow.workflow_id,
            idempotency_key=workflow.idempotency_key,
            correlation_id=workflow.evidence.get("correlationId"),
            status=workflow.status.value,
            body=workflow_payload,
        )
        workflow_statement = workflow_statement.on_conflict_do_update(
            index_elements=[self.workflows.c.workflow_id],
            set_={
                "correlation_id": workflow_statement.excluded.correlation_id,
                "status": workflow_statement.excluded.status,
                "body": workflow_statement.excluded.body,
            },
        )
        async with self._engine.begin() as connection:
            await connection.execute(workflow_statement)
            for message in messages:
                message_statement = insert(self.outbox).values(
                    message_id=message.message_id,
                    state=message.state,
                    next_attempt_at=message.next_attempt_at,
                    body=asdict(message),
                )
                message_statement = message_statement.on_conflict_do_update(
                    index_elements=[self.outbox.c.message_id],
                    set_={
                        "state": message_statement.excluded.state,
                        "next_attempt_at": message_statement.excluded.next_attempt_at,
                        "body": message_statement.excluded.body,
                    },
                )
                await connection.execute(message_statement)

    async def add(self, message: OutboxMessage) -> None:
        await self.save_message(message)

    async def due(self, limit: int) -> list[OutboxMessage]:
        from sqlalchemy import select

        async with self._engine.connect() as connection:
            rows = (
                await connection.execute(
                    select(self.outbox.c.body)
                    .where(
                        self.outbox.c.state == "PENDING",
                        self.outbox.c.next_attempt_at <= time.time(),
                    )
                    .order_by(self.outbox.c.next_attempt_at)
                    .limit(limit)
                )
            ).all()
        return [OutboxMessage(**row[0]) for row in rows]

    async def save_message(self, message: OutboxMessage) -> None:
        from sqlalchemy.dialects.postgresql import insert

        payload = asdict(message)
        statement = insert(self.outbox).values(
            message_id=message.message_id,
            state=message.state,
            next_attempt_at=message.next_attempt_at,
            body=payload,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[self.outbox.c.message_id],
            set_={
                "state": statement.excluded.state,
                "next_attempt_at": statement.excluded.next_attempt_at,
                "body": statement.excluded.body,
            },
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)

    async def get_ws_ticket(self, key: str) -> dict[str, Any] | None:
        from sqlalchemy import select

        async with self._engine.connect() as connection:
            row = (
                await connection.execute(
                    select(self.ws_tickets.c.expires_at, self.ws_tickets.c.body).where(
                        self.ws_tickets.c.cache_key == key
                    )
                )
            ).first()
        if row is None or int(row[0]) <= int(time.time()):
            return None
        return row[1]

    async def save_ws_ticket(
        self,
        key: str,
        expires_at: int,
        body: dict[str, Any],
    ) -> None:
        from sqlalchemy.dialects.postgresql import insert

        statement = insert(self.ws_tickets).values(
            cache_key=key,
            expires_at=expires_at,
            body=body,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[self.ws_tickets.c.cache_key],
            set_={
                "expires_at": statement.excluded.expires_at,
                "body": statement.excluded.body,
            },
        )
        async with self._engine.begin() as connection:
            await connection.execute(statement)


class InMemoryRepository:
    def __init__(self) -> None:
        self.workflows: dict[str, Workflow] = {}
        self.keys: dict[str, str] = {}
        self.messages: dict[str, OutboxMessage] = {}
        self.ws_tickets: dict[str, tuple[int, dict[str, Any]]] = {}

    async def initialize(self) -> None:
        return None

    async def dispose(self) -> None:
        return None

    async def find_by_idempotency(self, key: str) -> Workflow | None:
        return self.workflows.get(self.keys.get(key, ""))

    async def get(self, workflow_id: str) -> Workflow | None:
        return self.workflows.get(workflow_id)

    async def find_by_correlation(self, correlation_id: str) -> Workflow | None:
        return next(
            (
                workflow
                for workflow in self.workflows.values()
                if workflow.evidence.get("correlationId") == correlation_id
            ),
            None,
        )

    async def save(self, workflow: Workflow) -> None:
        workflow.updated_at = datetime.now(timezone.utc)
        self.workflows[workflow.workflow_id] = workflow
        self.keys[workflow.idempotency_key] = workflow.workflow_id

    async def list_by_status(self, status: str, limit: int = 100) -> list[Workflow]:
        return [
            workflow
            for workflow in self.workflows.values()
            if workflow.status.value == status
        ][:limit]

    async def save_with_outbox(
        self,
        workflow: Workflow,
        messages: list[OutboxMessage],
    ) -> None:
        await self.save(workflow)
        for message in messages:
            self.messages[message.message_id] = message

    async def add(self, message: OutboxMessage) -> None:
        self.messages[message.message_id] = message

    async def due(self, limit: int) -> list[OutboxMessage]:
        return [
            message
            for message in self.messages.values()
            if message.state == "PENDING" and message.next_attempt_at <= time.time()
        ][:limit]

    async def save_message(self, message: OutboxMessage) -> None:
        self.messages[message.message_id] = message

    async def get_ws_ticket(self, key: str) -> dict[str, Any] | None:
        item = self.ws_tickets.get(key)
        if item is None or item[0] <= int(time.time()):
            return None
        return item[1]

    async def save_ws_ticket(
        self,
        key: str,
        expires_at: int,
        body: dict[str, Any],
    ) -> None:
        self.ws_tickets[key] = (expires_at, body)


def repository_from_url(database_url: str):
    if database_url.startswith("postgresql+"):
        return PostgresRepository(database_url)
    return SqliteRepository(database_url)
