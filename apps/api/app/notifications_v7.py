"""Notifications Orga Alfiya : événements, préférences, abonnements, push et boîte d'envoi."""
import base64
import json
import os
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

EVENT_TYPES = ("assignment", "mention", "comment", "completed", "reminder", "overdue", "project_access", "critical")
DEFAULT_EVENTS = {event: True for event in EVENT_TYPES}
MAX_ITEMS = 50


class PreferenceInput(BaseModel):
    email_enabled: bool
    push_enabled: bool
    events: dict[str, bool] = Field(default_factory=lambda: dict(DEFAULT_EVENTS))

    def valid_events(self):
        if set(self.events) != set(EVENT_TYPES):
            raise HTTPException(422, "Préférences incomplètes")


class PushSubscriptionInput(BaseModel):
    endpoint: str = Field(min_length=20, max_length=2048)
    p256dh: str = Field(min_length=20, max_length=256)
    auth: str = Field(min_length=8, max_length=128)


class FollowInput(BaseModel):
    follow: bool


def schema_notifications(db):
    with db() as conn:
        for sql in [
            """CREATE TABLE IF NOT EXISTS notification_preferences (
                user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
                email_enabled BOOLEAN NOT NULL DEFAULT true,
                push_enabled BOOLEAN NOT NULL DEFAULT true,
                events JSONB NOT NULL DEFAULT '{}'::jsonb
            )""",
            """CREATE TABLE IF NOT EXISTS notifications (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                card_id BIGINT REFERENCES cards(id) ON DELETE CASCADE,
                event_type TEXT NOT NULL,
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                dedupe_key TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                read_at TIMESTAMPTZ,
                UNIQUE(user_id, dedupe_key)
            )""",
            """CREATE TABLE IF NOT EXISTS notification_deliveries (
                id BIGSERIAL PRIMARY KEY,
                notification_id BIGINT NOT NULL REFERENCES notifications(id) ON DELETE CASCADE,
                channel TEXT NOT NULL CHECK(channel IN ('email','push')),
                status TEXT NOT NULL DEFAULT 'pending'
                    CHECK(status IN ('pending','processing','sent','failed')),
                attempts INT NOT NULL DEFAULT 0,
                next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                locked_at TIMESTAMPTZ,
                sent_at TIMESTAMPTZ,
                last_error TEXT,
                UNIQUE(notification_id,channel)
            )""",
            """CREATE TABLE IF NOT EXISTS card_followers (
                card_id BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY(card_id,user_id)
            )""",
            """CREATE TABLE IF NOT EXISTS push_subscriptions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                endpoint TEXT NOT NULL UNIQUE,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS notification_user_idx ON notifications(user_id,id DESC)",
            "CREATE INDEX IF NOT EXISTS deliveries_due_idx ON notification_deliveries(status,next_attempt_at)",
            "CREATE INDEX IF NOT EXISTS push_user_idx ON push_subscriptions(user_id)",
        ]:
            conn.execute(sql)


def preference(conn, user_id):
    row = conn.execute("""SELECT email_enabled,push_enabled,events FROM notification_preferences
        WHERE user_id=%s""",(user_id,)).fetchone()
    return {
        "email_enabled": row["email_enabled"] if row else True,
        "push_enabled": row["push_enabled"] if row else True,
        "events": {**DEFAULT_EVENTS, **(row["events"] if row else {})}
    }


def notify(conn, user_id, event, title, message, card_id=None, dedupe_key=None, actor_id=None):
    """Write notification and channel jobs atomically with the triggering action."""
    if event not in EVENT_TYPES or user_id == actor_id:
        return None
    target = conn.execute("SELECT active,role FROM users WHERE id=%s",(user_id,)).fetchone()
    if not target or not target["active"]:
        return None
    # Super-admin gets only critical events and actions addressed to their own work.
    if target["role"] == "superadmin" and event == "project_access":
        return None
    prefs=preference(conn,user_id)
    if not prefs["events"].get(event,True):
        return None
    notification = conn.execute("""INSERT INTO notifications
        (user_id,card_id,event_type,title,message,dedupe_key)
        VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id,dedupe_key) DO NOTHING RETURNING id""",
        (user_id,card_id,event,title[:150],message[:500],dedupe_key)).fetchone()
    if notification:
        for channel,enabled in (("email",prefs["email_enabled"]),("push",prefs["push_enabled"])):
            if enabled:
                conn.execute("""INSERT INTO notification_deliveries(notification_id,channel)
                    VALUES (%s,%s)""",(notification["id"],channel))
    return notification["id"] if notification else None


def subscribers(conn, card_id):
    return [r["user_id"] for r in conn.execute(
        "SELECT user_id FROM card_followers WHERE card_id=%s",(card_id,)).fetchall()]


def card_link_context(conn, card_id):
    return conn.execute("""SELECT c.id,c.title,c.status,c.due_date,c.deleted_at,
        p.project_id,c.pole_id FROM cards c JOIN poles p ON p.id=c.pole_id
        WHERE c.id=%s""",(card_id,)).fetchone()


def get_card_authorized(conn, card_id, user):
    c = card_link_context(conn,card_id)
    if not c or c["deleted_at"] is not None:
        raise HTTPException(404, "Carte introuvable")
    if user["role"] != "superadmin" and not conn.execute(
        "SELECT 1 FROM project_access WHERE user_id=%s AND project_id=%s",
        (user["id"],c["project_id"])).fetchone():
        raise HTTPException(404,"Carte introuvable")
    return c


def push_endpoint_allowed(endpoint):
    url = urlsplit(endpoint)
    if url.scheme != "https" or not url.hostname or url.username or url.password or url.fragment:
        return False
    host=url.hostname.lower()
    # Only known browser push providers: never POST to arbitrary private addresses.
    return (host in {"fcm.googleapis.com","updates.push.services.mozilla.com",
                     "web.push.apple.com"}
            or host.endswith(".push.apple.com")
            or host.endswith(".notify.windows.com"))


def vapid_public_key():
    path=os.environ.get("VAPID_PRIVATE_KEY_FILE","")
    if not path or not os.path.isfile(path):
        return None
    from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PublicFormat
    from cryptography.hazmat.primitives.asymmetric import ec
    with open(path,"rb") as f:
        private=load_pem_private_key(f.read(),password=None)
    if not isinstance(private,ec.EllipticCurvePrivateKey) or not isinstance(private.curve,ec.SECP256R1):
        raise ValueError("Clé VAPID EC P-256 attendue")
    value=private.public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def register_notification_routes(app, db, current_user, require_request):
    @app.get("/api/notifications")
    def inbox(user=Depends(current_user)):
        with db() as conn:
            notifications=conn.execute("""SELECT n.id,n.event_type,n.title,n.message,
                n.card_id,n.created_at,n.read_at,p.project_id,c.pole_id
                FROM notifications n LEFT JOIN cards c ON c.id=n.card_id
                LEFT JOIN poles p ON p.id=c.pole_id
                WHERE n.user_id=%s
                AND (n.card_id IS NULL OR (
                    c.deleted_at IS NULL AND
                    (%s='superadmin' OR EXISTS(
                     SELECT 1 FROM project_access a WHERE a.project_id=p.project_id
                      AND a.user_id=%s))))
                ORDER BY n.id DESC LIMIT %s""",
                (user["id"],user["role"],user["id"],MAX_ITEMS)).fetchall()
            unread=conn.execute("""SELECT COUNT(*) AS n FROM notifications n
                LEFT JOIN cards c ON c.id=n.card_id
                LEFT JOIN poles p ON p.id=c.pole_id
                WHERE n.user_id=%s AND n.read_at IS NULL
                AND (n.card_id IS NULL OR (
                    c.deleted_at IS NULL AND (%s='superadmin' OR EXISTS(
                    SELECT 1 FROM project_access a WHERE a.project_id=p.project_id AND a.user_id=%s))))""",
                (user["id"],user["role"],user["id"])).fetchone()["n"]
        return {"notifications":notifications,"unread":unread}

    @app.post("/api/notifications/{notification_id}/read")
    def read(notification_id:int, request:Request,user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            row=conn.execute("""UPDATE notifications SET read_at=now()
                WHERE id=%s AND user_id=%s RETURNING id""",
                (notification_id,user["id"])).fetchone()
            if not row: raise HTTPException(404,"Notification introuvable")
        return {"status":"read"}

    @app.post("/api/notifications/read-all")
    def read_all(request:Request,user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            conn.execute("UPDATE notifications SET read_at=now() WHERE user_id=%s AND read_at IS NULL",
                         (user["id"],))
        return {"status":"read"}

    @app.get("/api/notifications/preferences")
    def get_preferences(user=Depends(current_user)):
        with db() as conn: return preference(conn,user["id"])

    @app.put("/api/notifications/preferences")
    def save_preferences(body:PreferenceInput,request:Request,user=Depends(current_user)):
        require_request(request);body.valid_events()
        from psycopg.types.json import Jsonb
        with db() as conn:
            conn.execute("""INSERT INTO notification_preferences(user_id,email_enabled,push_enabled,events)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT(user_id) DO UPDATE SET email_enabled=EXCLUDED.email_enabled,
                    push_enabled=EXCLUDED.push_enabled,events=EXCLUDED.events""",
                (user["id"],body.email_enabled,body.push_enabled,Jsonb(body.events)))
            # Stop pending dispatches on disabled channels, even for past notifications.
            for channel, enabled in (("email",body.email_enabled),("push",body.push_enabled)):
                if not enabled:
                    conn.execute("""UPDATE notification_deliveries SET status='failed',last_error='Désactivé'
                        WHERE channel=%s AND status='pending'
                        AND notification_id IN (SELECT id FROM notifications WHERE user_id=%s)""",
                        (channel,user["id"]))
        return {"status":"updated"}

    @app.get("/api/cards/{card_id}/follow")
    def follow_status(card_id:int,user=Depends(current_user)):
        with db() as conn:
            get_card_authorized(conn,card_id,user)
            followed=bool(conn.execute("SELECT 1 FROM card_followers WHERE card_id=%s AND user_id=%s",
                                      (card_id,user["id"])).fetchone())
        return {"followed":followed}

    @app.put("/api/cards/{card_id}/follow")
    def follow_card(card_id:int,body:FollowInput,request:Request,user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_card_authorized(conn,card_id,user)
            if body.follow:
                conn.execute("""INSERT INTO card_followers(card_id,user_id) VALUES(%s,%s)
                    ON CONFLICT DO NOTHING""",(card_id,user["id"]))
            else: conn.execute("DELETE FROM card_followers WHERE card_id=%s AND user_id=%s",
                              (card_id,user["id"]))
        return {"followed":body.follow}

    @app.get("/api/notifications/push-public-key")
    def push_public(user=Depends(current_user)):
        return {"key":vapid_public_key()}

    @app.post("/api/notifications/push-subscriptions",status_code=201)
    def subscribe(body:PushSubscriptionInput,request:Request,user=Depends(current_user)):
        require_request(request)
        if not vapid_public_key():
            raise HTTPException(503,"Notifications push non configurées")
        if not push_endpoint_allowed(body.endpoint):
            raise HTTPException(422,"Service de notification push non reconnu")
        with db() as conn:
            owner=conn.execute("SELECT user_id FROM push_subscriptions WHERE endpoint=%s",
                               (body.endpoint,)).fetchone()
            if owner and owner["user_id"] != user["id"]:
                raise HTTPException(409,"Abonnement déjà utilisé par un autre compte")
            conn.execute("""INSERT INTO push_subscriptions(user_id,endpoint,p256dh,auth)
                VALUES (%s,%s,%s,%s)
                ON CONFLICT(endpoint) DO UPDATE SET p256dh=EXCLUDED.p256dh,auth=EXCLUDED.auth""",
                (user["id"],body.endpoint,body.p256dh,body.auth))
        return {"status":"subscribed"}

    @app.delete("/api/notifications/push-subscriptions")
    def unsubscribe(request:Request,user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            conn.execute("DELETE FROM push_subscriptions WHERE user_id=%s",(user["id"],))
        return {"status":"unsubscribed"}
