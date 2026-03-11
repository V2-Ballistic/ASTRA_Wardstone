"""
ASTRA — Auth Provider Registry
================================
File: backend/app/services/auth_providers/__init__.py

Defines the base interface every auth provider must implement,
and a factory to instantiate the active provider from config.
"""

from abc import ABC, abstractmethod
from typing import Optional
from sqlalchemy.orm import Session
from app.models import User


class AuthProviderBase(ABC):
    """Interface that all auth providers implement."""

    name: str = "base"

    @abstractmethod
    def authenticate(self, db: Session, **kwargs) -> Optional[User]:
        """Validate credentials and return the User, or None."""
        ...

    def find_or_create_user(
        self, db: Session, *, username: str, email: str,
        full_name: str, role: str = "developer", department: str | None = None,
    ) -> User:
        """Upsert a user record from an external IdP assertion."""
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.full_name = full_name
            db.commit()
            db.refresh(user)
            return user

        user = User(
            username=username,
            email=email,
            hashed_password="EXTERNAL_IDP_NO_LOCAL_PASSWORD",
            full_name=full_name,
            role=role,
            department=department,
            is_active=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user


# ── Provider registry ──

_REGISTRY: dict[str, type[AuthProviderBase]] = {}


def register_provider(name: str):
    """Decorator to register a provider class."""
    def _wrap(cls):
        _REGISTRY[name] = cls
        return cls
    return _wrap


def get_provider(name: str) -> AuthProviderBase:
    """Instantiate the provider registered under *name*."""
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown auth provider '{name}'. "
            f"Available: {list(_REGISTRY.keys())}"
        )
    return cls()


# Import concrete providers so they self-register
from app.services.auth_providers import local   # noqa: F401, E402
from app.services.auth_providers import saml    # noqa: F401, E402
from app.services.auth_providers import oidc    # noqa: F401, E402
from app.services.auth_providers import piv     # noqa: F401, E402
