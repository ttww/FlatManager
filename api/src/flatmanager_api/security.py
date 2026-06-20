import hashlib
import hmac

from .settings import settings


def _hmac_digest(value: str, *, namespace: str, algorithm: str) -> str:
    payload = f"{namespace}:{value}".encode()
    key = settings.security_pepper.encode()
    return hmac.new(key, payload, getattr(hashlib, algorithm)).hexdigest()


def hash_access_code(apartment_id: str, code: str) -> str:
    canonical = f"{apartment_id}:{code}"
    return _hmac_digest(
        canonical,
        namespace="access_code",
        algorithm=settings.code_hash_algorithm,
    )


def verify_access_code(apartment_id: str, provided_code: str, expected_hash: str) -> bool:
    computed = hash_access_code(apartment_id=apartment_id, code=provided_code)
    return hmac.compare_digest(computed, expected_hash)


def hash_device_token(token: str) -> str:
    return _hmac_digest(
        token,
        namespace="device_token",
        algorithm=settings.token_hash_algorithm,
    )


def verify_device_token(provided_token: str, expected_hash: str) -> bool:
    computed = hash_device_token(token=provided_token)
    return hmac.compare_digest(computed, expected_hash)
