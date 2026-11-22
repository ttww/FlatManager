from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from secrets import compare_digest
from urllib.parse import unquote_to_bytes

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.x509.oid import ExtendedKeyUsageOID
from fastapi import HTTPException, Request

from .settings import settings

OPENAI_CLIENT_DNS_NAME = "mtls.prod.connectors.openai.com"


@lru_cache(maxsize=1)
def load_intermediate(path: str) -> x509.Certificate:
    return x509.load_pem_x509_certificate(Path(path).read_bytes())


def require_openai_mtls(request: Request) -> None:
    path = settings.chatgpt_guest_mtls_intermediate
    if not path:
        return

    # The proxy proves possession during TLS and must overwrite both headers.
    expected_token = settings.chatgpt_guest_mtls_proxy_token.get_secret_value().encode()
    proxy_token = request.headers.get("x-flatmanager-mtls-proxy-token", "").encode()
    if not expected_token or not compare_digest(expected_token, proxy_token):
        raise HTTPException(status_code=403, detail="OpenAI client certificate required")

    encoded_certificate = request.headers.get("x-flatmanager-mtls-client-cert", "")
    if not encoded_certificate or len(encoded_certificate) > 16_384:
        raise HTTPException(status_code=403, detail="OpenAI client certificate required")

    try:
        leaf = x509.load_pem_x509_certificate(unquote_to_bytes(encoded_certificate))
        leaf.verify_directly_issued_by(load_intermediate(path))
        names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        usage = leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        now = datetime.now(UTC)
        if (
            not leaf.not_valid_before_utc <= now <= leaf.not_valid_after_utc
            or OPENAI_CLIENT_DNS_NAME not in names.get_values_for_type(x509.DNSName)
            or ExtendedKeyUsageOID.CLIENT_AUTH not in usage
        ):
            raise ValueError("Unexpected client certificate identity or purpose")
    except (
        OSError,
        ValueError,
        TypeError,
        InvalidSignature,
        UnsupportedAlgorithm,
        x509.ExtensionNotFound,
        x509.DuplicateExtension,
    ):
        raise HTTPException(status_code=403, detail="Invalid OpenAI client certificate") from None
