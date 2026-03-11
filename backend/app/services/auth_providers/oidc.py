"""
ASTRA — OIDC Auth Provider
============================
File: backend/app/services/auth_providers/oidc.py

OpenID Connect integration using authlib with PKCE support.

Required env vars:
    OIDC_ISSUER_URL      — e.g. https://login.microsoftonline.com/{tenant}/v2.0
    OIDC_CLIENT_ID       — client ID from IdP registration
    OIDC_CLIENT_SECRET   — client secret (empty string for public clients)
    OIDC_REDIRECT_URI    — e.g. https://astra.mil/api/v1/auth/oidc/callback
"""

import os
from typing import Optional
from sqlalchemy.orm import Session

from app.models import User
from app.services.auth_providers import AuthProviderBase, register_provider


def _get_oidc_config() -> dict:
    return {
        "issuer": os.getenv("OIDC_ISSUER_URL", ""),
        "client_id": os.getenv("OIDC_CLIENT_ID", ""),
        "client_secret": os.getenv("OIDC_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv("OIDC_REDIRECT_URI", ""),
    }


def create_oidc_client():
    """Create an authlib OAuth client configured for the OIDC issuer."""
    try:
        from authlib.integrations.starlette_client import OAuth
    except ImportError:
        raise RuntimeError("authlib is not installed (pip install authlib)")

    cfg = _get_oidc_config()
    oauth = OAuth()
    oauth.register(
        name="oidc",
        client_id=cfg["client_id"],
        client_secret=cfg["client_secret"] or None,
        server_metadata_url=f"{cfg['issuer']}/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile",
            "code_challenge_method": "S256",  # PKCE
        },
    )
    return oauth


async def get_oidc_login_redirect(request):
    """Return a Starlette redirect response that sends the user to the IdP."""
    cfg = _get_oidc_config()
    oauth = create_oidc_client()
    return await oauth.oidc.authorize_redirect(request, cfg["redirect_uri"])


async def handle_oidc_callback(request) -> dict | None:
    """
    Exchange the authorization code for tokens and return user info.
    Returns dict with email / name / sub, or None on failure.
    """
    oauth = create_oidc_client()
    try:
        token = await oauth.oidc.authorize_access_token(request)
    except Exception:
        return None

    userinfo = token.get("userinfo")
    if not userinfo:
        return None

    return {
        "email": userinfo.get("email", ""),
        "full_name": userinfo.get("name", userinfo.get("preferred_username", "")),
        "username": userinfo.get("preferred_username", userinfo.get("sub", "")),
        "sub": userinfo.get("sub", ""),
    }


@register_provider("oidc")
class OIDCAuthProvider(AuthProviderBase):
    """OIDC authentication — callback-driven."""

    name = "oidc"

    def authenticate(self, db: Session, **kwargs) -> Optional[User]:
        """
        Called after the callback has validated the token.
        kwargs contain the userinfo fields.
        """
        email = kwargs.get("email")
        if not email:
            return None
        return self.find_or_create_user(
            db,
            username=kwargs.get("username", email.split("@")[0]),
            email=email,
            full_name=kwargs.get("full_name", email),
        )
