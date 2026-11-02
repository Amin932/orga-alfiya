"""Persistent notification dispatcher and due-date scheduler (deduplicated, Europe/Paris)."""
import json
import logging
import os
import smtplib
import ssl
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row

from .notifications_v7 import notify, preference, card_link_context

LOG=logging.getLogger("orga.notifications")
PARIS=ZoneInfo("Europe/Paris")
PUBLIC_URL=os.getenv("ORGA_PUBLIC_URL","https://orga-alfiya.amvei.synology.me").rstrip("/")


def connection():
    return psycopg.connect(os.environ["DATABASE_URL"],row_factory=dict_row,connect_timeout=5)


def enqueue_due_reminders(conn, local_date):
    """Can run repeatedly; per recipient/card/deadline/phase unique key avoids repeats."""
    events=((3,"reminder","Échéance dans 3 jours","J-3"),
            (1,"reminder","Échéance demain","J-1"),
            (0,"reminder","Échéance aujourd'hui","J0"),
            (-1,"overdue","Échéance dépassée","J+1"))
    # Short transactions, avoid delaying deliveries.
    for offset,event,title,phase in events:
        deadline=local_date+timedelta(days=offset)
        cards=conn.execute("""SELECT c.id,c.title,c.due_date FROM cards c
            WHERE c.deleted_at IS NULL AND c.status!='done' AND c.due_date=%s""",
            (deadline,)).fetchall()
        for card in cards:
            member_ids={r["user_id"] for r in conn.execute("""SELECT ca.user_id FROM card_assignees ca
                JOIN users u ON u.id=ca.user_id WHERE ca.card_id=%s AND u.active=true""",
                (card["id"],)).fetchall()}
            for user_id in member_ids:
                notify(conn,user_id,event,title,
                       f'« {card["title"]} » : échéance du {card["due_date"].strftime("%d/%m/%Y")}.',
                       card_id=card["id"],dedupe_key=f'due:{card["id"]}:{deadline}:{phase}')
            if phase=="J+1":
                admins=conn.execute("""SELECT id FROM users WHERE role='superadmin' AND active=true""").fetchall()
                for admin in admins:
                    if admin["id"] not in member_ids:
                        notify(conn,admin["id"],"critical","Mission en retard",
                               f'« {card["title"]} » a dépassé son échéance.',
                               card_id=card["id"],dedupe_key=f'admin-overdue:{card["id"]}:{deadline}')


def card_url(conn,card_id):
    if card_id is None: return PUBLIC_URL+"/"
    c=card_link_context(conn,card_id)
    if not c or c["deleted_at"] is not None: return PUBLIC_URL+"/"
    query=urlencode({"project":c["project_id"],"pole":c["pole_id"],"card":c["id"]})
    return PUBLIC_URL+"/?"+query


def smtp_send(to,subject,body):
    params=[os.getenv(k,"") for k in ("SMTP_HOST","SMTP_USERNAME","SMTP_PASSWORD","SMTP_FROM")]
    if not all(params): raise RuntimeError("SMTP non configuré")
    host,user,pwd,sender=params
    port=int(os.getenv("SMTP_PORT","465"))
    msg=EmailMessage()
    msg["From"],msg["To"],msg["Subject"]=sender,to,subject
    msg.set_content(body)
    if port==465:
        with smtplib.SMTP_SSL(host,port,timeout=20,context=ssl.create_default_context()) as s:
            s.login(user,pwd);s.send_message(msg)
    elif port==587:
        with smtplib.SMTP(host,port,timeout=20) as s:
            s.starttls(context=ssl.create_default_context());s.login(user,pwd);s.send_message(msg)
    else: raise RuntimeError("Port SMTP non pris en charge")


