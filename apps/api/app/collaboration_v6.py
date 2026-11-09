"""Bloc 6 : commentaires, mentions, pièces jointes privées, couverture et historique."""
import mimetypes
import os
import re
import secrets
from pathlib import Path

from fastapi import Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, model_validator
from psycopg.types.json import Jsonb
from .notifications_v7 import notify, subscribers

UPLOAD_DIR = Path(os.environ.get("ORGA_UPLOAD_DIR", "/app/uploads"))
MAX_FILE_BYTES = 15 * 1024 * 1024
EXTENSIONS = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif", ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".txt": "text/plain",
}
MENTION = re.compile(r"@\[[^\]\r\n]{1,100}\]\((user|pole):([0-9]{1,19})\)")


class CommentInput(BaseModel):
    body: str = Field(min_length=1, max_length=5000)

    @model_validator(mode="after")
    def non_empty(self):
        if not self.body.strip():
            raise ValueError("Le commentaire ne peut pas être vide")
        return self


class CoverInput(BaseModel):
    attachment_id: int | None = Field(default=None, gt=0)


def valid_signature(extension, first):
    if extension == ".png":
        return first.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in (".jpg", ".jpeg"):
        return first.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return first.startswith(b"RIFF") and first[8:12] == b"WEBP"
    if extension == ".gif":
        return first.startswith((b"GIF87a", b"GIF89a"))
    if extension == ".pdf":
        return first.startswith(b"%PDF-")
    if extension in (".docx", ".xlsx", ".pptx"):
        return first.startswith(b"PK\x03\x04")
    if extension == ".txt":
        return b"\x00" not in first
    return False


