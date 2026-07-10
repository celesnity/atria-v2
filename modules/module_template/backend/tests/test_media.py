import importlib
import os
import sys

BACKEND = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, BACKEND)


class _FakeS3:
    def __init__(self): self.objects = {}
    def head_bucket(self, Bucket): pass
    def create_bucket(self, Bucket): pass
    def put_object(self, Bucket, Key, Body, ContentType): self.objects[Key] = Body
    def generate_presigned_url(self, op, Params, ExpiresIn): return f"http://minio/{Params['Key']}?sig=x"


def _fresh(monkeypatch, tmp_path):
    monkeypatch.setenv("MT_DATABASE_URL", f"sqlite:///{tmp_path}/t.db")
    import db, media
    importlib.reload(db); importlib.reload(media)
    db.init_db()
    fake = _FakeS3()
    monkeypatch.setattr(media, "s3_client", lambda: fake)
    return db, media, fake


def test_put_media_writes_s3_and_row(monkeypatch, tmp_path):
    db, media, fake = _fresh(monkeypatch, tmp_path)
    row = media.put_media("hello.txt", b"hi", "text/plain")
    assert row["filename"] == "hello.txt" and row["size"] == 2
    assert any(k.endswith("/hello.txt") for k in fake.objects)
    with db.db_session() as s:
        assert s.query(db.MtMedia).count() == 1


def test_presigned_url(monkeypatch, tmp_path):
    _db, media, _fake = _fresh(monkeypatch, tmp_path)
    assert media.presigned_url("k/hello.txt").startswith("http://minio/")
