"""
ASTRA — IdP Step-Up Token model (F-036)
=========================================
File: backend/app/models/step_up_token.py

External-IdP-authenticated users (SAML, OIDC, PIV) have
``hashed_password = "EXTERNAL_IDP_NO_LOCAL_PASSWORD"`` and therefore
fail the password check in ``signature_service.request_signature``.

To let them sign without storing a local password, the workflow
router exposes ``POST /workflows/signatures/idp-step-up`` which (after
fresh IdP re-auth — represented in this MVP by simply being
authenticated as an IdP-sourced user) issues a one-time, short-lived
``StepUpToken``. The signing call accepts the token in place of a
password.

Storage:
  * ``token_hash`` — SHA-256 of the random token. We never persist
    the plaintext.
  * ``issued_at`` / ``expires_at`` — 5 minute default TTL.
  * ``consumed_at`` — set on first use; further attempts are rejected
    so the token is genuinely one-time.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, DateTime, ForeignKey, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class StepUpToken(Base):
    __tablename__ = "step_up_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    token_hash = Column(String(64), nullable=False, unique=True)
    issued_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)

    user = relationship("User")

    __table_args__ = (
        Index("ix_step_up_tokens_user_unconsumed", "user_id", "consumed_at"),
    )
