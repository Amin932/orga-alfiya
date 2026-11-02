"""API Kanban : accès par projet, cartes, déplacement et corbeille."""
from datetime import date, datetime
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from .templates_v5 import instantiate_template
from .collaboration_v6 import record_activity, purge_card_files, unlink_stored_files
from .notifications_v7 import notify, subscribers

Status = Literal["todo", "progress", "done"]
Template = Literal["free", "speaker", "no_speaker"]


class CardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    status: Status = "todo"
    template_key: Template = "free"
    template_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def title_required(self):
        if not self.title.strip():
            raise ValueError("Le titre est obligatoire")
        return self


class CardEdit(BaseModel):
    title: str | None = Field(default=None, max_length=180)
    description: str | None = Field(default=None, max_length=20000)
    start_date: date | None = None
    due_date: date | None = None

    @model_validator(mode="after")
    def ensure_valid(self):
        if "title" in self.model_fields_set and (self.title is None or not self.title.strip()):
            raise ValueError("Le titre ne peut pas être vide")
        return self


class CardMove(BaseModel):
    status: Status
    before_id: int | None = None


class CardAssignees(BaseModel):
    user_ids: list[int] = Field(default_factory=list, max_length=100)


def schema_cards(db):
    with db() as conn:
        for sql in [
            """CREATE TABLE IF NOT EXISTS cards (
                id BIGSERIAL PRIMARY KEY,
                pole_id BIGINT NOT NULL REFERENCES poles(id) ON DELETE CASCADE,
                created_by BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
                title VARCHAR(180) NOT NULL CHECK (length(trim(title)) > 0),
                description TEXT NOT NULL DEFAULT '',
                template_key TEXT NOT NULL DEFAULT 'free'
                    CHECK (template_key IN ('free','speaker','no_speaker')),
                status TEXT NOT NULL DEFAULT 'todo'
                    CHECK (status IN ('todo','progress','done')),
                position INTEGER NOT NULL DEFAULT 0,
                start_date DATE,
                due_date DATE,
                deleted_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CHECK (due_date IS NULL OR start_date IS NULL OR due_date >= start_date)
            )""",
            """CREATE TABLE IF NOT EXISTS card_assignees (
                card_id BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY(card_id,user_id)
            )""",
            "CREATE INDEX IF NOT EXISTS cards_pole_status_idx ON cards(pole_id,status,position,id) WHERE deleted_at IS NULL",
            "CREATE INDEX IF NOT EXISTS cards_deleted_idx ON cards(deleted_at) WHERE deleted_at IS NOT NULL",
        ]:
            conn.execute(sql)


