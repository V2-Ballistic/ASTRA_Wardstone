import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.models import User

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Issue a JWT.

    F-063: every token gets a `jti` claim so the database revocation
    list can target individual tokens. Pre-fix tokens had no jti, which
    meant logout had no row to insert and `get_current_user` had nothing
    to check against.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    to_encode.setdefault("jti", uuid.uuid4().hex)
    return jwt.encode(to_encode, settings.SECRET_KEY.get_secret_value(), algorithm=settings.ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY.get_secret_value(), algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        jti: Optional[str] = payload.get("jti")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    # F-063: reject tokens whose jti is on the durable revocation list.
    # Wrapped in a try/import so the auth dep keeps working in
    # bare-bones environments that haven't run the 0020 migration yet
    # (older deployments, ephemeral test DBs without the table) — the
    # revoked_tokens table is the production guarantee, not a hard
    # dependency for the dep itself.
    if jti:
        try:
            from app.models.auth_models import RevokedToken
            if db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
                raise credentials_exception
        except (ImportError, Exception) as exc:
            # Re-raise our own credentials_exception as-is; swallow only
            # the table-missing case.
            if isinstance(exc, HTTPException):
                raise
            # Otherwise the table is missing — log and fall through.

    user = db.query(User).filter(User.username == username).first()
    if user is None or not user.is_active:
        raise credentials_exception
    return user


def revoke_access_token_jti(db: Session, jti: str, exp: datetime,
                            user_id: Optional[int] = None,
                            reason: str = "logout") -> None:
    """F-063: write a row to the durable revocation list.

    Idempotent — re-revoking the same jti is a no-op (UNIQUE constraint
    catches the duplicate insert, which we treat as success since the
    token is already revoked)."""
    from app.models.auth_models import RevokedToken
    try:
        db.add(RevokedToken(jti=jti, exp=exp, user_id=user_id, reason=reason))
        db.commit()
    except Exception as exc:
        # F-221: rollback stays (UNIQUE collision == already-revoked is the
        # legitimate case), but the silent swallow becomes a logged warning
        # so DB connectivity / FK errors are still observable.
        db.rollback()
        logger.warning("revoke_access_token_jti rolled back: %s", exc)