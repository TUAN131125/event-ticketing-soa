from __future__ import annotations

from app.domain.value_objects import RequestContext

PASSWORD = "Correct-Horse-9!Long"


def test_register_login_me_and_csrf_protected_refresh(client):
    registered = client.post(
        "/auth/register", json={"email": "customer@example.com", "password": PASSWORD}
    )
    assert registered.status_code == 201
    login = client.post(
        "/auth/login",
        json={"email": "customer@example.com", "password": PASSWORD},
        headers={"Origin": "http://testserver"},
    )
    assert login.status_code == 200
    token = login.json()["accessToken"]
    csrf = login.json()["csrfToken"]
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["roles"] == ["CUSTOMER"]
    blocked = client.post(
        "/auth/refresh",
        headers={"Origin": "http://testserver", "X-CSRF-Token": "wrong"},
    )
    assert blocked.status_code == 403
    refreshed = client.post(
        "/auth/refresh",
        headers={"Origin": "http://testserver", "X-CSRF-Token": csrf},
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["accessToken"] != token


def test_duplicate_email_and_bad_login_do_not_leak_account_state(client):
    client.post(
        "/auth/register", json={"email": "case@example.com", "password": PASSWORD}
    )
    duplicate = client.post(
        "/auth/register",
        json={"email": "CASE@EXAMPLE.COM", "password": PASSWORD},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"
    unknown = client.post(
        "/auth/login",
        json={"email": "missing@example.com", "password": PASSWORD},
    )
    wrong = client.post(
        "/auth/login",
        json={"email": "case@example.com", "password": "Wrong-Horse-9!Long"},
    )
    assert unknown.status_code == wrong.status_code == 401
    assert (
        unknown.json()["error"]["code"]
        == wrong.json()["error"]["code"]
        == "INVALID_CREDENTIALS"
    )
    assert PASSWORD not in unknown.text
    assert "Authorization" not in unknown.text


def test_customer_cannot_call_admin_endpoint(client):
    registered = client.post(
        "/auth/register", json={"email": "customer2@example.com", "password": PASSWORD}
    )
    user_id = registered.json()["userId"]
    login = client.post(
        "/auth/login",
        json={"email": "customer2@example.com", "password": PASSWORD},
    )
    response = client.post(
        f"/admin/users/{user_id}/roles",
        json={"role": "CHECKIN_STAFF", "action": "ASSIGN"},
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
    )
    assert response.status_code == 403


def test_bootstrapped_admin_can_assign_role(client):
    service = client.app.state.identity_service
    context = RequestContext("admin-test", "3" * 32, "127.0.0.1", "pytest")
    admin = service.bootstrap_admin("admin@example.com", PASSWORD, context)
    target = client.post(
        "/auth/register",
        json={"email": "staff@example.com", "password": PASSWORD},
    ).json()
    login = client.post(
        "/auth/login",
        json={"email": admin.email, "password": PASSWORD},
    )
    response = client.post(
        f"/admin/users/{target['userId']}/roles",
        json={"role": "CHECKIN_STAFF", "action": "ASSIGN"},
        headers={"Authorization": f"Bearer {login.json()['accessToken']}"},
    )
    assert response.status_code == 200
    assert response.json()["changed"] is True
    assert "CHECKIN_STAFF" in response.json()["user"]["roles"]


def test_repeated_bad_logins_temporarily_lock_account(client):
    client.post(
        "/auth/register", json={"email": "locked@example.com", "password": PASSWORD}
    )
    for _ in range(5):
        response = client.post(
            "/auth/login",
            json={"email": "locked@example.com", "password": "Wrong-Horse-9!Long"},
        )
        assert response.status_code == 401
    locked = client.post(
        "/auth/login",
        json={"email": "locked@example.com", "password": PASSWORD},
    )
    assert locked.status_code == 423
    assert locked.json()["error"]["code"] == "ACCOUNT_LOCKED"


def test_jwks_has_cache_header(client):
    response = client.get("/.well-known/jwks.json")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=300"
    assert response.json()["keys"][0]["alg"] == "RS256"
