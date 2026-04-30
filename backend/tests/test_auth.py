"""
ASTRA — Auth Endpoint Tests
============================
File: backend/tests/test_auth.py
"""


class TestRegister:

    def test_register_user(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "SecurePass1",
            "full_name": "New User",
            "role": "developer",
        })
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["username"] == "newuser", "Returned username must match"
        assert data["email"] == "newuser@example.com"
        assert data["is_active"] is True
        assert "id" in data, "Response must include id"
        assert "hashed_password" not in data, "Password hash must never be exposed"

    def test_register_ignores_role_field(self, client):
        """
        AUDIT_FINDINGS F-015: any `role` in the request body MUST be
        ignored. Self-registration always produces a developer; elevated
        roles must come from POST /api/v1/admin/users.
        """
        from app.models import UserRole

        resp = client.post("/api/v1/auth/register", json={
            "username": "would_be_admin",
            "email": "would_be_admin@example.com",
            "password": "SecurePass1",
            "full_name": "Sneaky Admin",
            "role": "admin",         # <- attacker-supplied role
            "department": "Eng",
        })
        assert resp.status_code == 201, resp.text
        data = resp.json()
        # Body said "admin", but the server forced developer.
        assert data["role"] == UserRole.DEVELOPER.value, (
            f"Expected role={UserRole.DEVELOPER.value!r}, got {data['role']!r}"
        )

    def test_register_duplicate_username(self, client):
        payload = {
            "username": "dupeuser",
            "email": "d1@example.com",
            "password": "SecurePass1",
            "full_name": "Dupe",
        }
        first = client.post("/api/v1/auth/register", json=payload)
        assert first.status_code == 201

        payload["email"] = "d2@example.com"
        second = client.post("/api/v1/auth/register", json=payload)
        assert second.status_code == 400, "Duplicate username must be rejected"
        assert "already" in second.json()["detail"].lower()


class TestLogin:

    def test_login_success(self, client):
        client.post("/api/v1/auth/register", json={
            "username": "loginuser",
            "email": "loginuser@example.com",
            "password": "SecurePass1",
            "full_name": "Login User",
        })
        resp = client.post("/api/v1/auth/login", data={
            "username": "loginuser",
            "password": "SecurePass1",
        })
        assert resp.status_code == 200, f"Login failed: {resp.text}"
        data = resp.json()
        assert "access_token" in data, "Must return access_token"
        assert data["token_type"] == "bearer"

    def test_login_wrong_password(self, client):
        client.post("/api/v1/auth/register", json={
            "username": "wrongpw",
            "email": "wrongpw@example.com",
            "password": "SecurePass1",
            "full_name": "Wrong PW",
        })
        resp = client.post("/api/v1/auth/login", data={
            "username": "wrongpw",
            "password": "TOTALLY_WRONG",
        })
        assert resp.status_code == 401, "Wrong password must return 401"


