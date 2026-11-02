"""Tests de protections du bloc 3, indépendants de PostgreSQL."""
import pytest
from fastapi.testclient import TestClient
from app.main import app, admin, current_user


@pytest.fixture(autouse=True)
def reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_admin_endpoints_refuse_members():
    app.dependency_overrides[current_user] = lambda: {"id": 8, "role": "member"}
    client = TestClient(app)
    response = client.get("/api/admin/directory")
    assert response.status_code == 403


def test_admin_mutations_require_custom_header():
    app.dependency_overrides[admin] = lambda: {"id": 1, "role": "superadmin"}
    client = TestClient(app)
    response = client.post("/api/admin/users/8/poles", json={"pole_ids": []})
    assert response.status_code == 403


def test_duplicate_poles_rejected_before_database():
    app.dependency_overrides[admin] = lambda: {"id": 1, "role": "superadmin"}
    client = TestClient(app)
    response = client.post("/api/admin/users/8/poles",
                           json={"pole_ids": [3, 3]}, headers={"X-Orga-Request": "1"})
    assert response.status_code == 422


def test_invalid_pole_color_rejected():
    app.dependency_overrides[admin] = lambda: {"id": 1, "role": "superadmin"}
    client = TestClient(app)
    response = client.post("/api/admin/projects/1/poles/2/edit",
                           json={"name":"Trésorerie", "color":"red"},
                           headers={"X-Orga-Request":"1"})
    assert response.status_code == 422
