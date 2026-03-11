"""
ASTRA — Auth Endpoint Tests
============================
File: backend/tests/test_auth.py
"""


class TestRegister:

    def test_register_user(self, client):
        resp = client.post("/api/v1/auth/register", json={
            "username": "newuser",
            "email": "newuser@astra.test",
            "password": "SecurePass1",
            "full_name": "New User",
            "role": "developer",
        })
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["username"] == "newuser", "Returned username must match"
        assert data["email"] == "newuser@astra.test"
        assert data["is_active"] is True
        assert "id" in data, "Response must include id"
        assert "hashed_password" not in data, "Password hash must never be exposed"

    def test_register_duplicate_username(self, client):
        payload = {
            "username": "dupeuser",
            "email": "d1@astra.test",
            "password": "SecurePass1",
            "full_name": "Dupe",
        }
        first = client.post("/api/v1/auth/register", json=payload)
        assert first.status_code == 201

        payload["email"] = "d2@astra.test"
        second = client.post("/api/v1/auth/register", json=payload)
        assert second.status_code == 400, "Duplicate username must be rejected"
        assert "already" in second.json()["detail"].lower()


class TestLogin:

    def test_login_success(self, client):
        client.post("/api/v1/auth/register", json={
            "username": "loginuser",
            "email": "loginuser@astra.test",
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
            "email": "wrongpw@astra.test",
            "password": "SecurePass1",
            "full_name": "Wrong PW",
        })
        resp = client.post("/api/v1/auth/login", data={
            "username": "wrongpw",
            "password": "TOTALLY_WRONG",
        })
        assert resp.status_code == 401, "Wrong password must return 401"


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
