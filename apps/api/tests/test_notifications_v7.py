"""Bloc 7 — tests des notifications internes et Web Push sans SMTP."""
from datetime import date
import pytest
from fastapi.testclient import TestClient
from app.main import app, current_user
from app.notifications_v7 import (PreferenceInput, ReminderInput, push_endpoint_allowed,
                                   EVENT_TYPES)
from app.notification_worker_v7 import enqueue_due_reminders
import app.notification_worker_v7 as worker


@pytest.fixture(autouse=True)
def clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_default_notifications_and_invalid_offsets():
    body=ReminderInput()
    assert body.days_before == [3,1,0]
    assert body.overdue_next_day
    body.valid_days()
    with pytest.raises(Exception):
        ReminderInput(days_before=[3,3]).valid_days()
    with pytest.raises(Exception):
        ReminderInput(days_before=[4]).valid_days()
    PreferenceInput(push_enabled=True,events={
        event: True for event in EVENT_TYPES}).valid_events()
    with pytest.raises(Exception):
        PreferenceInput(push_enabled=True,events={}).valid_events()


def test_push_provider_allowlist():
    assert push_endpoint_allowed("https://fcm.googleapis.com/fcm/send/abc")
    assert push_endpoint_allowed("https://updates.push.services.mozilla.com/wpush/v2/a")
    assert push_endpoint_allowed("https://web.push.apple.com/a")
    assert not push_endpoint_allowed("http://127.0.0.1/internal")
    assert not push_endpoint_allowed("https://fcm.googleapis.com.evil.test/a")
    assert not push_endpoint_allowed("https://localhost/fcm")
    assert not push_endpoint_allowed("https://user:password@fcm.googleapis.com/a")


def test_reading_inbox_and_preferences_requires_session():
    c=TestClient(app)
    assert c.get("/api/notifications").status_code==401
    assert c.get("/api/notifications/preferences").status_code==401
    assert c.get("/api/cards/5/reminders").status_code==401
    assert c.get("/api/notifications/push-public-key").status_code==401


def test_mutations_require_csrf():
    app.dependency_overrides[current_user]=lambda: {"id":2,"role":"member"}
    c=TestClient(app)
    assert c.put("/api/notifications/preferences",json={
        "push_enabled":False,"events":{t:True for t in EVENT_TYPES}
    }).status_code==403
    assert c.post("/api/notifications/read-all",json={}).status_code==403
    assert c.put("/api/cards/1/follow",json={"follow":True}).status_code==403
    assert c.put("/api/cards/1/reminders",json={"days_before":[3],"overdue_next_day":False}).status_code==403


class FakeConnection:
    def execute(self, query, args=()):
        if "FROM cards c" in query:
            deadline=args[0]
            if deadline==date(2026,11,1):
                return FakeResult([{"id":5,"title":"Réserver la salle",
                    "due_date":deadline,"days_before":[3,1,0],
                    "overdue_next_day":True}])
            return FakeResult([])
        if "SELECT ca.user_id" in query:
            return FakeResult([{"user_id":8}])
        if "FROM users WHERE role='superadmin'" in query:
            return FakeResult([{"id":1}])
        raise AssertionError(query)


class FakeResult:
    def __init__(self,rows):self.rows=rows
    def fetchall(self):return self.rows


def test_due_reminder_j_plus_one_and_admin(monkeypatch):
    calls=[]
    monkeypatch.setattr(worker,"notify",lambda *args,**kwargs:calls.append((args,kwargs)))
    enqueue_due_reminders(FakeConnection(),date(2026,11,2))
    assert len(calls)==2
    assert calls[0][1]["dedupe_key"]=="due:5:2026-11-01:J+1"
    assert calls[1][1]["dedupe_key"]=="admin-overdue:5:2026-11-01"
