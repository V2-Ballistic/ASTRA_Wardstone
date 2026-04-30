"""
ASTRA — Application Configuration (Security-Hardened)
======================================================
File: backend/app/config.py

Uses Pydantic SecretStr for credentials so they never appear in
tracebacks, logs, or repr() output.

Adds: ENCRYPTION_KEY, SSL paths, ALLOWED_HOSTS, lockout params,
session timeout, rate limits, and a production startup guard that
refuses to run with the default dev SECRET_KEY *or* with an unset /
known-weak ENCRYPTION_KEY.

NIST 800-53: IA-5 (Authenticator Management), SC-12 (Crypto Key Mgmt),
SC-28 (Protection of Information at Rest)
"""

import sys
from typing import List
from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings


# Known-weak dev secrets that must never reach production
_WEAK_SECRETS = {
    "dev-secret-key-change-in-production",
    "replace-with-64-char-random-string-openssl-rand-hex-32",
    "changeme",
    "secret",
    "",
}

# Known-weak encryption-key fallbacks that must never reach production
_WEAK_ENCRYPTION_KEYS = {
    "",
    "dev-fallback-encryption-key",
    "test-secret-key-not-for-production",
    "<openssl rand -hex 32>",  # the .env placeholder shipped before remediation
}


class Settings(BaseSettings):
    # ── Database ──
    DATABASE_URL: SecretStr = SecretStr("postgresql://astra:astra@db:5432/astra")

    # ── Auth / JWT ──
    SECRET_KEY: SecretStr = SecretStr("dev-secret-key-change-in-production")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    SESSION_TIMEOUT_MINUTES: int = 60

    # ── Encryption at rest (SC-28) ──
    ENCRYPTION_KEY: SecretStr = SecretStr("")

    # ── TLS ──
    SSL_CERT_FILE: str = ""
    SSL_KEY_FILE: str = ""

    # ── CORS / Hosts ──
    BACKEND_CORS_ORIGINS: str = "http://localhost:3000"
    ALLOWED_HOSTS: str = "*"

    # ── Account lockout (AC-7) ──
    MAX_LOGIN_ATTEMPTS: int = 5
    LOCKOUT_DURATION_MINUTES: int = 30

    # ── Rate limiting (SC-5) ──
    RATE_LIMIT_DEFAULT: int = 100
    RATE_LIMIT_AUTH: int = 10
    RATE_LIMIT_IMPORT: int = 5

    # ── App ──
    ENVIRONMENT: str = "development"
    APP_NAME: str = "ASTRA"
    APP_VERSION: str = "1.0.0"

    # ── Derived helpers ──

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.BACKEND_CORS_ORIGINS.split(",")]

    @property
    def allowed_hosts_list(self) -> List[str]:
        return [h.strip() for h in self.ALLOWED_HOSTS.split(",")]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    # ── Validation ──

    @field_validator("SECRET_KEY")
    @classmethod
    def _warn_weak_secret(cls, v: SecretStr) -> SecretStr:
        """Log a loud warning if the secret looks like a dev default."""
        raw = v.get_secret_value() if isinstance(v, SecretStr) else str(v)
        if raw in _WEAK_SECRETS:
            print(
                "\n"
                "╔══════════════════════════════════════════════════════╗\n"
                "║  WARNING: SECRET_KEY is set to a known weak value!  ║\n"
                "║  Generate a real key: openssl rand -hex 32          ║\n"
                "╚══════════════════════════════════════════════════════╝\n",
                file=sys.stderr,
            )
        return v

    def enforce_production_guards(self) -> None:
        """
        Call at startup.  Refuses to start the application in production
        mode if critical secrets are still set to their dev defaults.

        Checks:
          - SECRET_KEY is not empty / known-weak / too short
          - ENCRYPTION_KEY is not empty / known-weak (covers F-003 + F-067)
          - ALLOWED_HOSTS is not the wildcard "*" (covers F-066)
        """
        if not self.is_production:
            return

        # ── SECRET_KEY ──
        secret = self.SECRET_KEY.get_secret_value()
        if secret in _WEAK_SECRETS:
            print(
                "\n"
                "FATAL: Cannot start in production with a default SECRET_KEY.\n"
                "Set a strong random key: export SECRET_KEY=$(openssl rand -hex 32)\n",
                file=sys.stderr,
            )
            sys.exit(1)

        if len(secret) < 32:
            print(
                "\n"
                "FATAL: SECRET_KEY is too short for production (need ≥ 32 chars).\n",
                file=sys.stderr,
            )
            sys.exit(1)

        # ── ENCRYPTION_KEY ──
        enc = self.ENCRYPTION_KEY.get_secret_value()
        if enc in _WEAK_ENCRYPTION_KEYS:
            print(
                "\n"
                "FATAL: ENCRYPTION_KEY is unset or set to a known-weak placeholder.\n"
                "Field-level encryption (PII, MFA secrets, integration tokens)\n"
                "would silently use a publicly-known key. Generate a real key:\n"
                "    export ENCRYPTION_KEY=$(openssl rand -hex 32)\n",
                file=sys.stderr,
            )
            sys.exit(1)

        if len(enc) < 32:
            print(
                "\n"
                "FATAL: ENCRYPTION_KEY is too short for production (need ≥ 32 chars).\n",
                file=sys.stderr,
            )
            sys.exit(1)

        # ── ALLOWED_HOSTS (F-066) ──
        # Wildcard ALLOWED_HOSTS in production lets a Host-header
        # attacker poison password-reset emails / cache keys / etc.
        # TrustedHostMiddleware (registered in main.py) requires a
        # concrete host list to be useful.
        hosts = [h for h in self.allowed_hosts_list if h]
        if "*" in hosts or not hosts:
            print(
                "\n"
                "FATAL: ALLOWED_HOSTS cannot be \"*\" or empty in production.\n"
                "Set a concrete host list, e.g. ALLOWED_HOSTS=astra.example.com,api.astra.example.com\n",
                file=sys.stderr,
            )
            sys.exit(1)

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