def push_send(user_id, title, message, url):
    from pywebpush import webpush, WebPushException
    key_path=os.getenv("VAPID_PRIVATE_KEY_FILE","")
    contact=os.getenv("VAPID_CONTACT","")
    if not key_path or not os.path.isfile(key_path) or not contact.startswith("mailto:"):
        raise RuntimeError("Clé VAPID ou contact non configuré")
    with connection() as conn:
        subscriptions=conn.execute("""SELECT id,endpoint,p256dh,auth FROM push_subscriptions
            WHERE user_id=%s""",(user_id,)).fetchall()
    if not subscriptions:
        return 0
    count=0
    for sub in subscriptions:
        try:
            webpush(subscription_info={"endpoint":sub["endpoint"],
                     "keys":{"p256dh":sub["p256dh"],"auth":sub["auth"]}},
                    data=json.dumps({"title":title,"body":message,"url":url},ensure_ascii=False),
                    vapid_private_key=key_path,vapid_claims={"sub":contact},ttl=3600)
            count+=1
        except WebPushException as exc:
            status=getattr(getattr(exc,"response",None),"status_code",None)
            if status in (404,410):
                with connection() as conn:
                    conn.execute("DELETE FROM push_subscriptions WHERE id=%s",(sub["id"],))
            else:
                raise
    return count


def process_deliveries(limit=25):
    done=0
    for _ in range(limit):
        with connection() as conn:
            row=conn.execute("""SELECT d.id,d.channel,d.attempts,n.user_id,n.title,n.message,
                n.event_type,n.card_id,u.email,u.active FROM notification_deliveries d
                JOIN notifications n ON n.id=d.notification_id
                JOIN users u ON u.id=n.user_id
                WHERE (d.status='pending' AND d.next_attempt_at<=now())
                 OR (d.status='processing' AND d.locked_at<now()-interval '15 minutes')
                ORDER BY d.id FOR UPDATE OF d SKIP LOCKED LIMIT 1""").fetchone()
            if not row: return done
            conn.execute("""UPDATE notification_deliveries SET status='processing',locked_at=now(),
                attempts=attempts+1 WHERE id=%s""",(row["id"],))
            prefs=preference(conn,row["user_id"])
            link=card_url(conn,row["card_id"])
        failure=None
        try:
            if not row["active"] or not prefs["events"].get(row["event_type"],True) or not prefs[row["channel"]+"_enabled"]:
                raise ValueError("Notifications désactivées ou compte inactif")
            if row["channel"]=="email":
                smtp_send(row["email"],"Orga Alfiya — "+row["title"],row["message"]+"\n\nAccéder à Orga Alfiya : "+link)
            else:
                push_send(row["user_id"],row["title"],row["message"],link)
        except Exception as exc:
            failure=exc
            LOG.warning("Échec d'envoi notification %s (%s): %s",row["id"],row["channel"],type(exc).__name__)
        with connection() as conn:
            if failure is None:
                conn.execute("""UPDATE notification_deliveries SET status='sent',sent_at=now(),
                    locked_at=NULL,last_error=NULL WHERE id=%s""",(row["id"],))
            else:
                is_disabled=isinstance(failure,ValueError)
                final=is_disabled or row["attempts"]+1>=5
                delay=min(3600,60*2**row["attempts"])
                conn.execute("""UPDATE notification_deliveries SET status=%s,locked_at=NULL,
                    next_attempt_at=now()+(%s * interval '1 second'),last_error=%s WHERE id=%s""",
                    ("failed" if final else "pending",delay,type(failure).__name__,row["id"]))
        done+=1
    return done


def tick():
    today=datetime.now(PARIS)
    if today.hour >= 9:
        with connection() as conn:
            enqueue_due_reminders(conn,today.date())
    return process_deliveries()


def main():
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s")
    LOG.info("Service de notifications démarré")
    while True:
        try:
            count=tick()
            if count: LOG.info("Envois traités : %s",count)
        except (Exception) as exc:
            LOG.exception("Erreur du service de notifications : %s",type(exc).__name__)
        time.sleep(60)


if __name__=="__main__":
    main()
