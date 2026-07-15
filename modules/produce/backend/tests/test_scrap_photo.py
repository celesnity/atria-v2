"""E5 defect photo attach (P-SCRAP-03). Service layer runs anywhere; the route
test mocks MinIO and skips if python-multipart is absent from the dev venv."""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import db


@pytest.fixture(autouse=True)
def sqlite_engine(monkeypatch):
    eng = create_engine("sqlite://", future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()
    yield


def test_set_photo_updates_record():
    from domain.scrap import service

    sc = service.record_scrap("D-01", 3, station_id=1)
    updated = service.set_photo(sc["id"], "scrap/1/abc-photo.jpg")
    assert updated["photo_ref"] == "scrap/1/abc-photo.jpg"
    assert service.get_scrap(sc["id"])["photo_ref"] == "scrap/1/abc-photo.jpg"

    with pytest.raises(service.ScrapError):
        service.set_photo(9999, "x")


def test_photo_upload_route_with_mocked_minio(monkeypatch, tmp_path):
    pytest.importorskip("multipart")
    from fastapi.testclient import TestClient

    # In-memory SQLite is per-connection/thread; TestClient serves the request on
    # another thread, so use a file-backed DB shared across threads for this test.
    file_url = f"sqlite:///{tmp_path/'produce.db'}"
    eng = create_engine(file_url, future=True)
    monkeypatch.setattr(db, "_engine", eng)
    monkeypatch.setattr(db, "_SessionLocal", sessionmaker(bind=eng, future=True))
    monkeypatch.setattr(db, "get_engine", lambda: eng)
    db.init_db()

    import media
    from domain.scrap import service

    monkeypatch.setattr(media, "ensure_bucket", lambda: None)
    monkeypatch.setattr(media, "put_defect_photo", lambda sid, fn, data, ct: f"scrap/{sid}/{fn}")
    monkeypatch.setattr(media, "presigned_url", lambda key, expires=3600: f"http://minio/{key}")

    import app

    sc = service.record_scrap("D-02", 2, station_id=1)
    c = TestClient(app.app)
    r = c.post(
        f"/scrap/records/{sc['id']}/photo",
        files={"file": ("defect.jpg", b"\xff\xd8\xff", "image/jpeg")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["photo_ref"] == f"scrap/{sc['id']}/defect.jpg"
    assert service.get_scrap(sc["id"])["photo_ref"] == body["photo_ref"]

    assert c.post("/scrap/records/9999/photo", files={"file": ("x.jpg", b"x", "image/jpeg")}).status_code == 404
