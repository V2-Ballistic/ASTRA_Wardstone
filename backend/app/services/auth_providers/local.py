"""
ASTRA — Local (bcrypt/JWT) Auth Provider
==========================================
File: backend/app/services/auth_providers/local.py

Wraps the existing password-hash logic in the pluggable interface.
"""

from typing import Optional
from sqlalchemy.orm import Session
from passlib.context import CryptContext

from app.models import User
from app.services.auth_providers import AuthProviderBase, register_provider

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


@register_provider("local")
class LocalAuthProvider(AuthProviderBase):
    """Username + bcrypt password authentication."""

    name = "local"

    def authenticate(self, db: Session, **kwargs) -> Optional[User]:
        username: str = kwargs.get("username", "")
        password: str = kwargs.get("password", "")

        user = db.query(User).filter(User.username == username).first()
        if not user or not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user
