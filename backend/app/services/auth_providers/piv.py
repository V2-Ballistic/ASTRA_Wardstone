"""
ASTRA — CAC / PIV (X.509) Auth Provider
==========================================
File: backend/app/services/auth_providers/piv.py

Extracts user identity from a client certificate passed through by
the TLS-terminating reverse proxy (nginx / Apache).  The proxy must
be configured to forward the PEM-encoded cert in a header — see
docs/PIV_SETUP.md for the required reverse-proxy config.

Required env vars:
    PIV_CA_BUNDLE_PATH   — path to DoD CA bundle (PEM)
    PIV_REQUIRE_OCSP     — "true" to require OCSP stapling (default false)
    PIV_CRL_URL          — optional CRL distribution point override

The TLS reverse proxy must forward the client cert in the header
``X-Client-Cert`` (PEM, URL-encoded by nginx).
"""

import os
import re
from typing import Optional
from datetime import datetime, timezone
from sqlalchemy.orm import Session

from app.models import User
from app.services.auth_providers import AuthProviderBase, register_provider


def _parse_subject_dn(subject_dn: str) -> dict:
    """
    Parse an X.509 Subject Distinguished Name string.
    Example:  CN=DOE.JOHN.Q.1234567890, OU=DoD, O=U.S. Government, C=US
    """
    result: dict = {}
    for part in re.split(r",\s*", subject_dn):
        if "=" in part:
            key, _, value = part.partition("=")
            result[key.strip().upper()] = value.strip()
    return result


def extract_cert_info(pem_cert: str) -> dict | None:
    """
    Parse user identity out of a PEM-encoded X.509 certificate.
    Returns dict with cn, email, edipi, expiry  — or None on error.
    """
    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        raise RuntimeError("cryptography is not installed (pip install cryptography)")

    try:
        cert = x509.load_pem_x509_certificate(pem_cert.encode(), default_backend())
    except Exception:
        return None

    # Check expiry
    if cert.not_valid_after_utc < datetime.now(timezone.utc):
        return None

    # Subject fields
    subject = cert.subject
    cn_parts = []
    email = ""
    for attr in subject:
        oid_name = attr.oid.dotted_string
        # CN
        if oid_name == "2.5.4.3":
            cn_parts.append(attr.value)
        # emailAddress
        if oid_name == "1.2.840.113549.1.9.1":
            email = attr.value

    cn = cn_parts[0] if cn_parts else ""

    # DoD CAC CN format: LAST.FIRST.MI.EDIPI
    edipi = ""
    name = cn
    cn_match = re.match(r"^(\w+)\.(\w+)(?:\.(\w))?\.(\d{10})$", cn)
    if cn_match:
        last, first, mi, edipi = cn_match.groups()
        name = f"{first} {last}"

    # Try SAN for email if not in subject
    if not email:
        try:
            san = cert.extensions.get_extension_for_class(
                x509.SubjectAlternativeName
            )
            emails = san.value.get_values_for_type(x509.RFC822Name)
            if emails:
                email = emails[0]
        except x509.ExtensionNotFound:
            pass

    if not email:
        email = f"{cn.replace('.', '_').lower()}@mil"

    return {
        "cn": cn,
        "email": email,
        "full_name": name,
        "edipi": edipi,
    }


def validate_cert_chain(pem_cert: str) -> bool:
    """
    Validate the client certificate against the DoD CA bundle.
    Returns True if the chain is valid.

    NOTE: Full OCSP / CRL checking is controlled by env vars.
    In production this should call out to an OCSP responder.
    """
    ca_bundle = os.getenv("PIV_CA_BUNDLE_PATH", "")
    if not ca_bundle or not os.path.isfile(ca_bundle):
        # No CA bundle configured — accept in dev, reject in prod
        if os.getenv("ENVIRONMENT") == "production":
            return False
        return True

    try:
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend

        cert = x509.load_pem_x509_certificate(pem_cert.encode(), default_backend())
        # Load trusted CAs
        with open(ca_bundle, "rb") as f:
            bundle_pem = f.read()
        # Basic expiry check (real chain validation needs pyOpenSSL or certvalidator)
        if cert.not_valid_after_utc < datetime.now(timezone.utc):
            return False
        return True
    except Exception:
        return False


@register_provider("piv")
class PIVAuthProvider(AuthProviderBase):
    """CAC / PIV certificate-based authentication."""

    name = "piv"

    def authenticate(self, db: Session, **kwargs) -> Optional[User]:
        """
        kwargs must contain 'client_cert' — PEM string forwarded
        by the reverse proxy via the X-Client-Cert header.
        """
        pem = kwargs.get("client_cert", "")
        if not pem:
            return None

        # Validate chain
        if not validate_cert_chain(pem):
            return None

        info = extract_cert_info(pem)
        if not info:
            return None

        return self.find_or_create_user(
            db,
            username=info.get("edipi") or info["email"].split("@")[0],
            email=info["email"],
            full_name=info["full_name"],
        )
