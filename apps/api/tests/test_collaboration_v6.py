"""Bloc 6 : validation des commentaires, formats de fichiers, routes privées."""
import io
import pytest
from fastapi.testclient import TestClient

from app.main import app, current_user
from app.collaboration_v6 import (CommentInput, CoverInput, valid_signature, MENTION,
                                   MAX_FILE_BYTES, EXTENSIONS)


@pytest.fixture(autouse=True)
def clear():
    yield
    app.dependency_overrides.clear()


def test_comment_non_empty_and_length():
    assert CommentInput(body=" @Trésorerie ").body
    with pytest.raises(ValueError):
        CommentInput(body="  ")
    with pytest.raises(ValueError):
        CommentInput(body="X" * 5001)


def test_mention_token_parser():
    text = "Bonjour @[Sarah Majid](user:14) et @[Trésorerie](pole:5) !"
    assert MENTION.findall(text) == [("user", "14"), ("pole", "5")]
    assert not MENTION.findall("@[Bad](admin:1)")


def test_file_signatures_and_limit():
    assert valid_signature(".png", b"\x89PNG\r\n\x1a\nmore")
    assert valid_signature(".jpg", b"\xff\xd8\xffrest")
    assert valid_signature(".webp", b"RIFF\x00\x00\x00\x00WEBP")
    assert valid_signature(".pdf", b"%PDF-1.7")
    assert valid_signature(".docx", b"PK\x03\x04data")
    assert not valid_signature(".png", b"<script>not an image</script>")
    assert ".svg" not in EXTENSIONS
    assert MAX_FILE_BYTES == 15 * 1024 * 1024


def test_cover_input():
    assert CoverInput(attachment_id=None).attachment_id is None
    with pytest.raises(ValueError):
        CoverInput(attachment_id=-3)


def test_collaboration_requires_login():
    client = TestClient(app)
    assert client.get("/api/cards/10/collaboration").status_code == 401
    assert client.get("/api/cards/10/attachments/2").status_code == 401
    assert client.get("/api/projects/1/mentions").status_code == 401


def test_comments_need_csrf_protection():
    app.dependency_overrides[current_user] = lambda: {"id": 2, "role": "member"}
    client = TestClient(app)
    assert client.post("/api/cards/1/comments", json={"body": "Bonjour"}).status_code == 403
    assert client.patch("/api/cards/1/comments/5", json={"body": "Edit"}).status_code == 403
    assert client.delete("/api/cards/1/comments/5").status_code == 403
    assert client.post("/api/cards/1/cover", json={"attachment_id": None}).status_code == 403


def test_file_upload_needs_csrf_header():
    app.dependency_overrides[current_user] = lambda: {"id": 2, "role": "member"}
    client = TestClient(app)
    response = client.post("/api/cards/2/attachments",
                           files={"file": ("test.png", io.BytesIO(b"\x89PNG\r\n\x1a\n"), "image/png")})
    assert response.status_code == 403
