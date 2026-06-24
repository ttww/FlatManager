from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from flatmanager_api.db import get_engine, init_db, reset_engine_cache
from flatmanager_api.main import app
from flatmanager_api.models import AccessCode, AccessLog, Device, DoorCommand
from flatmanager_api.security import hash_access_code, hash_device_token
from flatmanager_api.settings import settings


def _iso_now(offset_seconds: int = 0) -> datetime:
    return datetime.now(UTC) + timedelta(seconds=offset_seconds)


def _seed_access_code(
    session: Session,
    *,
    apartment_id: str,
    code: str,
) -> AccessCode:
    access_code = AccessCode(
        apartment_id=apartment_id,
        code_hash=hash_access_code(apartment_id, code),
        valid_from=_iso_now(-3600),
        valid_until=_iso_now(3600),
        max_uses=10,
        used_count=0,
        active=True,
    )
    session.add(access_code)
    session.commit()
    session.refresh(access_code)
    return access_code


def _seed_device(session: Session, *, apartment_id: str, token: str) -> Device:
    device = Device(
        apartment_id=apartment_id,
        device_name="Front Door",
        device_token_hash=hash_device_token(token),
    )
    session.add(device)
    session.commit()
    session.refresh(device)
    return device


def _prepare_test_db(tmp_path: Path) -> None:
    settings.database_url = f"sqlite:///{tmp_path / 'test.db'}"
    reset_engine_cache()
    init_db()


