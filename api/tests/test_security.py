from flatmanager_api.security import (
    hash_access_code,
    hash_device_token,
    verify_access_code,
    verify_device_token,
)


def test_access_code_hash_is_stable_for_same_input() -> None:
    first = hash_access_code(apartment_id="apartment-01", code="123456")
    second = hash_access_code(apartment_id="apartment-01", code="123456")

    assert first == second


def test_access_code_hash_changes_for_different_apartment() -> None:
    first = hash_access_code(apartment_id="apartment-01", code="123456")
    second = hash_access_code(apartment_id="apartment-02", code="123456")

    assert first != second


def test_verify_access_code_accepts_only_correct_value() -> None:
    expected = hash_access_code(apartment_id="apartment-01", code="123456")

    assert verify_access_code("apartment-01", "123456", expected)
    assert not verify_access_code("apartment-01", "999999", expected)


def test_verify_device_token_accepts_only_correct_value() -> None:
    expected = hash_device_token("super-secret-device-token")

    assert verify_device_token("super-secret-device-token", expected)
    assert not verify_device_token("different-token", expected)
