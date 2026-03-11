# ASTRA — Security Configuration Guide

This document describes ASTRA's security hardening measures, their
configuration, and their mapping to NIST SP 800-53 Rev 5 controls.

---

## 1. Encryption at Rest (SC-28)

### Field-Level Encryption
Sensitive database fields are encrypted using AES-128 via the `cryptography`
library's Fernet implementation.  The encryption key is derived from the
`ENCRYPTION_KEY` env var using PBKDF2 (480,000 iterations, SHA-256).

**Configuration:**
```env
ENCRYPTION_KEY=<openssl rand -hex 32>
```

**Applying to a model field:**
```python
from app.services.encryption import EncryptedString
class SensitiveModel(Base):
    ssn = Column(EncryptedString(length=500))
```

If `ENCRYPTION_KEY` is unset, the system falls back to `SECRET_KEY` with a
stderr warning.  This is acceptable for development but **must** be set
independently in production.

### Database-Level Encryption
PostgreSQL should be configured with `pgcrypto` extension and TDE (Transparent
Data Encryption) if available on the hosting platform.

---

## 2. Encryption in Transit (SC-8)

### TLS Configuration
TLS is terminated at the nginx reverse proxy.

| Setting | Value |
|---------|-------|
| Protocols | TLSv1.2, TLSv1.3 only |
| Ciphers | ECDHE-ECDSA-AES256-GCM-SHA384, ECDHE-RSA-AES256-GCM-SHA384, CHACHA20-POLY1305, AES128-GCM |
| HSTS | max-age=63072000; includeSubDomains; preload |
| OCSP Stapling | Enabled |
| Session Tickets | Disabled |

**Certificate setup:**
```bash
mkdir -p certs/
# Generate DH parameters (do this once, takes a few minutes)
openssl dhparam -out certs/dhparam.pem 2048

# Place your certificate and key:
cp /path/to/your/cert.pem certs/server.crt
cp /path/to/your/key.pem  certs/server.key
chmod 600 certs/server.key
```

### PostgreSQL SSL
In production, the database connection enforces SSL:
```env
DATABASE_URL=postgresql://astra:PASSWORD@db:5432/astra?sslmode=require
```

---

## 3. Security Headers (SC-8, SI-11)

Every HTTP response includes these headers, added by both nginx and
the `SecurityHeadersMiddleware`:

| Header | Value | Purpose |
|--------|-------|---------|
| Strict-Transport-Security | max-age=63072000; includeSubDomains; preload | Force HTTPS |
| X-Content-Type-Options | nosniff | Prevent MIME sniffing |
| X-Frame-Options | DENY | Prevent clickjacking |
| X-XSS-Protection | 1; mode=block | Legacy XSS filter |
| Content-Security-Policy | default-src 'self' | Prevent injection |
| Referrer-Policy | strict-origin-when-cross-origin | Limit referrer leakage |
| Permissions-Policy | camera=(), microphone=(), geolocation=() | Disable unnecessary APIs |
| Cache-Control | no-store (on authenticated responses) | Prevent caching of sensitive data |

In development mode, CSP is relaxed to allow Next.js hot-reload.

---

## 4. Rate Limiting (SC-5)

A token-bucket rate limiter runs as middleware with three tiers:

| Tier | Default Limit | Env Var |
|------|---------------|---------|
| General API | 100 req/min per IP | `RATE_LIMIT_DEFAULT` |
| Auth endpoints | 10 req/min per IP | `RATE_LIMIT_AUTH` |
| Import endpoints | 5 req/min per IP | `RATE_LIMIT_IMPORT` |

When exceeded, the server returns HTTP 429 with a `Retry-After: 60` header.

nginx adds a second rate-limiting layer (50 req/sec API, 5 req/sec auth).

---

## 5. Account Lockout (AC-7)

Failed login attempts are tracked per username in the `account_lockouts` table.

| Setting | Default | Env Var |
|---------|---------|---------|
| Max attempts before lockout | 5 | `MAX_LOGIN_ATTEMPTS` |
| Lockout duration | 30 minutes | `LOCKOUT_DURATION_MINUTES` |

