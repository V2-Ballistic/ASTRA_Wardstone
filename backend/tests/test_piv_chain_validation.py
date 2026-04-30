"""
ASTRA — PIV cert chain validation (F-037)
===========================================
File: backend/tests/test_piv_chain_validation.py

Pre-fix `validate_cert_chain` only checked NotAfter — any unexpired cert
passed regardless of issuer. F-037 wires the cert against a configured
CA bundle via cryptography.x509.verification.PolicyBuilder.

Coverage:
  * Cert signed by the configured CA → accepted.
  * Cert signed by a different CA (not in the bundle) → rejected.
  * Bundle file present but contains no valid certs → rejected.
  * No PIV_CA_BUNDLE_PATH set + ENVIRONMENT=production → rejected
    (no silent prod fallback).
  * No PIV_CA_BUNDLE_PATH set + ENVIRONMENT=development → accepted
    (dev round-trip stays unblocked).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.services.auth_providers.piv import validate_cert_chain


# ──────────────────────────────────────
#  Cert factory helpers
# ──────────────────────────────────────


def _make_ca(common_name: str):
    """Return (cert, private_key) for a self-signed root CA. Includes the
    extensions PolicyBuilder requires (BasicConstraints, KeyUsage,
    SubjectKeyIdentifier)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=False, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=True, crl_sign=True,
                encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    return cert, key


def _make_leaf(*, ca_cert, ca_key, common_name: str):
    """Return (cert_pem_str, key) for a leaf client cert signed by the
    given CA. Includes ExtendedKeyUsage CLIENT_AUTH, SAN, SKI, AKI —
    all required for cryptography's PolicyBuilder client verifier."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, common_name),
    ])
    now = datetime.now(timezone.utc)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(hours=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([
                x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH,
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectAlternativeName([
                x509.RFC822Name(f"{common_name.lower().replace('.', '_')}@mil"),
            ]),
            critical=False,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(
                ca_key.public_key()
            ),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )
    pem = leaf.public_bytes(serialization.Encoding.PEM).decode()
    return pem, key


def _write_bundle(tmp_path: Path, *ca_certs) -> Path:
    """Write one or more CA certs to a PEM bundle file."""
    bundle = tmp_path / "ca-bundle.pem"
    with bundle.open("wb") as f:
        for ca in ca_certs:
            f.write(ca.public_bytes(serialization.Encoding.PEM))
    return bundle


# ──────────────────────────────────────
#  Tests
# ──────────────────────────────────────


class TestChainValidation:
    def test_leaf_signed_by_bundled_ca_is_accepted(self, monkeypatch, tmp_path):
        ca_cert, ca_key = _make_ca("ASTRA Test Root CA")
        leaf_pem, _ = _make_leaf(ca_cert=ca_cert, ca_key=ca_key, common_name="DOE.JOHN.A.0000000001")
        bundle = _write_bundle(tmp_path, ca_cert)

        monkeypatch.setenv("PIV_CA_BUNDLE_PATH", str(bundle))
        monkeypatch.setenv("ENVIRONMENT", "production")

        assert validate_cert_chain(leaf_pem) is True

    def test_leaf_signed_by_stranger_ca_is_rejected(self, monkeypatch, tmp_path):
        trusted_ca, _ = _make_ca("Trusted CA")
        stranger_ca, stranger_key = _make_ca("Stranger CA")
        leaf_pem, _ = _make_leaf(
            ca_cert=stranger_ca, ca_key=stranger_key,
            common_name="MALLORY.E.A.9999999999",
        )
        bundle = _write_bundle(tmp_path, trusted_ca)

        monkeypatch.setenv("PIV_CA_BUNDLE_PATH", str(bundle))
        monkeypatch.setenv("ENVIRONMENT", "production")

        assert validate_cert_chain(leaf_pem) is False

    def test_empty_bundle_file_is_rejected(self, monkeypatch, tmp_path):
        ca_cert, ca_key = _make_ca("Some CA")
        leaf_pem, _ = _make_leaf(ca_cert=ca_cert, ca_key=ca_key, common_name="X.Y.A.1234567890")

        empty = tmp_path / "empty.pem"
        empty.write_text("")

        monkeypatch.setenv("PIV_CA_BUNDLE_PATH", str(empty))
        monkeypatch.setenv("ENVIRONMENT", "production")

        assert validate_cert_chain(leaf_pem) is False

    def test_no_bundle_in_production_is_rejected(self, monkeypatch, tmp_path):
        ca_cert, ca_key = _make_ca("Some CA")
        leaf_pem, _ = _make_leaf(ca_cert=ca_cert, ca_key=ca_key, common_name="X.Y.A.1234567890")

        monkeypatch.delenv("PIV_CA_BUNDLE_PATH", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "production")

        assert validate_cert_chain(leaf_pem) is False

    def test_no_bundle_in_dev_still_accepted(self, monkeypatch):
        ca_cert, ca_key = _make_ca("Some CA")
        leaf_pem, _ = _make_leaf(ca_cert=ca_cert, ca_key=ca_key, common_name="X.Y.A.1234567890")

        monkeypatch.delenv("PIV_CA_BUNDLE_PATH", raising=False)
        monkeypatch.setenv("ENVIRONMENT", "development")

        assert validate_cert_chain(leaf_pem) is True
