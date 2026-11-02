"""Tests de validation et d'accès du Kanban sans PostgreSQL."""
import pytest
from fastapi.testclient import TestClient
from app.main import app, current_user, admin
from app.kanban import CardCreate, CardEdit


@pytest.fixture(autouse=True)
def reset_dependencies():
    yield
    app.dependency_overrides.clear()


def test_title_is_required_even_when_using_template():
    with pytest.raises(ValueError):
        CardCreate(title="")
    with pytest.raises(ValueError):
        CardCreate(title=" " * 3, template_key="speaker")


def test_templates_and_statuses_restricted():
    with pytest.raises(ValueError):
        CardCreate(title="Activité", template_key="unknown")
    with pytest.raises(ValueError):
        CardCreate(title="Activité", status="archived")


def test_blank_edit_title_rejected():
    with pytest.raises(ValueError):
        CardEdit(title="")
    with pytest.raises(ValueError):
        CardEdit(title=None)


def test_empty_optional_dates_allowed():
    card = CardEdit(start_date=None, due_date=None, description="")
    assert card.description == ""


def test_cards_require_authentication():
    response = TestClient(app).get("/api/poles/19/cards")
    assert response.status_code == 401


def test_mutations_require_csrf_header():
    app.dependency_overrides[current_user] = lambda: {"id": 2, "role": "member"}
    client = TestClient(app)
    response = client.post("/api/poles/5/cards", json={"title": "Réunion"})
    assert response.status_code == 403


def test_admin_trash_requires_superadmin():
    app.dependency_overrides[current_user] = lambda: {"id": 2, "role": "member"}
    response = TestClient(app).get("/api/admin/cards/trash")
    assert response.status_code == 403


def test_admin_delete_requires_csrf():
    app.dependency_overrides[admin] = lambda: {"id": 1, "role": "superadmin"}
    response = TestClient(app).delete("/api/admin/cards/1")
    assert response.status_code == 403
