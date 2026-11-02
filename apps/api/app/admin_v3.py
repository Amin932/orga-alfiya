"""Gestion administrative des pôles, membres et projets – bloc 3.

Les autorisations sont appliquées côté serveur. Un pôle est une appartenance
visuelle/organisationnelle; seul project_access ouvre l'accès à un projet.
"""
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field
from psycopg.errors import ForeignKeyViolation


class MembershipInput(BaseModel):
    pole_ids: list[int] = Field(default_factory=list, max_length=100)


class ProjectEdit(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default="", max_length=500)


class PoleEdit(ProjectEdit):
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class ConfirmDelete(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def clean_name(value: str) -> str:
    value = value.strip()
    if len(value) < 2:
        raise HTTPException(422, "Nom trop court")
    return value


def register_admin_routes(app, db, require_request, admin):
    """Routes réservées au compte super-administrateur."""

    @app.get("/api/admin/directory")
    def directory(_user=Depends(admin)):
        with db() as conn:
            users = conn.execute("""SELECT id,email,first_name,last_name,role,active
                FROM users ORDER BY lower(first_name),lower(last_name),id""").fetchall()
            access = conn.execute("SELECT user_id,project_id FROM project_access ORDER BY project_id").fetchall()
            poles = conn.execute("""SELECT up.user_id,up.pole_id,up.position,p.name,p.color,p.project_id
                FROM user_poles up JOIN poles p ON p.id=up.pole_id
                ORDER BY up.user_id,up.position,up.pole_id""").fetchall()
        return [
            {**u, "state": ("active" if u["active"] else ("disabled" if u["first_name"] else "pending")),
             "project_ids": [a["project_id"] for a in access if a["user_id"] == u["id"]],
             "poles": [{k: p[k] for k in ("pole_id","position","name","color","project_id")}
                       for p in poles if p["user_id"] == u["id"]]}
            for u in users
        ]

    @app.post("/api/admin/users/{user_id}/poles")
    def set_member_poles(user_id: int, body: MembershipInput, request: Request,
                         _user=Depends(admin)):
        require_request(request)
        pole_ids = body.pole_ids
        if len(pole_ids) != len(set(pole_ids)):
            raise HTTPException(422, "Un même pôle ne peut apparaître deux fois")
        with db() as conn:
            target = conn.execute("SELECT role,active FROM users WHERE id=%s FOR UPDATE",
                                  (user_id,)).fetchone()
            if not target:
                raise HTTPException(404, "Membre introuvable")
            if target["role"] == "superadmin" and user_id != _user["id"]:
                raise HTTPException(403, "Seul le super-administrateur concerné peut choisir ses pôles")
            if not target["active"]:
                raise HTTPException(409, "Le membre doit d'abord activer son compte")
            if target["role"] == "superadmin":
                rows = conn.execute("SELECT id FROM poles WHERE id=ANY(%s)",
                                    (pole_ids,)).fetchall() if pole_ids else []
            else:
                rows = conn.execute("""SELECT p.id FROM poles p JOIN project_access pa
                    ON pa.project_id=p.project_id
                    WHERE pa.user_id=%s AND p.id=ANY(%s)""", (user_id, pole_ids)).fetchall() if pole_ids else []
            if {r["id"] for r in rows} != set(pole_ids):
                raise HTTPException(422, "Pôle absent ou projet non autorisé")
            conn.execute("DELETE FROM user_poles WHERE user_id=%s", (user_id,))
            for position, pole_id in enumerate(pole_ids, start=1):
                conn.execute("""INSERT INTO user_poles (user_id,pole_id,position)
                    VALUES (%s,%s,%s)""", (user_id, pole_id, position))
        return {"status": "updated", "primary_pole_id": pole_ids[0] if pole_ids else None}

    @app.post("/api/admin/users/{user_id}/enable")
    def enable_member(user_id: int, request: Request, _user=Depends(admin)):
        require_request(request)
        with db() as conn:
            target = conn.execute("SELECT role,first_name FROM users WHERE id=%s FOR UPDATE",
                                  (user_id,)).fetchone()
            if not target:
                raise HTTPException(404, "Membre introuvable")
            if target["role"] == "superadmin":
                raise HTTPException(403, "Compte super-administrateur protégé")
            if not target["first_name"]:
                raise HTTPException(409, "Compte non activé : renvoyer une invitation")
            conn.execute("UPDATE users SET active=true WHERE id=%s", (user_id,))
        return {"status": "enabled"}

    @app.post("/api/admin/projects/{project_id}/edit")
    def edit_project(project_id: int, body: ProjectEdit, request: Request,
                     _user=Depends(admin)):
        require_request(request)
        with db() as conn:
            row = conn.execute("""UPDATE projects SET name=%s,description=%s
                WHERE id=%s RETURNING id,name,description""",
                (clean_name(body.name), body.description.strip(), project_id)).fetchone()
            if not row:
                raise HTTPException(404, "Projet introuvable")
        return row

    @app.post("/api/admin/projects/{project_id}/delete")
    def delete_project(project_id: int, body: ConfirmDelete, request: Request,
                       _user=Depends(admin)):
        require_request(request)
        with db() as conn:
            row = conn.execute("SELECT name FROM projects WHERE id=%s FOR UPDATE",
                               (project_id,)).fetchone()
            if not row:
                raise HTTPException(404, "Projet introuvable")
            if body.name != row["name"]:
                raise HTTPException(422, "Confirmez le nom exact du projet")
            if conn.execute("SELECT 1 FROM poles WHERE project_id=%s LIMIT 1",
                            (project_id,)).fetchone():
                raise HTTPException(409, "Supprimez d'abord les pôles du projet")
            try:
                conn.execute("DELETE FROM projects WHERE id=%s", (project_id,))
            except ForeignKeyViolation:
                raise HTTPException(409, "Ce projet contient encore des données liées") from None
        return {"status": "deleted"}

    @app.post("/api/admin/projects/{project_id}/poles/{pole_id}/edit")
    def edit_pole(project_id: int, pole_id: int, body: PoleEdit, request: Request,
                  _user=Depends(admin)):
        require_request(request)
        with db() as conn:
            row = conn.execute("""UPDATE poles SET name=%s,color=%s,description=%s
                WHERE id=%s AND project_id=%s
                RETURNING id,project_id,name,color,description""",
                (clean_name(body.name), body.color.upper(), body.description.strip(),
                 pole_id, project_id)).fetchone()
            if not row:
                raise HTTPException(404, "Pôle introuvable dans ce projet")
        return row

    @app.post("/api/admin/projects/{project_id}/poles/{pole_id}/delete")
    def delete_pole(project_id: int, pole_id: int, body: ConfirmDelete,
                    request: Request, _user=Depends(admin)):
        require_request(request)
        with db() as conn:
            row = conn.execute("""SELECT name FROM poles WHERE id=%s AND project_id=%s
                FOR UPDATE""", (pole_id, project_id)).fetchone()
            if not row:
                raise HTTPException(404, "Pôle introuvable dans ce projet")
            if row["name"] != body.name:
                raise HTTPException(422, "Confirmez le nom exact du pôle")
            # Empêcher toute suppression en cascade de cartes et de pièces jointes.
            if conn.execute("SELECT 1 FROM cards WHERE pole_id=%s LIMIT 1",
                            (pole_id,)).fetchone():
                raise HTTPException(409, "Ce pôle contient encore des cartes, y compris dans la corbeille")
            # Les appartenances des membres sont supprimées, pas leurs accès aux projets.
            try:
                conn.execute("DELETE FROM poles WHERE id=%s AND project_id=%s",
                             (pole_id, project_id))
            except ForeignKeyViolation:
                raise HTTPException(409, "Le pôle contient encore des données liées") from None
        return {"status": "deleted"}
