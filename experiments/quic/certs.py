"""Ephemeral TLS certificate generator for isolated NetPulse QUIC experiments.

Generates temporary X.509 self-signed certificates and RSA private keys
specifically bound to the Mininet host IP (10.0.0.2) via SubjectAlternativeName.
Does NOT weaken TLS (no CERT_NONE); the client explicitly trusts this temporary certificate.
Certificates are cleaned up immediately following test completion.
"""
from __future__ import annotations

import ipaddress
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


@dataclass
class EphemeralCert:
    cert_path: Path
    key_path: Path
    temp_dir: tempfile.TemporaryDirectory

    def cleanup(self) -> None:
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass


def generate_ephemeral_certificate(
    server_ip: str = "10.0.0.2",
    valid_hours: int = 24,
) -> EphemeralCert:
    """Generate temporary self-signed certificate and RSA key in a secure temporary directory.

    The SAN strictly includes the server IP address to satisfy modern TLS 1.3 verification.
    """
    temp_dir = tempfile.TemporaryDirectory(prefix="netpulse_quic_tls_")
    cert_path = Path(temp_dir.name) / "cert.pem"
    key_path = Path(temp_dir.name) / "key.pem"

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, server_ip),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "NetPulse Ephemeral Test CA"),
    ])

    san_entries: list[x509.GeneralName] = [
        x509.IPAddress(ipaddress.ip_address(server_ip)),
        x509.DNSName("localhost"),
    ]

    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(hours=valid_hours))
        .add_extension(
            x509.BasicConstraints(ca=True, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.SubjectAlternativeName(san_entries),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    cert_bytes = cert.public_bytes(serialization.Encoding.PEM)
    key_bytes = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    cert_path.write_bytes(cert_bytes)
    key_path.write_bytes(key_bytes)
    cert_path.chmod(0o644)
    key_path.chmod(0o600)

    return EphemeralCert(cert_path=cert_path, key_path=key_path, temp_dir=temp_dir)
