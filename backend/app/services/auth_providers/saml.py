"""
ASTRA — SAML 2.0 Auth Provider
================================
File: backend/app/services/auth_providers/saml.py

Implements a SAML 2.0 Service Provider using python3-saml (onelogin).
On successful assertion the user is upserted into the local DB and a JWT issued.

Required env vars:
    SAML_IDP_METADATA_URL   — IdP metadata endpoint
    SAML_SP_ENTITY_ID       — our SP entity ID (e.g. https://astra.mil/saml)
    SAML_SP_ACS_URL         — Assertion Consumer Service URL
    SAML_CERT_FILE          — path to SP certificate (PEM)
    SAML_KEY_FILE           — path to SP private key (PEM)
"""

import logging
import os
from typing import Optional
from sqlalchemy.orm import Session

from app.models import User
from app.services.auth_providers import AuthProviderBase, register_provider

logger = logging.getLogger(__name__)


def _get_saml_settings() -> dict:
    """Build the python3-saml settings dict from env vars."""
    idp_metadata_url = os.getenv("SAML_IDP_METADATA_URL", "")
    sp_entity = os.getenv("SAML_SP_ENTITY_ID", "https://astra.local/saml")
    sp_acs = os.getenv("SAML_SP_ACS_URL", "https://astra.local/api/v1/auth/saml/acs")
    cert_file = os.getenv("SAML_CERT_FILE", "")
    key_file = os.getenv("SAML_KEY_FILE", "")

    sp_cert = ""
    sp_key = ""
    # F-082: use a context manager so the file handle is closed even
    # if the read raises. Pre-fix the bare `open(...).read()` leaked
    # the handle on any mid-read exception — and SAML reads the SP
    # cert on every login, so under load that surfaces as
    # "too many open files" in the auth hot path.
    if cert_file and os.path.isfile(cert_file):
        with open(cert_file) as f:
            sp_cert = f.read()
    if key_file and os.path.isfile(key_file):
        with open(key_file) as f:
            sp_key = f.read()

    return {
        "strict": True,
        "debug": os.getenv("ENVIRONMENT", "") == "development",
        "sp": {
            "entityId": sp_entity,
            "assertionConsumerService": {
                "url": sp_acs,
                "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
            },
            "x509cert": sp_cert,
            "privateKey": sp_key,
        },
        "idp": {
            "entityId": "",
            "singleSignOnService": {"url": "", "binding": ""},
            "x509cert": "",
        },
        "security": {
            "authnRequestsSigned": True,
            "wantAssertionsSigned": True,
            "wantNameIdEncrypted": False,
        },
    }


def _prepare_request(http_info: dict) -> dict:
    """Convert ASGI / FastAPI request info into the format python3-saml expects."""
    return {
        "https": "on" if http_info.get("scheme") == "https" else "off",
        "http_host": http_info.get("host", "localhost"),
        "script_name": http_info.get("path", ""),
        "get_data": http_info.get("query", {}),
        "post_data": http_info.get("form", {}),
    }


def get_saml_login_url(http_info: dict) -> str:
    """Return the IdP redirect URL."""
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        raise RuntimeError("python3-saml is not installed (pip install python3-saml)")

    req = _prepare_request(http_info)
    auth = OneLogin_Saml2_Auth(req, _get_saml_settings())
    return auth.login()


def process_saml_response(http_info: dict) -> dict | None:
    """
    Validate the IdP response posted to ACS.
    Returns extracted attributes dict or None on failure.
    """
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        raise RuntimeError("python3-saml is not installed")

    req = _prepare_request(http_info)
    auth = OneLogin_Saml2_Auth(req, _get_saml_settings())
    auth.process_response()

    errors = auth.get_errors()
    if errors:
        return None

    if not auth.is_authenticated():
        return None

    attrs = auth.get_attributes()
    name_id = auth.get_nameid()

    return {
        "email": attrs.get("email", [name_id])[0] if attrs.get("email") else name_id,
        "full_name": attrs.get("displayName", [name_id])[0] if attrs.get("displayName") else name_id,
        "username": attrs.get("uid", [name_id])[0] if attrs.get("uid") else name_id,
        "role": attrs.get("role", ["developer"])[0] if attrs.get("role") else "developer",
    }


def get_sp_metadata() -> str:
    """Return SP metadata XML string."""
    try:
        from onelogin.saml2.auth import OneLogin_Saml2_Auth
    except ImportError:
        raise RuntimeError("python3-saml is not installed")

    auth = OneLogin_Saml2_Auth({
        "https": "on", "http_host": "localhost",
        "script_name": "", "get_data": {}, "post_data": {},
    }, _get_saml_settings())
    metadata = auth.get_settings().get_sp_metadata()
    return metadata.decode() if isinstance(metadata, bytes) else metadata


@register_provider("saml")
class SAMLAuthProvider(AuthProviderBase):
    """SAML 2.0 authentication — callback-driven, not direct."""

    name = "saml"

    def authenticate(self, db: Session, **kwargs) -> Optional[User]:
        """
        Called from the ACS callback with already-validated attributes.
        kwargs: email, full_name, username, role
        """
        email = kwargs.get("email")
        if not email:
            return None
        username = kwargs.get("username", email.split("@")[0])
        # F-220: never honour an IdP-provided role on new-user
        # provisioning. A misconfigured IdP that exposes the `role`
        # attribute as user-controllable (some Azure AD self-service
        # profile setups) would otherwise let an unprivileged user
        # promote themselves to admin. New users always get
        # "developer"; admins must elevate via /admin/users/{id}.
        # Matches the F-015 posture for /auth/register.
        idp_role = kwargs.get("role")
        if idp_role and idp_role != "developer":
            logger.warning(
                "SAML IdP provided role=%r for new user %s; ignoring, "
                "defaulting to developer",
                idp_role, username,
            )
        return self.find_or_create_user(
            db,
            username=username,
            email=email,
            full_name=kwargs.get("full_name", email),
            role="developer",
        )