def test_guest_open_success_creates_pending_command_and_logs(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)

    with Session(get_engine()) as session:
        _seed_access_code(session, apartment_id="apartment-01", code="123456")
        _seed_device(session, apartment_id="apartment-01", token="device-token-1")

    client = TestClient(app)
    response = client.post(
        "/api/guest/open",
        json={"apartment_id": "apartment-01", "code": "123456"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    with Session(get_engine()) as session:
        command = session.exec(select(DoorCommand)).first()
        assert command is not None
        assert command.status == "pending"

        logs = session.exec(select(AccessLog)).all()
        assert any(row.result == "success" for row in logs)


def test_guest_open_denied_invalid_code_is_neutral(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)

    with Session(get_engine()) as session:
        _seed_access_code(session, apartment_id="apartment-01", code="123456")
        _seed_device(session, apartment_id="apartment-01", token="device-token-1")

    client = TestClient(app)
    response = client.post(
        "/api/guest/open",
        json={"apartment_id": "apartment-01", "code": "999999"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "denied",
        "message": "Code invalid or not valid.",
    }


def test_device_wait_command_requires_bearer_auth(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    response = client.get("/api/device/wait-command")

    assert response.status_code == 401


def test_device_wait_command_delivers_pending_command(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    settings.long_poll_timeout_seconds = 1
    settings.long_poll_poll_interval_ms = 10

    with Session(get_engine()) as session:
        _seed_access_code(session, apartment_id="apartment-01", code="123456")
        device = _seed_device(session, apartment_id="apartment-01", token="device-token-1")
        session.add(
            DoorCommand(
                device_id=device.id,
                apartment_id="apartment-01",
                command="open",
                duration_ms=1500,
                status="pending",
                expires_at=_iso_now(60),
                source="guest",
            )
        )
        session.commit()

    client = TestClient(app)
    response = client.get(
        "/api/device/wait-command",
        headers={"Authorization": "Bearer device-token-1"},
    )

    assert response.status_code == 200
    assert response.json()["command"] == "open"


def test_command_result_updates_status(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)

    with Session(get_engine()) as session:
        _seed_access_code(session, apartment_id="apartment-01", code="123456")
        device = _seed_device(session, apartment_id="apartment-01", token="device-token-1")
        command = DoorCommand(
            device_id=device.id,
            apartment_id="apartment-01",
            command="open",
            duration_ms=1500,
            status="delivered",
            expires_at=_iso_now(60),
            source="guest",
        )
        session.add(command)
        session.commit()
        session.refresh(command)

    client = TestClient(app)
    response = client.post(
        "/api/device/command-result",
        headers={"Authorization": "Bearer device-token-1"},
        json={"command_id": command.id, "status": "done", "message": "ok"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"

    with Session(get_engine()) as session:
        updated = session.get(DoorCommand, command.id)
        assert updated is not None
        assert updated.status == "done"


def test_rate_limit_denies_after_threshold(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    settings.rate_limit_ip_max_attempts = 1
    settings.rate_limit_apartment_max_attempts = 100

    with Session(get_engine()) as session:
        _seed_access_code(session, apartment_id="apartment-01", code="123456")
        _seed_device(session, apartment_id="apartment-01", token="device-token-1")

    client = TestClient(app)

    first = client.post(
        "/api/guest/open",
        json={"apartment_id": "apartment-01", "code": "999999"},
    )
    second = client.post(
        "/api/guest/open",
        json={"apartment_id": "apartment-01", "code": "999999"},
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "denied"

    with Session(get_engine()) as session:
        rows = session.exec(select(AccessLog).where(AccessLog.result == "rate_limited")).all()
        assert len(rows) >= 1


def test_admin_endpoints_require_token(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    response = client.get("/api/admin/devices/status")

    assert response.status_code == 401


def test_admin_can_read_device_status(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)

    with Session(get_engine()) as session:
        _seed_device(session, apartment_id="apartment-01", token="device-token-1")

    client = TestClient(app)
    response = client.get(
        "/api/admin/devices/status",
        headers={"X-Admin-Token": settings.admin_token},
    )

    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1


def test_admin_can_create_and_list_device(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    create_response = client.post(
        "/api/admin/devices",
        headers={"X-Admin-Token": settings.admin_token},
        json={"apartment_id": "apartment-02", "device_name": "Lobby Door"},
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    assert payload["apartment_id"] == "apartment-02"
    assert payload["device_name"] == "Lobby Door"
    assert isinstance(payload["raw_token"], str)
    assert len(payload["raw_token"]) > 20

    list_response = client.get(
        "/api/admin/devices",
        headers={"X-Admin-Token": settings.admin_token},
    )

    assert list_response.status_code == 200
    devices = list_response.json()
    assert len(devices) == 1
    assert devices[0]["apartment_id"] == "apartment-02"


def test_admin_can_rotate_token_and_old_token_stops_working(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    settings.long_poll_timeout_seconds = 0
    settings.long_poll_poll_interval_ms = 10

    client = TestClient(app)
    create_response = client.post(
        "/api/admin/devices",
        headers={"X-Admin-Token": settings.admin_token},
        json={"apartment_id": "apartment-03", "device_name": "Back Door"},
    )
    assert create_response.status_code == 200
    created = create_response.json()
    device_id = created["id"]
    old_token = created["raw_token"]

    rotate_response = client.post(
        f"/api/admin/devices/{device_id}/rotate-token",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert rotate_response.status_code == 200
    new_token = rotate_response.json()["raw_token"]
    assert new_token != old_token

    old_auth = client.get(
        "/api/device/wait-command",
        headers={"Authorization": f"Bearer {old_token}"},
    )
    assert old_auth.status_code == 401

    new_auth = client.get(
        "/api/device/wait-command",
        headers={"Authorization": f"Bearer {new_token}"},
    )
    assert new_auth.status_code == 200
    assert new_auth.json()["command"] == "none"


def test_admin_can_delete_device(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    create_response = client.post(
        "/api/admin/devices",
        headers={"X-Admin-Token": settings.admin_token},
        json={"apartment_id": "apartment-04", "device_name": "Garage"},
    )
    device_id = create_response.json()["id"]

    delete_response = client.delete(
        f"/api/admin/devices/{device_id}",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert delete_response.status_code == 204

    list_response = client.get(
        "/api/admin/devices",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_admin_can_update_device_fields(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    create_response = client.post(
        "/api/admin/devices",
        headers={"X-Admin-Token": settings.admin_token},
        json={"apartment_id": "apartment-04", "device_name": "Garage"},
    )
    assert create_response.status_code == 200
    device_id = create_response.json()["id"]

    update_response = client.patch(
        f"/api/admin/devices/{device_id}",
        headers={"X-Admin-Token": settings.admin_token},
        json={"apartment_id": "apartment-08", "device_name": "Main Gate"},
    )

    assert update_response.status_code == 200
    payload = update_response.json()
    assert payload["apartment_id"] == "apartment-08"
    assert payload["device_name"] == "Main Gate"
    assert payload["apartment_timezone"] == "UTC"


def test_admin_can_manage_apartment_timezone(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    get_response = client.get(
        "/api/admin/apartments/apartment-05",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert get_response.status_code == 200
    assert get_response.json() == {"apartment_id": "apartment-05", "timezone": "UTC"}

    update_response = client.put(
        "/api/admin/apartments/apartment-05/timezone",
        headers={"X-Admin-Token": settings.admin_token},
        json={"timezone": "Europe/Berlin"},
    )
    assert update_response.status_code == 200
    assert update_response.json() == {"apartment_id": "apartment-05", "timezone": "Europe/Berlin"}

    list_response = client.get(
        "/api/admin/apartments?apartment_id=apartment-05",
        headers={"X-Admin-Token": settings.admin_token},
    )
    assert list_response.status_code == 200
    assert list_response.json() == [{"apartment_id": "apartment-05", "timezone": "Europe/Berlin"}]


def test_admin_rejects_invalid_apartment_timezone(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    response = client.put(
        "/api/admin/apartments/apartment-06/timezone",
        headers={"X-Admin-Token": settings.admin_token},
        json={"timezone": "Not/A-Real-Timezone"},
    )

    assert response.status_code == 400


def test_admin_create_access_code_converts_naive_input_timezone_to_utc(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    client.put(
        "/api/admin/apartments/apartment-07/timezone",
        headers={"X-Admin-Token": settings.admin_token},
        json={"timezone": "Europe/Berlin"},
    )

    response = client.post(
        "/api/admin/access-codes",
        headers={"X-Admin-Token": settings.admin_token},
        json={
            "apartment_id": "apartment-07",
            "code": "123456",
            "valid_from": "2026-01-15T10:00:00",
            "valid_until": "2026-01-15T12:00:00",
            "input_timezone": "Europe/Berlin",
            "max_uses": 20,
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["apartment_timezone"] == "Europe/Berlin"

    with Session(get_engine()) as session:
        access_code = session.exec(
            select(AccessCode).where(AccessCode.apartment_id == "apartment-07")
        ).first()
        assert access_code is not None
        assert access_code.valid_from.hour == 9
        assert access_code.valid_until.hour == 11
