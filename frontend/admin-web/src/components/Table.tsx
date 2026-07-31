import type { ReactNode } from 'react';
import { EmptyState } from '@event-ticketing/shared-ui';

export type Column<T> = { key: string; label: string; render: (row: T) => ReactNode };
export function Table<T extends { id?: string; traceId?: string }>({ columns, rows, emptyTitle = 'No records found', emptyDescription = 'When data is available it will appear here.' }: { columns: Column<T>[]; rows: T[]; emptyTitle?: string; emptyDescription?: string }) {
  if (rows.length === 0) return <EmptyState title={emptyTitle} description={emptyDescription} />;
  return <div className="table-wrap"><table className="data-table"><thead><tr>{columns.map((column) => <th scope="col" key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row, index) => <tr key={row.id ?? row.traceId ?? index}>{columns.map((column) => <td key={column.key}>{column.render(row)}</td>)}</tr>)}</tbody></table></div>;
}
