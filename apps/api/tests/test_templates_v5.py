"""Bloc 5 : structures des modèles, accès et validation des requêtes."""
import pytest
from fastapi.testclient import TestClient
from app.main import app, current_user
from app.templates_v5 import TemplateInput, FormField, official_definitions, ValuesUpdate


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_official_models_and_required_sections():
    models = {template["slug"]: template for template in official_definitions()}
    assert set(models) == {"speaker", "no_speaker"}
    speaker = models["speaker"]
    assert {f["section"] for f in speaker["fields"]} == {"Description", "Infos"}
    assert {c["title"] for c in speaker["checklists"]} == {
        "Préparation avant le jour J", "Post-événement"
    }
    assert len(speaker["checklists"][0]["items"]) == 7
    assert len(speaker["checklists"][1]["items"]) == 5
    assert len(models["no_speaker"]["checklists"][0]["items"]) == 7


def test_field_keys_unique_and_validated():
    with pytest.raises(ValueError):
        TemplateInput(name="Doublons", fields=[
            FormField(key="same", section="Infos", label="Un"),
            FormField(key="same", section="Infos", label="Deux"),
        ])
    with pytest.raises(ValueError):
        FormField(key="Bad Key", section="Infos", label="Invalide")
    with pytest.raises(ValueError):
        FormField(key="kind", section="Infos", label="Choix", kind="choice", options=[])


def test_blank_optional_fields_allowed():
    template = TemplateInput(name="Mon modèle")
    assert template.fields == []
    values = ValuesUpdate(values={"budget": "", "event_date": None})
    assert values.values["budget"] == ""


def test_global_library_requires_authentication():
    r = TestClient(app).get("/api/templates")
    assert r.status_code == 401


def test_new_template_requires_csrf_header():
    app.dependency_overrides[current_user] = lambda: {"id": 2, "role": "member"}
    r = TestClient(app).post("/api/templates", json={"name": "Test", "fields": [], "checklists": []})
    assert r.status_code == 403


def test_card_contents_require_authentication():
    r = TestClient(app).get("/api/cards/5/template-content")
    assert r.status_code == 401