class TestLoginLockout:
    """AUDIT_FINDINGS F-016: NIST AC-7 account lockout."""

    def _register(self, client, username="lockoutuser"):
        return client.post("/api/v1/auth/register", json={
            "username": username,
            "email": f"{username}@example.com",
            "password": "SecurePass1",
            "full_name": "Lockout User",
        })

    def test_lockout_after_max_failed_attempts_returns_429(self, client, db_session):
        from app.services import account_lockout

        self._register(client, "lockout1")

        # Burn through MAX_ATTEMPTS - 1 failures → should still 401
        for i in range(account_lockout.MAX_ATTEMPTS - 1):
            r = client.post("/api/v1/auth/login", data={
                "username": "lockout1", "password": "WRONG",
            })
            assert r.status_code == 401, (
                f"Attempt {i+1}: expected 401 (still under threshold), "
                f"got {r.status_code}"
            )

        # The Nth failure crosses the threshold and MUST 429
        r = client.post("/api/v1/auth/login", data={
            "username": "lockout1", "password": "WRONG",
        })
        assert r.status_code == 429, (
            f"Expected 429 on the {account_lockout.MAX_ATTEMPTS}th failure, "
            f"got {r.status_code}: {r.text}"
        )
        assert "Retry-After" in r.headers, "429 must include Retry-After"
        assert int(r.headers["Retry-After"]) > 0

        # Subsequent attempts (including with the *correct* password)
        # also 429 while locked.
        r = client.post("/api/v1/auth/login", data={
            "username": "lockout1", "password": "SecurePass1",
        })
        assert r.status_code == 429, (
            "Locked account must reject even valid credentials with 429"
        )

    def test_clear_lockout_allows_login_again(self, client, db_session):
        """After record_successful_login (or manual clear), login works again."""
        from app.services import account_lockout

        self._register(client, "lockout2")

        # Trip the lockout
        for _ in range(account_lockout.MAX_ATTEMPTS):
            client.post("/api/v1/auth/login", data={
                "username": "lockout2", "password": "WRONG",
            })

        # Manually clear (simulates auto-unlock at locked_until)
        account_lockout.record_successful_login(db_session, "lockout2")

        r = client.post("/api/v1/auth/login", data={
            "username": "lockout2", "password": "SecurePass1",
        })
        assert r.status_code == 200, (
            f"After clear, valid credentials must succeed; got {r.status_code}"
        )


class TestLoginAudit:
    """AUDIT_FINDINGS F-031: failed-login audit emission."""

    def test_failed_login_against_known_user_emits_audit(self, client, db_session):
        """Wrong password against an existing user must write auth.login_failed."""
        from app.models.audit_log import AuditLog

        client.post("/api/v1/auth/register", json={
            "username": "auditfail", "email": "auditfail@example.com",
            "password": "SecurePass1", "full_name": "Audit Fail",
        })

        # Snapshot before
        before = db_session.query(AuditLog).filter(
            AuditLog.event_type == "auth.login_failed",
        ).count()

        r = client.post("/api/v1/auth/login", data={
            "username": "auditfail", "password": "WRONG",
        })
        assert r.status_code == 401

        after = db_session.query(AuditLog).filter(
            AuditLog.event_type == "auth.login_failed",
        ).count()
        assert after == before + 1, (
            f"Failed login must emit exactly one auth.login_failed audit row "
            f"(before={before}, after={after})"
        )

        # Confirm the row is anchored to the right user
        row = db_session.query(AuditLog).filter(
            AuditLog.event_type == "auth.login_failed",
        ).order_by(AuditLog.id.desc()).first()
        assert row is not None
        assert row.action_detail.get("username") == "auditfail"
        assert row.action_detail.get("attempts") == 1
        assert row.action_detail.get("locked") is False

    def test_successful_login_emits_audit(self, client, db_session):
        """Successful login must write auth.login_success (no try/except: pass)."""
        from app.models.audit_log import AuditLog

        client.post("/api/v1/auth/register", json={
            "username": "auditok", "email": "auditok@example.com",
            "password": "SecurePass1", "full_name": "Audit OK",
        })

        before = db_session.query(AuditLog).filter(
            AuditLog.event_type == "auth.login_success",
        ).count()

        r = client.post("/api/v1/auth/login", data={
            "username": "auditok", "password": "SecurePass1",
        })
        assert r.status_code == 200, r.text

        after = db_session.query(AuditLog).filter(
            AuditLog.event_type == "auth.login_success",
        ).count()
        assert after == before + 1


class TestMe:

    def test_me_endpoint(self, client, auth_headers):
        resp = client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "testadmin"
        assert data["role"] == "admin"

    def test_me_no_token(self, client):
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401, "No token → 401"

    def test_me_invalid_token(self, client):
        resp = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer totally.invalid.jwt"},
        )
        assert resp.status_code == 401, "Bad token → 401"