After `MAX_LOGIN_ATTEMPTS` consecutive failures, the account is locked and
returns HTTP 423 (Locked).  The lock auto-expires after the configured
duration.  A successful login resets the counter to zero.

---

## 6. Secret Management (IA-5, SC-12)

### Pydantic SecretStr
All credentials in `config.py` use `SecretStr`, which:
- Never appears in `repr()`, `str()`, or tracebacks
- Is excluded from JSON serialization
- Must be explicitly accessed via `.get_secret_value()`

### Production Startup Guard
When `ENVIRONMENT=production`, the application **refuses to start** if:
- `SECRET_KEY` is a known default value (e.g., `dev-secret-key-change-in-production`)
- `SECRET_KEY` is shorter than 32 characters

### Key Generation
```bash
# Generate a strong SECRET_KEY
openssl rand -hex 32

# Generate a separate ENCRYPTION_KEY
openssl rand -hex 32
```

---

## 7. Production Docker Configuration

Use `docker-compose.prod.yml` for production deployments:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

### Hardening measures:
- **No pgAdmin** exposed (use `psql` or a bastion host for DB admin)
- **No dev router** (ENVIRONMENT=production disables `/api/v1/dev/*`)
- **No Swagger docs** (docs_url and redoc_url are None in production)
- **Read-only filesystems** with explicit tmpfs mounts
- **Non-root users** (`user: 1000:1000`) in backend and frontend
- **Resource limits** (memory + CPU caps per container)
- **Backend not exposed** to host — only nginx port 443 is public
- **PostgreSQL SSL** enforced via command-line args
- **Health checks** on all services

---

## 8. CAC/PIV Certificate Auth (IA-2)

For CAC/PIV smart card authentication, uncomment the client-cert lines in
`nginx/nginx.conf` and provide the DoD CA bundle.  See `docs/PIV_SETUP.md`
for the complete guide.

---

## 9. Audit Trail (AU-2, AU-3, AU-9)

The tamper-evident audit log uses a SHA-256 hash chain.  See the audit
system documentation for details.  The PostgreSQL trigger in
`database/migrations/audit_append_only.sql` physically prevents
UPDATE/DELETE/TRUNCATE on the `audit_log` table.

---

## 10. NIST 800-53 Control Mapping

| Control | Title | Implementation |
|---------|-------|----------------|
| AC-2 | Account Management | RBAC + admin router |
| AC-7 | Unsuccessful Logon Attempts | Account lockout service |
| AU-2 | Audit Events | Audit log with hash chain |
| AU-3 | Content of Audit Records | Structured JSON action_detail |
| AU-9 | Protection of Audit Information | Append-only trigger + hash chain |
| IA-2 | Identification & Authentication | Local + SAML + OIDC + PIV |
| IA-5 | Authenticator Management | bcrypt, SecretStr, key derivation |
| SC-5 | Denial of Service Protection | Rate limiting (middleware + nginx) |
| SC-8 | Transmission Confidentiality | TLS 1.2+, HSTS, strong ciphers |
| SC-12 | Cryptographic Key Management | PBKDF2 key derivation, env-based keys |
| SC-13 | Cryptographic Protection | AES-128 Fernet, SHA-256 audit chain |
| SC-28 | Protection of Information at Rest | Field-level encryption |
| SI-11 | Error Handling | Security headers, no stack traces in production |

---

## 11. Checklist Before Going to Production

- [ ] Set strong `SECRET_KEY` (≥ 32 chars, `openssl rand -hex 32`)
- [ ] Set separate `ENCRYPTION_KEY`
- [ ] Set `ENVIRONMENT=production`
- [ ] Place real TLS certificates in `certs/`
- [ ] Generate `dhparam.pem` (`openssl dhparam -out certs/dhparam.pem 2048`)
- [ ] Set `DATABASE_URL` with `?sslmode=require`
- [ ] Set `ALLOWED_HOSTS` to your actual domain(s)
- [ ] Set `BACKEND_CORS_ORIGINS` to your frontend URL only
- [ ] Configure DoD CA bundle for PIV/CAC if needed
- [ ] Run `audit_append_only.sql` on the database
- [ ] Verify: `docker compose -f docker-compose.prod.yml config`
- [ ] Test: hit the health endpoint and verify HSTS + CSP headers