def register_card_routes(app, db, current_user, admin, require_request):
    def pole_access(conn, pole_id, user):
        pole = conn.execute("SELECT id,project_id FROM poles WHERE id=%s", (pole_id,)).fetchone()
        if not pole:
            raise HTTPException(404, "Pôle introuvable")
        if user["role"] != "superadmin":
            access = conn.execute(
                "SELECT 1 FROM project_access WHERE user_id=%s AND project_id=%s",
                (user["id"], pole["project_id"])).fetchone()
            if not access:
                raise HTTPException(404, "Pôle introuvable")
        return pole

    def card_access(conn, card_id, user, lock=False):
        sql = """SELECT c.*, p.project_id, u.first_name AS author_first_name,
                  u.last_name AS author_last_name FROM cards c
                  JOIN poles p ON p.id=c.pole_id
                  JOIN users u ON u.id=c.created_by WHERE c.id=%s"""
        row = conn.execute(sql + (" FOR UPDATE OF c" if lock else ""), (card_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Carte introuvable")
        pole_access(conn, row["pole_id"], user)
        return row

    def as_dict(conn, card):
        assignees = conn.execute("""SELECT u.id, u.first_name, u.last_name,
            (SELECT p.color FROM user_poles up JOIN poles p ON p.id=up.pole_id
             WHERE up.user_id=u.id ORDER BY up.position,p.id LIMIT 1) AS color
            FROM card_assignees ca JOIN users u ON u.id=ca.user_id
            WHERE ca.card_id=%s ORDER BY u.first_name,u.id""", (card["id"],)).fetchall()
        return {**card, "assignees": assignees}

    def check_dates(start, due):
        if start and due and due < start:
            raise HTTPException(422, "L'échéance doit être postérieure au début")

    @app.get("/api/poles/{pole_id}/cards")
    def list_cards(pole_id: int, user=Depends(current_user)):
        with db() as conn:
            pole_access(conn, pole_id, user)
            cards = conn.execute("""SELECT c.id,c.pole_id,c.title,c.description,c.template_key,c.template_id,c.cover_attachment_id,
                c.status,c.position,c.start_date,c.due_date,c.created_at,c.updated_at,
                c.created_by,u.first_name AS author_first_name,u.last_name AS author_last_name
                FROM cards c JOIN users u ON u.id=c.created_by
                WHERE c.pole_id=%s AND c.deleted_at IS NULL
                ORDER BY CASE c.status WHEN 'todo' THEN 0 WHEN 'progress' THEN 1 ELSE 2 END,
                c.position,c.id""", (pole_id,)).fetchall()
            return {"cards": [as_dict(conn, c) for c in cards]}

    @app.post("/api/poles/{pole_id}/cards", status_code=201)
    def create_card(pole_id: int, body: CardCreate, request: Request, user=Depends(current_user)):
        require_request(request)
        title = body.title.strip()
        if not title:
            raise HTTPException(422, "Le titre est obligatoire")
        with db() as conn:
            pole_access(conn, pole_id, user)
            conn.execute("SELECT id FROM poles WHERE id=%s FOR UPDATE", (pole_id,))
            position = conn.execute("""SELECT COALESCE(MAX(position),-1)+1 AS next
                FROM cards WHERE pole_id=%s AND status=%s AND deleted_at IS NULL""",
                (pole_id, body.status)).fetchone()["next"]
            card = conn.execute("""INSERT INTO cards
                (pole_id,created_by,title,status,template_key,position)
                VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                (pole_id,user["id"],title,body.status,body.template_key,position)).fetchone()
            template = None
            if body.template_id is not None:
                template = conn.execute("SELECT * FROM templates WHERE id=%s",
                                        (body.template_id,)).fetchone()
                if not template:
                    raise HTTPException(422, "Modèle introuvable")
            elif body.template_key in ("speaker", "no_speaker"):
                template = conn.execute("SELECT * FROM templates WHERE slug=%s",
                                        (body.template_key,)).fetchone()
            if template:
                instantiate_template(conn, card["id"], template)
                card["template_id"] = template["id"]
            record_activity(conn,card["id"],user["id"],"card_created",
                            {"title":title,"status":body.status})
            return as_dict(conn, card)

    @app.patch("/api/cards/{card_id}")
    def edit_card(card_id: int, body: CardEdit, request: Request, user=Depends(current_user)):
        require_request(request)
        allowed = {"title", "description", "start_date", "due_date"}
        fields = body.model_fields_set & allowed
        if not fields:
            raise HTTPException(422, "Aucun champ à mettre à jour")
        with db() as conn:
            card = card_access(conn, card_id, user, lock=True)
            if card["deleted_at"]:
                raise HTTPException(410, "Cette carte est dans la corbeille")
            values = {key: getattr(body, key) for key in fields}
            if "title" in values:
                values["title"] = values["title"].strip()
            check_dates(values.get("start_date",card["start_date"]),
                        values.get("due_date",card["due_date"]))
            columns = ", ".join(f"{field}=%s" for field in sorted(values))
            args = [values[key] for key in sorted(values)]
            row = conn.execute(f"UPDATE cards SET {columns},updated_at=now() WHERE id=%s RETURNING *",
                               (*args, card_id)).fetchone()
            record_activity(conn,card_id,user["id"],"card_updated",{"fields":sorted(values)})
            return as_dict(conn, row)

    @app.get("/api/projects/{project_id}/card-members")
    def card_members(project_id: int, user=Depends(current_user)):
        with db() as conn:
            project = conn.execute("SELECT id FROM projects WHERE id=%s", (project_id,)).fetchone()
            if not project:
                raise HTTPException(404, "Projet introuvable")
            if user["role"] != "superadmin" and not conn.execute(
                "SELECT 1 FROM project_access WHERE project_id=%s AND user_id=%s",
                (project_id,user["id"])).fetchone():
                raise HTTPException(404, "Projet introuvable")
            members = conn.execute("""SELECT DISTINCT u.id,u.first_name,u.last_name,
                (SELECT p.color FROM user_poles up JOIN poles p ON p.id=up.pole_id
                 WHERE up.user_id=u.id ORDER BY up.position,p.id LIMIT 1) AS color
                FROM users u LEFT JOIN project_access pa ON pa.user_id=u.id
                WHERE u.active=true AND (u.role='superadmin' OR pa.project_id=%s)
                ORDER BY u.first_name,u.last_name,u.id""", (project_id,)).fetchall()
            return {"members": members}

    @app.put("/api/cards/{card_id}/assignees")
    def set_assignees(card_id: int, body: CardAssignees, request: Request,
                      user=Depends(current_user)):
        require_request(request)
        ids = sorted(set(body.user_ids))
        with db() as conn:
            card = card_access(conn, card_id, user, lock=True)
            if card["deleted_at"]:
                raise HTTPException(410, "Carte supprimée")
            permitted = conn.execute("""SELECT DISTINCT u.id FROM users u
                LEFT JOIN project_access pa ON pa.user_id=u.id
                WHERE u.active=true AND (u.role='superadmin' OR pa.project_id=%s)
                AND u.id=ANY(%s)""", (card["project_id"], ids)).fetchall() if ids else []
            if {x["id"] for x in permitted} != set(ids):
                raise HTTPException(422, "Responsable sans accès à ce projet")
            previous = {r["user_id"] for r in conn.execute(
                "SELECT user_id FROM card_assignees WHERE card_id=%s",(card_id,)).fetchall()}
            conn.execute("DELETE FROM card_assignees WHERE card_id=%s", (card_id,))
            for member_id in ids:
                conn.execute("INSERT INTO card_assignees(card_id,user_id) VALUES (%s,%s)",
                             (card_id,member_id))
            conn.execute("UPDATE cards SET updated_at=now() WHERE id=%s", (card_id,))
            record_activity(conn,card_id,user["id"],"assignees_changed",{"member_ids":ids})
            for member_id in set(ids)-previous:
                conn.execute("""INSERT INTO card_followers(card_id,user_id) VALUES(%s,%s)
                    ON CONFLICT DO NOTHING""",(card_id,member_id))
                notify(conn,member_id,"assignment","Nouvelle mission attribuée",
                       f'Vous êtes responsable de « {card["title"]} ».',card_id,
                       actor_id=user["id"])
            return as_dict(conn, card)

    @app.post("/api/cards/{card_id}/move")
    def move_card(card_id: int, body: CardMove, request: Request, user=Depends(current_user)):
        require_request(request)
        # Serialize reorders per pole to avoid concurrent members corrupting positions.
        with db() as conn:
            card = card_access(conn, card_id, user)
            if card["deleted_at"]:
                raise HTTPException(410, "Carte supprimée")
            conn.execute("SELECT id FROM poles WHERE id=%s FOR UPDATE", (card["pole_id"],))
            card = card_access(conn, card_id, user, lock=True)
            if card["deleted_at"]:
                raise HTTPException(410, "Carte supprimée")
            if body.before_id == card_id:
                return {"status": "updated"}
            if body.before_id is not None:
                target = conn.execute("""SELECT id,pole_id,status FROM cards
                    WHERE id=%s AND deleted_at IS NULL""", (body.before_id,)).fetchone()
                if not target or target["pole_id"] != card["pole_id"] or target["status"] != body.status:
                    raise HTTPException(422, "Emplacement invalide")
            rows = conn.execute("""SELECT id,status FROM cards
                WHERE pole_id=%s AND deleted_at IS NULL AND id<>%s
                ORDER BY position,id""", (card["pole_id"], card_id)).fetchall()
            sequences = {status: [r["id"] for r in rows if r["status"] == status]
                         for status in ("todo", "progress", "done")}
            ordered = sequences[body.status]
            if body.before_id is None:
                ordered.append(card_id)
            else:
                ordered.insert(ordered.index(body.before_id), card_id)
            for status, card_ids in sequences.items():
                for pos, current_id in enumerate(card_ids):
                    conn.execute("""UPDATE cards SET status=%s,position=%s,
                        updated_at=CASE WHEN id=%s THEN now() ELSE updated_at END
                        WHERE id=%s""", (status,pos,card_id,current_id))
            record_activity(conn,card_id,user["id"],"card_moved",
                            {"from":card["status"],"to":body.status})
            if body.status=="done" and card["status"]!="done":
                for member_id in subscribers(conn,card_id):
                    notify(conn,member_id,"completed","Mission terminée",
                           f'« {card["title"]} » a été marquée terminée.',
                           card_id,actor_id=user["id"])
            return {"status": "updated"}

    @app.post("/api/cards/{card_id}/trash")
    def trash_card(card_id: int, request: Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            card = card_access(conn, card_id, user, lock=True)
            if card["created_by"] != user["id"] and user["role"] != "superadmin":
                raise HTTPException(403, "Seul le créateur ou le super-administrateur peut supprimer")
            if card["deleted_at"]:
                raise HTTPException(410, "Carte déjà placée dans la corbeille")
            conn.execute("UPDATE cards SET deleted_at=now(),updated_at=now() WHERE id=%s", (card_id,))
            record_activity(conn,card_id,user["id"],"card_trashed")
        return {"status": "trashed"}

    @app.get("/api/admin/cards/trash")
    def list_trash(user=Depends(admin)):
        with db() as conn:
            return {"cards": conn.execute("""SELECT c.id,c.title,c.deleted_at,p.name AS pole_name,
                pr.name AS project_name FROM cards c JOIN poles p ON p.id=c.pole_id
                JOIN projects pr ON pr.id=p.project_id WHERE c.deleted_at IS NOT NULL
                ORDER BY c.deleted_at DESC""").fetchall()}

    @app.post("/api/admin/cards/{card_id}/restore")
    def restore_card(card_id: int, request: Request, user=Depends(admin)):
        require_request(request)
        with db() as conn:
            row = conn.execute("SELECT * FROM cards WHERE id=%s FOR UPDATE", (card_id,)).fetchone()
            if not row or row["deleted_at"] is None:
                raise HTTPException(404, "Carte introuvable dans la corbeille")
            conn.execute("UPDATE cards SET deleted_at=NULL,updated_at=now() WHERE id=%s", (card_id,))
            record_activity(conn,card_id,user["id"],"card_restored")
        return {"status": "restored"}

    @app.delete("/api/admin/cards/{card_id}")
    def delete_card(card_id: int, request: Request, user=Depends(admin)):
        require_request(request)
        with db() as conn:
            row = conn.execute("SELECT id,deleted_at FROM cards WHERE id=%s FOR UPDATE",
                               (card_id,)).fetchone()
            if not row or row["deleted_at"] is None:
                raise HTTPException(404, "La carte doit être dans la corbeille")
            stored_names = purge_card_files(conn,card_id)
            conn.execute("DELETE FROM cards WHERE id=%s", (card_id,))
        unlink_stored_files(stored_names)
        return {"status": "deleted"}
