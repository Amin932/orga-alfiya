"""Bloc 5 : bibliothèque globale de modèles et checklists indépendantes par carte."""
import json
from datetime import datetime
from typing import Literal

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from psycopg.types.json import Jsonb
from .collaboration_v6 import record_activity


class FormField(BaseModel):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,59}$")
    label: str = Field(min_length=1, max_length=180)
    section: str = Field(min_length=1, max_length=90)
    kind: Literal["text", "longtext", "choice", "yesno", "number", "date", "time"] = "text"
    options: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_options(self):
        if self.kind == "choice" and not self.options:
            raise ValueError("Un champ de sélection doit avoir des options")
        if any(not o.strip() or len(o) > 120 for o in self.options):
            raise ValueError("Option invalide")
        return self


class ChecklistSpec(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    items: list[str] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def clean_items(self):
        if any(not s.strip() or len(s) > 300 for s in self.items):
            raise ValueError("Une tâche doit contenir entre 1 et 300 caractères")
        return self


class TemplateInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    fields: list[FormField] = Field(default_factory=list, max_length=100)
    checklists: list[ChecklistSpec] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_template(self):
        if not self.name.strip():
            raise ValueError("Nom de modèle obligatoire")
        keys = [f.key for f in self.fields]
        if len(set(keys)) != len(keys):
            raise ValueError("Les identifiants des champs doivent être uniques")
        return self


class ValuesUpdate(BaseModel):
    values: dict[str, str | None] = Field(max_length=100)


class ChecklistName(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class ItemText(BaseModel):
    text: str = Field(min_length=1, max_length=300)


class ItemToggle(BaseModel):
    done: bool


def field(key, label, section, kind="text", options=None):
    return dict(key=key, label=label, section=section, kind=kind, options=options or [])


def official_definitions():
    description = [
        field("mail_body", "Corps du mail à envoyer aux étudiants", "Description", "longtext"),
        field("eventbrite_description", "Descriptif sur Eventbrite", "Description", "longtext"),
        field("budget", "Budget (mentionner la trésorerie)", "Description", "text"),
        field("staff", "Effectif nécessaire et répartition des rôles", "Description", "longtext"),
        field("equipment", "Besoins matériels", "Description", "longtext"),
    ]
    info_base = [
        field("event_date", "Date de l'événement", "Infos", "date"),
        field("start_time", "Heure de début", "Infos", "time"),
        field("end_time", "Heure de fin", "Infos", "time"),
        field("event_title", "Titre de l'événement", "Infos", "text"),
        field("audience", "Public", "Infos", "choice", ["Étudiants uniquement", "Ouvert à tous"]),
    ]
    preparation = [
        "Description de la carte complétée",
        "Ajouter les mails des membres à l'événement dans Google Agenda une fois la date validée",
    ]
    post = [
        "Publication post-événement (photo et texte)",
        "Faire la liste des absents",
        "Mail de restriction temporaire de participation si une décision a été prise (envoi manuel)",
        "Témoignage étudiant sur l'intervention",
        "Récapitulatif du taux de présence",
    ]
    with_speaker = {
        "slug": "speaker",
        "name": "Événement avec intervenant",
        "fields": description + [
            field("speaker_program", "Programme à présenter à l'intervenant", "Description", "longtext"),
            field("special_request", "Demande particulière", "Description", "longtext"),
            field("other_speakers", "Autres propositions d'intervenants", "Description", "longtext"),
        ] + info_base + [
            field("speaker", "Intervenant", "Infos"),
            field("venue", "Lieu", "Infos", "choice", ["Présentiel", "Distanciel"]),
            field("zoom", "Diffusion sur Zoom", "Infos", "yesno"),
            field("communication", "Communication souhaitée par l'intervenant", "Infos", "choice",
                  ["Mail étudiants uniquement", "Mail et réseaux sociaux", "Réseaux sociaux uniquement"]),
            field("video", "Accord enregistrement vidéo", "Infos", "yesno"),
            field("audio", "Accord enregistrement audio", "Infos", "yesno"),
            field("photos", "Accord pour prendre des photos", "Infos", "yesno"),
            field("request_details", "Précisions sur la demande particulière", "Infos", "longtext"),
        ],
        "checklists": [
            {"title": "Préparation avant le jour J", "items": preparation},
            {"title": "Post-événement", "items": post},
        ]
    }
    without_speaker = {
        "slug": "no_speaker",
        "name": "Événement sans intervenant",
        "fields": description + info_base,
        "checklists": [
            {"title": "Préparation avant le jour J",
             "items": preparation},
            {"title": "Post-événement", "items": post},
        ]
    }
    return [with_speaker, without_speaker]


def schema_templates(db):
    with db() as conn:
        statements = [
            """CREATE TABLE IF NOT EXISTS templates (
                id BIGSERIAL PRIMARY KEY, slug TEXT UNIQUE, name VARCHAR(120) NOT NULL,
                official BOOLEAN NOT NULL DEFAULT false,
                created_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                fields JSONB NOT NULL DEFAULT '[]'::jsonb,
                checklists JSONB NOT NULL DEFAULT '[]'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )""",
            "ALTER TABLE cards ADD COLUMN IF NOT EXISTS template_id BIGINT REFERENCES templates(id) ON DELETE SET NULL",
            "ALTER TABLE cards ADD COLUMN IF NOT EXISTS template_snapshot JSONB NOT NULL DEFAULT '[]'::jsonb",
            "ALTER TABLE cards ADD COLUMN IF NOT EXISTS template_values JSONB NOT NULL DEFAULT '{}'::jsonb",
            """CREATE TABLE IF NOT EXISTS card_checklists (
                id BIGSERIAL PRIMARY KEY, card_id BIGINT NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
                title VARCHAR(120) NOT NULL, position INT NOT NULL DEFAULT 0
            )""",
            """CREATE TABLE IF NOT EXISTS card_checklist_items (
                id BIGSERIAL PRIMARY KEY,
                checklist_id BIGINT NOT NULL REFERENCES card_checklists(id) ON DELETE CASCADE,
                text VARCHAR(300) NOT NULL, position INT NOT NULL DEFAULT 0,
                done BOOLEAN NOT NULL DEFAULT false,
                done_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
                done_at TIMESTAMPTZ
            )""",
            "CREATE INDEX IF NOT EXISTS card_checklists_card_idx ON card_checklists(card_id,position,id)",
            "CREATE INDEX IF NOT EXISTS card_checklist_items_list_idx ON card_checklist_items(checklist_id,position,id)",
        ]
        for sql in statements:
            conn.execute(sql)
        for definition in official_definitions():
            # Do not overwrite intentional edits to an official template during restarts.
            conn.execute("""INSERT INTO templates(slug,name,official,fields,checklists)
                VALUES (%s,%s,true,%s,%s) ON CONFLICT (slug) DO NOTHING""",
                (definition["slug"], definition["name"], Jsonb(definition["fields"]),
                 Jsonb(definition["checklists"])))
        # Migration ciblée : les tâches Communication n'appartiennent plus aux modèles
        # organisateurs. Ne pas écraser les autres champs/checklists personnalisés.
        com_labels = {
            "Visuel de communication terminé",
            "Eventbrite créé",
            "Eventbrite publié",
            "Mail programmé",
            "Liste des participants du BDE et répartition des rôles prêtes",
        }
        for slug in ("speaker", "no_speaker"):
            template = conn.execute("SELECT id,checklists FROM templates WHERE slug=%s AND official=true",
                                    (slug,)).fetchone()
            if not template:
                continue
            updated = []
            changed = False
            for group in template["checklists"]:
                if group["title"] == "Préparation avant le jour J":
                    filtered = [item for item in group["items"] if item not in com_labels]
                    changed |= len(filtered) != len(group["items"])
                    updated.append({**group, "items": filtered})
                else:
                    updated.append(group)
            if changed:
                conn.execute("""UPDATE templates SET checklists=%s,updated_at=now()
                    WHERE id=%s""", (Jsonb(updated), template["id"]))

        # Les anciennes cartes sont traitées sans toucher aux tâches terminées
        # (qui restent comme preuve du travail effectué) ni aux modèles personnels.
        conn.execute("""DELETE FROM card_checklist_items AS i
            USING card_checklists AS cl, cards AS c, templates AS t
            WHERE i.checklist_id=cl.id AND cl.card_id=c.id
              AND c.template_id=t.id AND t.official=true
              AND t.slug IN ('speaker','no_speaker')
              AND cl.title='Préparation avant le jour J'
              AND i.done=false AND i.done_at IS NULL
              AND i.text=ANY(%s)""", (list(com_labels),))
        # Cards created in block 4 can be populated once, without losing card content.
        for definition in official_definitions():
            template = conn.execute("SELECT * FROM templates WHERE slug=%s", (definition["slug"],)).fetchone()
            existing = conn.execute("""SELECT id FROM cards
                WHERE template_key=%s AND template_id IS NULL ORDER BY id""", (definition["slug"],)).fetchall()
            for card in existing:
                instantiate_template(conn, card["id"], template)


def instantiate_template(conn, card_id, template):
    if not template:
        return
    conn.execute("""UPDATE cards SET template_id=%s,template_snapshot=%s,template_values=%s
        WHERE id=%s""", (template["id"], Jsonb(template["fields"]), Jsonb({}), card_id))
    for pos, spec in enumerate(template["checklists"]):
        record = conn.execute("""INSERT INTO card_checklists(card_id,title,position)
            VALUES (%s,%s,%s) RETURNING id""", (card_id, spec["title"], pos)).fetchone()
        for order, label in enumerate(spec["items"]):
            conn.execute("""INSERT INTO card_checklist_items(checklist_id,text,position)
                VALUES (%s,%s,%s)""", (record["id"], label, order))


def card_template_content(conn, card_id):
    row = conn.execute("""SELECT template_id,template_snapshot,template_values
        FROM cards WHERE id=%s""", (card_id,)).fetchone()
    lists = conn.execute("""SELECT id,title,position FROM card_checklists
        WHERE card_id=%s ORDER BY position,id""", (card_id,)).fetchall()
    for group in lists:
        group["items"] = conn.execute("""SELECT i.id,i.text,i.position,i.done,i.done_at,
            i.done_by,u.first_name AS done_by_name FROM card_checklist_items i
            LEFT JOIN users u ON u.id=i.done_by
            WHERE i.checklist_id=%s ORDER BY i.position,i.id""", (group["id"],)).fetchall()
    return {"template_id": row["template_id"], "fields": row["template_snapshot"],
            "values": row["template_values"], "checklists": lists}


def register_template_routes(app, db, current_user, admin, require_request):
    def template_rights(template, user):
        if template["official"] and user["role"] != "superadmin":
            raise HTTPException(403, "Modèle officiel réservé au super-administrateur")
        if not template["official"] and user["role"] != "superadmin" and template["created_by"] != user["id"]:
            raise HTTPException(403, "Seul le créateur peut modifier ce modèle")

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

    def get_list(conn, card_id, list_id, user):
        get_card(conn, card_id, user)
        result = conn.execute("""SELECT id FROM card_checklists WHERE id=%s AND card_id=%s""",
                              (list_id, card_id)).fetchone()
        if not result:
            raise HTTPException(404, "Checklist introuvable")
        return result

    @app.get("/api/templates")
    def list_templates(user=Depends(current_user)):
        with db() as conn:
            return {"templates": conn.execute("""SELECT id,slug,name,official,created_by,fields,checklists
                FROM templates ORDER BY official DESC,name,id""").fetchall()}

    @app.post("/api/templates", status_code=201)
    def create_template(body: TemplateInput, request: Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            return conn.execute("""INSERT INTO templates(name,created_by,fields,checklists)
                VALUES (%s,%s,%s,%s)
                RETURNING id,slug,name,official,created_by,fields,checklists""",
                (body.name.strip(),user["id"],Jsonb([x.model_dump() for x in body.fields]),
                 Jsonb([x.model_dump() for x in body.checklists]))).fetchone()

    @app.put("/api/templates/{template_id}")
    def update_template(template_id: int, body: TemplateInput, request: Request,
                        user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            row = conn.execute("SELECT * FROM templates WHERE id=%s FOR UPDATE",
                               (template_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Modèle introuvable")
            template_rights(row, user)
            return conn.execute("""UPDATE templates SET name=%s,fields=%s,checklists=%s,updated_at=now()
                WHERE id=%s RETURNING id,slug,name,official,created_by,fields,checklists""",
                (body.name.strip(),Jsonb([x.model_dump() for x in body.fields]),
                 Jsonb([x.model_dump() for x in body.checklists]),template_id)).fetchone()

    @app.delete("/api/templates/{template_id}")
    def delete_template(template_id: int, request: Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            row = conn.execute("SELECT * FROM templates WHERE id=%s FOR UPDATE",
                               (template_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Modèle introuvable")
            template_rights(row, user)
            if row["official"]:
                raise HTTPException(403, "Les deux modèles officiels doivent rester disponibles")
            conn.execute("DELETE FROM templates WHERE id=%s", (template_id,))
        return {"status": "deleted"}

    @app.get("/api/cards/{card_id}/template-content")
    def get_content(card_id: int, user=Depends(current_user)):
        with db() as conn:
            get_card(conn,card_id,user)
            return card_template_content(conn,card_id)

    @app.patch("/api/cards/{card_id}/template-values")
    def update_values(card_id: int, body: ValuesUpdate, request: Request,
                      user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_card(conn,card_id,user)
            row = conn.execute("SELECT template_snapshot,template_values FROM cards WHERE id=%s FOR UPDATE",
                               (card_id,)).fetchone()
            valid = {f["key"]: f for f in row["template_snapshot"]}
            values = dict(row["template_values"])
            for key, value in body.values.items():
                if key not in valid:
                    raise HTTPException(422, "Champ non reconnu")
                if value is not None:
                    if not isinstance(value,str) or len(value) > 20000:
                        raise HTTPException(422, "Valeur invalide")
                    kind = valid[key]["kind"]
                    if kind == "yesno" and value not in ("","Oui","Non"):
                        raise HTTPException(422, "Choix invalide")
                    if kind == "choice" and value not in ("",*valid[key]["options"]):
                        raise HTTPException(422, "Choix invalide")
                    if kind == "date" and value:
                        try:
                            datetime.strptime(value,"%Y-%m-%d")
                        except ValueError:
                            raise HTTPException(422, "Date invalide") from None
                    if kind == "time" and value:
                        try:
                            datetime.strptime(value,"%H:%M")
                        except ValueError:
                            raise HTTPException(422, "Heure invalide") from None
                    if kind == "number" and value:
                        try:
                            float(value)
                        except ValueError:
                            raise HTTPException(422, "Nombre invalide") from None
                values[key] = value or ""
            conn.execute("UPDATE cards SET template_values=%s,updated_at=now() WHERE id=%s",
                         (Jsonb(values),card_id))
            record_activity(conn,card_id,user["id"],"template_updated",{"fields":sorted(body.values.keys())})
            return {"values": values}

    @app.post("/api/cards/{card_id}/checklists", status_code=201)
    def new_checklist(card_id: int, body: ChecklistName, request: Request,
                      user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_card(conn,card_id,user)
            position = conn.execute("""SELECT COALESCE(MAX(position),-1)+1 AS n
                FROM card_checklists WHERE card_id=%s""",(card_id,)).fetchone()["n"]
            row=conn.execute("""INSERT INTO card_checklists(card_id,title,position)
                VALUES (%s,%s,%s) RETURNING id,title,position""",
                (card_id,body.title.strip(),position)).fetchone()
            record_activity(conn,card_id,user["id"],"checklist_created",{"list_id":row["id"]})
            return row

    @app.post("/api/cards/{card_id}/checklists/{list_id}/items", status_code=201)
    def new_item(card_id: int, list_id: int, body: ItemText, request: Request,
                 user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_list(conn,card_id,list_id,user)
            position = conn.execute("""SELECT COALESCE(MAX(position),-1)+1 AS n
                FROM card_checklist_items WHERE checklist_id=%s""",(list_id,)).fetchone()["n"]
            row=conn.execute("""INSERT INTO card_checklist_items(checklist_id,text,position)
                VALUES (%s,%s,%s) RETURNING id,text,position,done""",
                (list_id,body.text.strip(),position)).fetchone()
            record_activity(conn,card_id,user["id"],"checklist_item_added",{"item_id":row["id"]})
            return row

    @app.patch("/api/cards/{card_id}/checklists/{list_id}")
    def rename_list(card_id: int, list_id: int, body: ChecklistName, request: Request,
                    user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_list(conn,card_id,list_id,user)
            conn.execute("UPDATE card_checklists SET title=%s WHERE id=%s",
                         (body.title.strip(),list_id))
            record_activity(conn,card_id,user["id"],"checklist_renamed",{"list_id":list_id})
        return {"status":"updated"}

    @app.delete("/api/cards/{card_id}/checklists/{list_id}")
    def delete_list(card_id: int, list_id: int, request: Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_list(conn,card_id,list_id,user)
            conn.execute("DELETE FROM card_checklists WHERE id=%s", (list_id,))
            record_activity(conn,card_id,user["id"],"checklist_deleted",{"list_id":list_id})
        return {"status":"deleted"}

    @app.patch("/api/cards/{card_id}/checklists/{list_id}/items/{item_id}")
    def update_item(card_id: int, list_id: int, item_id: int, body: ItemText,
                    request: Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_list(conn,card_id,list_id,user)
            row = conn.execute("""UPDATE card_checklist_items SET text=%s
                WHERE id=%s AND checklist_id=%s RETURNING id""",
                (body.text.strip(),item_id,list_id)).fetchone()
            if not row:
                raise HTTPException(404, "Tâche introuvable")
            record_activity(conn,card_id,user["id"],"checklist_item_updated",{"item_id":item_id})
        return {"status":"updated"}

    @app.patch("/api/cards/{card_id}/checklists/{list_id}/items/{item_id}/done")
    def mark_item(card_id: int, list_id: int, item_id: int, body: ItemToggle,
                  request: Request, user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_list(conn,card_id,list_id,user)
            row = conn.execute("""UPDATE card_checklist_items SET done=%s,
                done_by=%s,done_at=CASE WHEN %s THEN now() ELSE NULL END
                WHERE id=%s AND checklist_id=%s RETURNING id,done,done_at""",
                (body.done,user["id"] if body.done else None,body.done,item_id,list_id)).fetchone()
            if not row:
                raise HTTPException(404, "Tâche introuvable")
            record_activity(conn,card_id,user["id"],"checklist_checked",{"item_id":item_id,"done":body.done})
            return row

    @app.delete("/api/cards/{card_id}/checklists/{list_id}/items/{item_id}")
    def delete_item(card_id: int, list_id: int, item_id: int, request: Request,
                    user=Depends(current_user)):
        require_request(request)
        with db() as conn:
            get_list(conn,card_id,list_id,user)
            deleted = conn.execute("""DELETE FROM card_checklist_items
                WHERE id=%s AND checklist_id=%s RETURNING id""",(item_id,list_id)).fetchone()
            if not deleted:
                raise HTTPException(404, "Tâche introuvable")
            record_activity(conn,card_id,user["id"],"checklist_item_deleted",{"item_id":item_id})
        return {"status":"deleted"}
