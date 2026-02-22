import pytest
from fastapi.testclient import TestClient
from main import app
from config import settings


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def api_key():
    return settings.app_api_key


@pytest.fixture
def auth_headers(api_key):
    return {"X-API-Key": api_key}
