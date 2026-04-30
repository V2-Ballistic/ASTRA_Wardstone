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


def _load_ca_bundle(ca_bundle_path: str):
    """
    Parse a PEM CA bundle into a list of x509.Certificate objects.
    Returns None on read or parse failure.
    """
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    try:
        with open(ca_bundle_path, "rb") as f:
            data = f.read()
    except OSError:
        return None

    # Split PEM file into individual certificate blocks; load each.
    cas: list = []
    blocks = re.findall(
        rb"-----BEGIN CERTIFICATE-----[\s\S]+?-----END CERTIFICATE-----",
        data,
    )
    for block in blocks:
        try:
            cas.append(x509.load_pem_x509_certificate(block, default_backend()))
        except Exception:
            continue
    return cas or None


def validate_cert_chain(pem_cert: str) -> bool:
    """
    F-037: Validate the client certificate against the configured CA bundle
    using ``cryptography.x509.verification.PolicyBuilder`` (cryptography
    >= 42). The validator walks the chain, verifies signatures, checks
    NotBefore / NotAfter, and enforces the basic Web PKI server-auth
    profile (which is also adequate for client-cert chains for our
    purposes — the PIV CN structure is checked separately in
    ``extract_cert_info``).

    Behavior:
      * No CA bundle configured (PIV_CA_BUNDLE_PATH unset / missing
        file) — refuse in production (ENVIRONMENT=production), accept
        in dev. Dev acceptance is bounded by ``ENVIRONMENT`` because
        F-037's intent is "no silent prod fallback to expiry-only."
      * CA bundle empty / unparseable — always refuse.
      * Chain validation fails (signature mismatch, untrusted root,
        expired) — refuse.
      * Chain validation succeeds — accept.

    OCSP / CRL is NOT covered here; F-037's scope is chain validation.
    OCSP is tracked separately under PIV_REQUIRE_OCSP for a follow-up.
    """
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend

    is_prod = os.getenv("ENVIRONMENT") == "production"

    ca_bundle_path = os.getenv("PIV_CA_BUNDLE_PATH", "")
    if not ca_bundle_path or not os.path.isfile(ca_bundle_path):
        # In production we refuse — no CA bundle means no chain validation.
        # In dev we accept so local round-trips work without a real PKI.
        return not is_prod

    cas = _load_ca_bundle(ca_bundle_path)
    if not cas:
        # File exists but no valid certs in it — always refuse.
        return False

    try:
        cert = x509.load_pem_x509_certificate(pem_cert.encode(), default_backend())
    except Exception:
        return False

    # Use the PolicyBuilder verifier when available (cryptography >= 42).
    try:
        from cryptography.x509.verification import PolicyBuilder, Store

        store = Store(cas)
        # ClientVerifier is the right shape for client-cert authentication
        # (CAC / PIV); falls back to ServerVerifier on older releases.
        builder = PolicyBuilder().store(store)
        verifier = (
            builder.build_client_verifier()
            if hasattr(builder, "build_client_verifier")
            else builder.build_server_verifier(x509.DNSName("localhost"))
        )
        # Returns chain on success, raises VerificationError on failure.
        verifier.verify(cert, [])
        return True
    except ImportError:
        # Cryptography < 42 — refuse in production rather than silently
        # falling back to expiry-only.
        if is_prod:
            return False
        # Dev fallback: expiry check only.
        return cert.not_valid_after_utc >= datetime.now(timezone.utc)
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
