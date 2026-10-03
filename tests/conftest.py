"""Cấu hình chung cho pytest.
- Dùng DB riêng (test_trung_tam.db), không đụng vào DB chính.
- Tắt Gemini API để test dùng fallback.
"""
import os

# QUAN TRỌNG: set env TRƯỚC khi import app
os.environ["DATABASE_URL"] = "sqlite:///./test_trung_tam.db"
os.environ["GEMINI_API_KEY"] = ""

# Xóa DB test cũ (nếu có) để luôn chạy fresh
_DB_FILE = "test_trung_tam.db"
if os.path.exists(_DB_FILE):
    try:
        os.remove(_DB_FILE)
    except OSError:
        pass

import pytest
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app


@pytest.fixture(scope="session")
def _boot():
    """Chạy app 1 lần để tạo DB + seed data."""
    with TestClient(app):
        pass
    yield


@pytest.fixture
def client(_boot):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def db(_boot):
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _login(c: TestClient, username: str, password: str):
    return c.post(
        "/login",
        data={"username": username, "password": password},
        follow_redirects=False,
    )


@pytest.fixture
def admin_client(_boot):
    with TestClient(app) as c:
        r = _login(c, "admin", "admin123")
        assert r.status_code == 303, "Đăng nhập admin thất bại"
        yield c


@pytest.fixture
def tvv_client(_boot):
    with TestClient(app) as c:
        r = _login(c, "tvv1", "tvv123")
        assert r.status_code == 303, "Đăng nhập TVV thất bại"
        yield c


@pytest.fixture
def gv_client(_boot):
    with TestClient(app) as c:
        r = _login(c, "gv1", "gv123")
        assert r.status_code == 303, "Đăng nhập GV thất bại"
        yield c


@pytest.fixture
def hv_client(_boot):
    with TestClient(app) as c:
        r = _login(c, "hv1", "hv123")
        assert r.status_code == 303, "Đăng nhập HV thất bại"
        yield c