def schema_collaboration(db):
    with db() as conn:
        for statement in [
            """CREATE TABLE IF NOT EXISTS card_comments (
                id BIGSERIAL PRIMARY KEY,
                card_id BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                author_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                body TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                deleted_at TIMESTAMPTZ
            )""",
            """CREATE TABLE IF NOT EXISTS comment_mentions (
                comment_id BIGINT NOT NULL REFERENCES card_comments(id) ON DELETE CASCADE,
                target_type TEXT NOT NULL CHECK(target_type IN ('user','pole')),
                target_id BIGINT NOT NULL,
                PRIMARY KEY(comment_id,target_type,target_id)
            )""",
            """CREATE TABLE IF NOT EXISTS card_attachments (
                id BIGSERIAL PRIMARY KEY,
                card_id BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                uploaded_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                stored_name TEXT NOT NULL UNIQUE,
                file_name TEXT NOT NULL,
                mime_type TEXT NOT NULL,
                size_bytes BIGINT NOT NULL CHECK(size_bytes > 0 AND size_bytes <= 15728640),
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "ALTER TABLE cards ADD COLUMN IF NOT EXISTS cover_attachment_id BIGINT REFERENCES card_attachments(id) ON DELETE SET NULL",
            """CREATE TABLE IF NOT EXISTS card_activity (
                id BIGSERIAL PRIMARY KEY,
                card_id BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                actor_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                action TEXT NOT NULL,
                details JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "CREATE INDEX IF NOT EXISTS card_comments_idx ON card_comments(card_id,id)",
            "CREATE INDEX IF NOT EXISTS card_files_idx ON card_attachments(card_id,id)",
            "CREATE INDEX IF NOT EXISTS card_activity_idx ON card_activity(card_id,id)",
        ]:
            conn.execute(statement)


# Any genuine work on a newly created mission moves it into "En cours".
# Administrative actions (handoff, creation, deletion, restoration, sorting) do not.
WORK_STARTED_ACTIONS = frozenset({
    "card_updated", "assignees_changed", "template_updated",
    "checklist_created", "checklist_renamed", "checklist_deleted",
    "checklist_item_added", "checklist_item_updated",
    "checklist_checked", "checklist_item_deleted",
    "comment_created", "comment_updated", "comment_deleted",
    "file_added", "file_deleted", "cover_changed",
})


def record_activity(conn, card_id, actor_id, action, details=None):
    if action in WORK_STARTED_ACTIONS:
        conn.execute("""UPDATE cards AS c SET status='progress', updated_at=now(),
            position=(SELECT COALESCE(MAX(other.position), -1)+1
                      FROM cards other WHERE other.pole_id=c.pole_id
                        AND other.status='progress' AND other.deleted_at IS NULL)
            WHERE c.id=%s AND c.status='todo' AND c.deleted_at IS NULL""", (card_id,))
    conn.execute("""INSERT INTO card_activity(card_id,actor_id,action,details)
        VALUES (%s,%s,%s,%s)""", (card_id, actor_id, action, Jsonb(details or {})))


def purge_card_files(conn, card_id):
    """Return stored filenames before a permanent DB deletion; unlink only after commit."""
    records = conn.execute("SELECT stored_name FROM card_attachments WHERE card_id=%s",
                           (card_id,)).fetchall()
    return [r["stored_name"] for r in records]


def unlink_stored_files(names):
    for name in names:
        if re.fullmatch(r"[0-9a-f]{32}\.(?:jpg|jpeg|png|webp|gif|pdf|docx|xlsx|pptx|txt)", name):
            try:
                (UPLOAD_DIR / name).unlink(missing_ok=True)
            except OSError:
                pass


def register_collaboration_routes(app, db, current_user, require_request):
    def get_card(conn, card_id, user):
        card = conn.execute("""SELECT c.id,c.deleted_at,p.project_id FROM cards c
            JOIN poles p ON p.id=c.pole_id WHERE c.id=%s""", (card_id,)).fetchone()
        if not card or card["deleted_at"] is not None:
            raise HTTPException(404, "Carte introuvable")
        if user["role"] != "superadmin" and not conn.execute(
            "SELECT 1 FROM project_access WHERE user_id=%s AND project_id=%s",
            (user["id"], card["project_id"])).fetchone():
            raise HTTPException(404, "Carte introuvable")
        return card

    def validate_mentions(conn, card_id, user, text):
        card = get_card(conn, card_id, user)
        found = {(kind, int(target)) for kind, target in MENTION.findall(text)}
        if len(found) > 30:
            raise HTTPException(422, "Trop de mentions")
        for kind, target_id in found:
            if kind == "user":
                row = conn.execute("""SELECT 1 FROM users u
                    LEFT JOIN project_access pa ON pa.user_id=u.id AND pa.project_id=%s
                    WHERE u.id=%s AND u.active=true
                    AND (u.role='superadmin' OR pa.user_id IS NOT NULL)""",
                    (card["project_id"], target_id)).fetchone()
            else:
                row = conn.execute("""SELECT 1 FROM poles
                    WHERE id=%s AND project_id=%s""", (target_id,card["project_id"])).fetchone()
            if not row:
                raise HTTPException(422, "Mention non autorisée pour ce projet")
        return sorted(found)

    @app.get("/api/projects/{project_id}/mentions")
    def mention_targets(project_id: int, user=Depends(current_user)):
        with db() as conn:
            if user["role"] != "superadmin" and not conn.execute(
                "SELECT 1 FROM project_access WHERE user_id=%s AND project_id=%s",
                (user["id"], project_id)).fetchone():
                raise HTTPException(404, "Projet introuvable")
            project = conn.execute("SELECT 1 FROM projects WHERE id=%s", (project_id,)).fetchone()
            if not project:
                raise HTTPException(404, "Projet introuvable")
            people = conn.execute("""SELECT DISTINCT u.id,u.first_name,u.last_name,
                (SELECT po.color FROM user_poles up JOIN poles po ON po.id=up.pole_id
                 WHERE up.user_id=u.id ORDER BY up.position,po.id LIMIT 1) AS color
                FROM users u LEFT JOIN project_access pa ON pa.user_id=u.id AND pa.project_id=%s
                WHERE u.active=true AND (u.role='superadmin' OR pa.user_id IS NOT NULL)
                ORDER BY u.first_name,u.last_name,u.id""", (project_id,)).fetchall()
            poles = conn.execute("SELECT id,name,color FROM poles WHERE project_id=%s ORDER BY name,id",
                                 (project_id,)).fetchall()
        return {"users":people, "poles":poles}

    @app.get("/api/cards/{card_id}/collaboration")
    def collaboration(card_id: int, user=Depends(current_user)):
        with db() as conn:
            get_card(conn,card_id,user)
            comments = conn.execute("""SELECT cm.id,cm.body,cm.created_at,cm.updated_at,
                cm.author_id,u.first_name,u.last_name,
                (SELECT po.color FROM user_poles up JOIN poles po ON po.id=up.pole_id
                  WHERE up.user_id=cm.author_id ORDER BY up.position,po.id LIMIT 1) AS color
                FROM card_comments cm JOIN users u ON u.id=cm.author_id
                WHERE cm.card_id=%s AND cm.deleted_at IS NULL ORDER BY cm.id""",(card_id,)).fetchall()
            files = conn.execute("""SELECT a.id,a.file_name,a.mime_type,a.size_bytes,
                a.created_at,a.uploaded_by,u.first_name,u.last_name,
                a.id=(SELECT cover_attachment_id FROM cards WHERE id=%s) AS is_cover
                FROM card_attachments a JOIN users u ON u.id=a.uploaded_by
                WHERE a.card_id=%s ORDER BY a.id""",(card_id,card_id)).fetchall()
            activity = conn.execute("""SELECT ac.id,ac.action,ac.details,ac.created_at,ac.actor_id,
                u.first_name,u.last_name,
                (SELECT po.color FROM user_poles up JOIN poles po ON po.id=up.pole_id
                  WHERE up.user_id=ac.actor_id ORDER BY up.position,po.id LIMIT 1) AS color
                FROM card_activity ac JOIN users u ON u.id=ac.actor_id
                WHERE ac.card_id=%s ORDER BY ac.id DESC LIMIT 150""",(card_id,)).fetchall()
        return {"comments":comments,"files":files,"activity":activity}

    @app.post("/api/cards/{card_id}/comments", status_code=201)
    def comment(card_id:int, body: CommentInput, request:Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            mentions = validate_mentions(conn,card_id,user,body.body)
            cm = conn.execute("""INSERT INTO card_comments(card_id,author_id,body)
                VALUES (%s,%s,%s) RETURNING id""",(card_id,user["id"],body.body.strip())).fetchone()
            for kind,target in mentions:
                conn.execute("""INSERT INTO comment_mentions(comment_id,target_type,target_id)
                    VALUES (%s,%s,%s)""",(cm["id"],kind,target))
            record_activity(conn,card_id,user["id"],"comment_created",{"comment_id":cm["id"]})
            card = conn.execute("SELECT title,pole_id FROM cards WHERE id=%s",(card_id,)).fetchone()
            project_id=conn.execute("SELECT project_id FROM poles WHERE id=%s",(card["pole_id"],)).fetchone()["project_id"]
            mentioned=set()
            for kind,target in mentions:
                if kind=="user":
                    mentioned.add(target)
                else:
                    rows=conn.execute("""SELECT DISTINCT u.id FROM user_poles up
                        JOIN users u ON u.id=up.user_id
                        JOIN project_access a ON a.user_id=u.id AND a.project_id=%s
                        WHERE up.pole_id=%s AND u.active=true""",(project_id,target)).fetchall()
                    mentioned.update(r["id"] for r in rows)
            for member_id in mentioned:
                notify(conn,member_id,"mention","Vous avez été mentionné(e)",
                       f'Un membre vous a mentionné dans « {card["title"]} ».',card_id,
                       dedupe_key=f"mention:{cm['id']}:{member_id}",actor_id=user["id"])
            for member_id in set(subscribers(conn,card_id))-mentioned:
                notify(conn,member_id,"comment","Nouveau commentaire",
                       f'Nouveau commentaire dans « {card["title"]} ».',card_id,
                       dedupe_key=f"comment:{cm['id']}:{member_id}",actor_id=user["id"])
        return {"id":cm["id"],"status":"created"}

    @app.patch("/api/cards/{card_id}/comments/{comment_id}")
    def edit_comment(card_id:int, comment_id:int, body:CommentInput, request:Request,
                     user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            validate_mentions(conn,card_id,user,body.body)
            cm = conn.execute("""SELECT id,author_id FROM card_comments
                WHERE id=%s AND card_id=%s AND deleted_at IS NULL FOR UPDATE""",
                (comment_id,card_id)).fetchone()
            if not cm:
                raise HTTPException(404,"Commentaire introuvable")
            if cm["author_id"] != user["id"]:
                raise HTTPException(403,"Seul l'auteur peut modifier son commentaire")
            conn.execute("""UPDATE card_comments SET body=%s,updated_at=now() WHERE id=%s""",
                         (body.body.strip(),comment_id))
            conn.execute("DELETE FROM comment_mentions WHERE comment_id=%s",(comment_id,))
            for kind,target in validate_mentions(conn,card_id,user,body.body):
                conn.execute("""INSERT INTO comment_mentions(comment_id,target_type,target_id)
                    VALUES (%s,%s,%s)""",(comment_id,kind,target))
            record_activity(conn,card_id,user["id"],"comment_updated",{"comment_id":comment_id})
        return {"status":"updated"}

    @app.delete("/api/cards/{card_id}/comments/{comment_id}")
    def delete_comment(card_id:int, comment_id:int, request:Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_card(conn,card_id,user)
            cm = conn.execute("""SELECT author_id FROM card_comments
                WHERE id=%s AND card_id=%s AND deleted_at IS NULL FOR UPDATE""",
                (comment_id,card_id)).fetchone()
            if not cm:
                raise HTTPException(404,"Commentaire introuvable")
            if cm["author_id"] != user["id"] and user["role"] != "superadmin":
                raise HTTPException(403,"Suppression réservée à l'auteur ou au super-admin")
            conn.execute("UPDATE card_comments SET deleted_at=now() WHERE id=%s",(comment_id,))
            record_activity(conn,card_id,user["id"],"comment_deleted",{"comment_id":comment_id})
        return {"status":"deleted"}

    @app.post("/api/cards/{card_id}/attachments", status_code=201)
    async def upload_file(card_id:int, request:Request, file:UploadFile=File(...),
                          user=Depends(current_user)):
        require_request(request)
        name = Path((file.filename or "").replace("\\","/").split("/")[-1]).name
        name = re.sub(r"[\x00-\x1f\x7f]", "", name).strip()[:160]
        ext = Path(name).suffix.lower()
        if not name or ext not in EXTENSIONS:
            raise HTTPException(422,"Format de fichier non autorisé")
        with db() as conn:
            get_card(conn,card_id,user)
            count = conn.execute("SELECT count(*) AS total FROM card_attachments WHERE card_id=%s",
                                 (card_id,)).fetchone()["total"]
            if count >= 40:
                raise HTTPException(422,"Limite de 40 fichiers par carte")
        UPLOAD_DIR.mkdir(parents=True,exist_ok=True)
        storage_name = secrets.token_hex(16) + ext
        destination = UPLOAD_DIR / storage_name
        total = 0
        first = b""
        try:
            with destination.open("xb") as output:
                while chunk := await file.read(1024*1024):
                    total += len(chunk)
                    if total > MAX_FILE_BYTES:
                        raise HTTPException(413,"Fichier trop volumineux (15 Mo maximum)")
                    if not first:
                        first=chunk[:512]
                    output.write(chunk)
            if not total or not valid_signature(ext,first):
                raise HTTPException(422,"Fichier vide ou contenu non conforme au format")
            with db() as conn:
                get_card(conn,card_id,user)
                result = conn.execute("""INSERT INTO card_attachments
                    (card_id,uploaded_by,stored_name,file_name,mime_type,size_bytes)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING id""",
                    (card_id,user["id"],storage_name,name,EXTENSIONS[ext],total)).fetchone()
                record_activity(conn,card_id,user["id"],"file_added",
                                {"file_id":result["id"],"file_name":name})
            return {"id":result["id"],"file_name":name,"size_bytes":total}
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        finally:
            await file.close()

    @app.get("/api/cards/{card_id}/attachments/{file_id}")
    def download_file(card_id:int,file_id:int,user=Depends(current_user)):
        with db() as conn:
            get_card(conn,card_id,user)
            row = conn.execute("""SELECT stored_name,file_name,mime_type FROM card_attachments
                WHERE id=%s AND card_id=%s""",(file_id,card_id)).fetchone()
        if not row:
            raise HTTPException(404,"Fichier introuvable")
        path = UPLOAD_DIR / row["stored_name"]
        if not path.is_file():
            raise HTTPException(404,"Fichier indisponible")
        return FileResponse(path, media_type=row["mime_type"],filename=row["file_name"],
                            content_disposition_type="inline" if row["mime_type"].startswith("image/") else "attachment",
                            headers={"X-Content-Type-Options":"nosniff","Cache-Control":"private, no-store"})

    @app.post("/api/cards/{card_id}/cover")
    def cover(card_id:int, body:CoverInput, request:Request,user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_card(conn,card_id,user)
            if body.attachment_id is not None:
                row=conn.execute("""SELECT 1 FROM card_attachments WHERE id=%s
                    AND card_id=%s AND mime_type LIKE 'image/%%'""",
                    (body.attachment_id,card_id)).fetchone()
                if not row:
                    raise HTTPException(422,"Choisir une image de cette carte")
            conn.execute("UPDATE cards SET cover_attachment_id=%s,updated_at=now() WHERE id=%s",
                         (body.attachment_id,card_id))
            record_activity(conn,card_id,user["id"],"cover_changed",
                            {"attachment_id":body.attachment_id})
        return {"status":"updated"}

    @app.delete("/api/cards/{card_id}/attachments/{file_id}")
    def delete_file(card_id:int,file_id:int,request:Request,user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_card(conn,card_id,user)
            row=conn.execute("""SELECT id,stored_name,uploaded_by FROM card_attachments
                WHERE id=%s AND card_id=%s FOR UPDATE""",(file_id,card_id)).fetchone()
            if not row:
                raise HTTPException(404,"Fichier introuvable")
            if row["uploaded_by"] != user["id"] and user["role"] != "superadmin":
                raise HTTPException(403,"Seul l'auteur du fichier ou le super-admin peut le retirer")
            conn.execute("UPDATE cards SET cover_attachment_id=NULL WHERE cover_attachment_id=%s",
                         (file_id,))
            conn.execute("DELETE FROM card_attachments WHERE id=%s",(file_id,))
            record_activity(conn,card_id,user["id"],"file_deleted",{"file_id":file_id})
        unlink_stored_files([row["stored_name"]])
        return {"status":"deleted"}
