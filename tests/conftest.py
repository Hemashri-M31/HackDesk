import pytest
from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app


@pytest.fixture
def client():
    app.dependency_overrides[get_settings] = lambda: Settings(
        app_name="HackDesk",
        environment="test",
        llm_api_key="test-key",
        database_url="sqlite:///:memory:",
    )
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
