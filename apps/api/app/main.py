"""Orga Alfiya – comptes sur invitation, liens de connexion et droits par projet."""
import hashlib
import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from pydantic import BaseModel, Field

DATABASE_URL = os.environ.get('DATABASE_URL', '')
PUBLIC_URL = os.environ.get('ORGA_PUBLIC_URL', 'https://orga-alfiya.amvei.synology.me').rstrip('/')
SECURE_COOKIE = os.environ.get('COOKIE_SECURE', 'true').lower() == 'true'
SESSION_DAYS = 90
app = FastAPI(title='Orga Alfiya API', version='0.2.0', docs_url=None, redoc_url=None, openapi_url=None)


def now():
    return datetime.now(timezone.utc)


def db():
    return psycopg.connect(DATABASE_URL, row_factory=dict_row, connect_timeout=5)


def digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def clean_email(value):
    value = value.strip().lower()
    if len(value) > 254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
        raise HTTPException(422, 'Adresse e-mail invalide')
    return value


def require_request(request: Request):
    """Évite les POST cross-origin et formulaires CSRF, y compris sur sous-domaines."""
    if request.headers.get('x-orga-request') != '1':
        raise HTTPException(403, 'Requête non autorisée')
    origin = request.headers.get('origin')
    if origin:
        expected = urlsplit(PUBLIC_URL)
        actual = urlsplit(origin)
        if (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc):
            raise HTTPException(403, 'Origine non autorisée')


class EmailInput(BaseModel):
    email: str


class TokenInput(BaseModel):
    token: str = Field(min_length=20, max_length=256)


class ActivationInput(TokenInput):
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    pole_id: int | None = None


class InviteInput(EmailInput):
    project_ids: list[int] = Field(default_factory=list, max_length=100)


class ProjectInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str = Field(default='', max_length=500)


class PoleInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    color: str = Field(pattern=r'^#[0-9a-fA-F]{6}$')
    description: str = Field(default='', max_length=500)


class AccessInput(BaseModel):
    project_ids: list[int] = Field(default_factory=list, max_length=100)


def mail(to, subject, body):
    host, user, password, sender = (os.getenv(x, '') for x in ('SMTP_HOST', 'SMTP_USERNAME', 'SMTP_PASSWORD', 'SMTP_FROM'))
    port = int(os.getenv('SMTP_PORT', '465'))
    if not all((host, user, password, sender)) or port not in (465, 587):
        raise RuntimeError('SMTP non configuré (465 SSL ou 587 STARTTLS)')
    msg = EmailMessage()
    msg['From'], msg['To'], msg['Subject'] = sender, to, subject
    msg.set_content(body)
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=15, context=ssl.create_default_context()) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=15) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.login(user, password)
            smtp.send_message(msg)


def schema():
    with db() as conn:
        for statement in [
            """CREATE TABLE IF NOT EXISTS users (
                id BIGSERIAL PRIMARY KEY, email TEXT NOT NULL UNIQUE,
                first_name TEXT NOT NULL DEFAULT '', last_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('member','superadmin')),
                active BOOLEAN NOT NULL DEFAULT false, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS projects (
                id BIGSERIAL PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS poles (
                id BIGSERIAL PRIMARY KEY, project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                name TEXT NOT NULL, color TEXT NOT NULL, description TEXT NOT NULL DEFAULT '')""",
            """CREATE TABLE IF NOT EXISTS project_access (
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                PRIMARY KEY(user_id,project_id))""",
            """CREATE TABLE IF NOT EXISTS user_poles (
                user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                pole_id BIGINT NOT NULL REFERENCES poles(id) ON DELETE CASCADE,
                position INT NOT NULL, PRIMARY KEY(user_id,pole_id))""",
            """CREATE TABLE IF NOT EXISTS auth_tokens (
                token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                purpose TEXT NOT NULL CHECK (purpose IN ('invite','login')),
                expires_at TIMESTAMPTZ NOT NULL, used_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY, user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at TIMESTAMPTZ NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
            """CREATE TABLE IF NOT EXISTS login_requests (
                id BIGSERIAL PRIMARY KEY, email TEXT NOT NULL, ip_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT now())""",
            "CREATE INDEX IF NOT EXISTS login_requests_created_idx ON login_requests(created_at)",
            "CREATE INDEX IF NOT EXISTS auth_tokens_user_idx ON auth_tokens(user_id)",
            "CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id)",
        ]:
            conn.execute(statement)
        admin_email = os.getenv('SUPERADMIN_EMAIL', '').strip()
        if admin_email:
            admin_email = clean_email(admin_email)
            existing = conn.execute("SELECT 1 FROM users WHERE role='superadmin' LIMIT 1").fetchone()
            if not existing:
                conn.execute("""INSERT INTO users (email, first_name, role, active)
                    VALUES (%s,'Administrateur','superadmin',true)
                    ON CONFLICT (email) DO UPDATE SET role='superadmin', active=true""", (admin_email,))


@app.on_event('startup')
def startup():
    if not DATABASE_URL:
        raise RuntimeError('DATABASE_URL requis')
    if not SECURE_COOKIE and os.getenv('ALLOW_INSECURE_LOCAL', '') != 'yes':
        raise RuntimeError('COOKIE_SECURE=false autorisé uniquement avec ALLOW_INSECURE_LOCAL=yes')
    schema()


@app.get('/api/health')
def health():
    return {'status': 'ok', 'service': 'orga-alfiya-api'}


@app.get('/api/health/database')
def health_database():
    try:
        with db() as conn:
            conn.execute('SELECT 1')
    except psycopg.Error:
        raise HTTPException(503, 'Base de données indisponible') from None
    return {'status': 'ok', 'database': 'connected'}


def current_user(request: Request):
    cookie = request.cookies.get('orga_session', '')
    if not cookie or len(cookie) > 256:
        raise HTTPException(401, 'Connexion nécessaire')
    with db() as conn:
        user = conn.execute("""SELECT u.id, u.email, u.first_name, u.last_name, u.role
            FROM sessions s JOIN users u ON u.id=s.user_id
            WHERE s.token_hash=%s AND s.expires_at>now() AND u.active=true""", (digest(cookie),)).fetchone()
    if not user:
        raise HTTPException(401, 'Session expirée')
    return user


def admin(user=Depends(current_user)):
    if user['role'] != 'superadmin':
        raise HTTPException(403, 'Accès réservé à la super-administration')
    return user


def set_session(conn, response, user_id):
    secret = secrets.token_urlsafe(48)
    conn.execute('INSERT INTO sessions(token_hash,user_id,expires_at) VALUES (%s,%s,%s)',
                 (digest(secret), user_id, now() + timedelta(days=SESSION_DAYS)))
    response.set_cookie('orga_session', secret, max_age=SESSION_DAYS * 86400,
                        httponly=True, secure=SECURE_COOKIE, samesite='lax', path='/')


def visible_projects(conn, user):
    if user['role'] == 'superadmin':
        return conn.execute('SELECT id,name,description FROM projects ORDER BY id').fetchall()
    return conn.execute("""SELECT p.id,p.name,p.description FROM projects p
        JOIN project_access pa ON pa.project_id=p.id WHERE pa.user_id=%s ORDER BY p.id""", (user['id'],)).fetchall()


@app.get('/api/auth/me')
def me(user=Depends(current_user)):
    with db() as conn:
        projects = visible_projects(conn, user)
        poles = conn.execute("""SELECT p.id,p.name,p.color,p.project_id,p.description FROM poles p
            JOIN user_poles up ON up.pole_id=p.id WHERE up.user_id=%s ORDER BY up.position,p.id""", (user['id'],)).fetchall()
    return {'user': user, 'projects': projects, 'poles': poles}


@app.post('/api/auth/request-link')
def request_link(body: EmailInput, request: Request):
    require_request(request)
    email = clean_email(body.email)
    ip = (request.headers.get('x-real-ip') or (request.client.host if request.client else ''))[:120]
    ip_hash = digest(ip)
    # Réponse identique pour adresses connues et inconnues; limitation par adresse et IP.
    with db() as conn:
        by_email = conn.execute("SELECT 1 FROM login_requests WHERE email=%s AND created_at>now()-interval '3 minutes'", (email,)).fetchone()
        by_ip = conn.execute("SELECT count(*) AS count FROM login_requests WHERE ip_hash=%s AND created_at>now()-interval '1 hour'", (ip_hash,)).fetchone()
        if by_email or by_ip['count'] >= 8:
            return {'message': 'Si ce compte existe, un lien de connexion sera envoyé.'}
        conn.execute('INSERT INTO login_requests(email,ip_hash) VALUES (%s,%s)', (email, ip_hash))
        user = conn.execute('SELECT id FROM users WHERE email=%s AND active=true', (email,)).fetchone()
        if user:
            secret = secrets.token_urlsafe(40)
            conn.execute("DELETE FROM auth_tokens WHERE user_id=%s AND purpose='login'", (user['id'],))
            conn.execute("INSERT INTO auth_tokens(token_hash,user_id,purpose,expires_at) VALUES (%s,%s,'login',%s)",
                         (digest(secret), user['id'], now() + timedelta(minutes=20)))
    if user:
        try:
            mail(email, 'Votre lien de connexion Orga Alfiya',
                 f'Voici votre lien personnel, valable 20 minutes et utilisable une fois :\n\n{PUBLIC_URL}/#login={secret}\n\nSi vous ne l\'avez pas demandé, ignorez ce message.')
        except Exception:
            # Ne pas exposer la configuration SMTP ni l'existence du compte.
            import logging
            logging.getLogger('orga.auth').exception('Échec SMTP connexion')
    return {'message': 'Si ce compte existe, un lien de connexion sera envoyé.'}


@app.post('/api/auth/login')
def login(body: TokenInput, request: Request, response: Response):
    require_request(request)
    with db() as conn:
        row = conn.execute("""SELECT a.user_id FROM auth_tokens a JOIN users u ON u.id=a.user_id
            WHERE a.token_hash=%s AND a.purpose='login' AND a.expires_at>now()
              AND a.used_at IS NULL AND u.active=true FOR UPDATE OF a""", (digest(body.token),)).fetchone()
        if not row:
            raise HTTPException(400, 'Lien invalide ou expiré')
        conn.execute('UPDATE auth_tokens SET used_at=now() WHERE token_hash=%s', (digest(body.token),))
        set_session(conn, response, row['user_id'])
    return {'status': 'connected'}


@app.post('/api/auth/logout')
def logout(request: Request, response: Response):
    require_request(request)
    cookie = request.cookies.get('orga_session', '')
    if cookie:
        with db() as conn:
            conn.execute('DELETE FROM sessions WHERE token_hash=%s', (digest(cookie),))
    response.delete_cookie('orga_session', path='/', secure=SECURE_COOKIE, samesite='lax')
    return {'status': 'disconnected'}


@app.post('/api/auth/invitation')
def invitation(body: TokenInput, request: Request):
    require_request(request)
    with db() as conn:
        user = conn.execute("""SELECT u.id,u.email FROM auth_tokens a JOIN users u ON u.id=a.user_id
            WHERE a.token_hash=%s AND a.purpose='invite' AND a.used_at IS NULL
            AND a.expires_at>now() AND u.active=false""", (digest(body.token),)).fetchone()
        if not user:
            raise HTTPException(400, 'Invitation invalide ou expirée')
        poles = conn.execute("""SELECT po.id,po.name,po.color,pr.name AS project FROM poles po
            JOIN projects pr ON pr.id=po.project_id
            JOIN project_access pa ON pa.project_id=pr.id
            WHERE pa.user_id=%s ORDER BY pr.id,po.id""", (user['id'],)).fetchall()
    return {'email': user['email'], 'poles': poles}


@app.post('/api/auth/activate')
def activate(body: ActivationInput, request: Request, response: Response):
    require_request(request)
    first, last = body.first_name.strip(), body.last_name.strip()
    if not first or not last:
        raise HTTPException(422, 'Nom et prénom requis')
    with db() as conn:
        row = conn.execute("""SELECT a.user_id FROM auth_tokens a JOIN users u ON u.id=a.user_id
            WHERE a.token_hash=%s AND a.purpose='invite' AND a.expires_at>now()
              AND a.used_at IS NULL AND u.active=false FOR UPDATE OF a""", (digest(body.token),)).fetchone()
        if not row:
            raise HTTPException(400, 'Invitation invalide ou expirée')
        poles = conn.execute("""SELECT po.id FROM poles po JOIN project_access pa
            ON pa.project_id=po.project_id WHERE pa.user_id=%s""", (row['user_id'],)).fetchall()
        choices = {p['id'] for p in poles}
        if choices and body.pole_id not in choices:
            raise HTTPException(422, 'Sélectionnez un pôle autorisé')
        if body.pole_id is not None and body.pole_id not in choices:
            raise HTTPException(422, 'Pôle non autorisé')
        conn.execute('UPDATE users SET first_name=%s,last_name=%s,active=true WHERE id=%s',
                     (first, last, row['user_id']))
        if body.pole_id:
            conn.execute('INSERT INTO user_poles(user_id,pole_id,position) VALUES (%s,%s,1)',
                         (row['user_id'], body.pole_id))
        conn.execute('UPDATE auth_tokens SET used_at=now() WHERE token_hash=%s', (digest(body.token),))
        set_session(conn, response, row['user_id'])
    return {'status': 'activated'}


@app.get('/api/workspace')
def workspace(user=Depends(current_user)):
    with db() as conn:
        projects = visible_projects(conn, user)
        ids = [p['id'] for p in projects]
        poles = conn.execute('SELECT id,project_id,name,color,description FROM poles WHERE project_id=ANY(%s) ORDER BY id', (ids,)).fetchall() if ids else []
    return {'projects': [{**p, 'poles': [po for po in poles if po['project_id'] == p['id']]} for p in projects]}


@app.get('/api/admin/users')
def users(user=Depends(admin)):
    with db() as conn:
        return conn.execute('SELECT id,email,first_name,last_name,role,active FROM users ORDER BY id').fetchall()


@app.post('/api/admin/projects', status_code=201)
def create_project(body: ProjectInput, request: Request, user=Depends(admin)):
    require_request(request)
    with db() as conn:
        return conn.execute('INSERT INTO projects(name,description) VALUES (%s,%s) RETURNING id,name,description',
                            (body.name.strip(), body.description.strip())).fetchone()


@app.post('/api/admin/projects/{project_id}/poles', status_code=201)
def create_pole(project_id: int, body: PoleInput, request: Request, user=Depends(admin)):
    require_request(request)
    with db() as conn:
        if not conn.execute('SELECT 1 FROM projects WHERE id=%s', (project_id,)).fetchone():
            raise HTTPException(404, 'Projet introuvable')
        return conn.execute("""INSERT INTO poles(project_id,name,color,description)
            VALUES (%s,%s,%s,%s) RETURNING id,project_id,name,color,description""",
            (project_id, body.name.strip(), body.color.upper(), body.description.strip())).fetchone()


@app.post('/api/admin/invitations', status_code=201)
def invite(body: InviteInput, request: Request, user=Depends(admin)):
    require_request(request)
    email = clean_email(body.email)
    project_ids = list(set(body.project_ids))
    with db() as conn:
        valid_ids = conn.execute('SELECT id FROM projects WHERE id=ANY(%s)', (project_ids,)).fetchall() if project_ids else []
        if {x['id'] for x in valid_ids} != set(project_ids):
            raise HTTPException(422, 'Projet inconnu')
        member = conn.execute('SELECT id,active FROM users WHERE email=%s FOR UPDATE', (email,)).fetchone()
        if member and member['active']:
            raise HTTPException(409, 'Ce membre possède déjà un compte actif')
        if not member:
            member = conn.execute("INSERT INTO users(email) VALUES (%s) RETURNING id,active", (email,)).fetchone()
        conn.execute('DELETE FROM project_access WHERE user_id=%s', (member['id'],))
        for project_id in project_ids:
            conn.execute('INSERT INTO project_access(user_id,project_id) VALUES (%s,%s)', (member['id'], project_id))
        conn.execute("DELETE FROM auth_tokens WHERE user_id=%s AND purpose='invite'", (member['id'],))
        secret = secrets.token_urlsafe(40)
        conn.execute("INSERT INTO auth_tokens(token_hash,user_id,purpose,expires_at) VALUES (%s,%s,'invite',%s)",
                     (digest(secret), member['id'], now() + timedelta(days=7)))
        # En cas d'échec SMTP la transaction est annulée ; aucun lien perdu en base.
        try:
            mail(email, 'Invitation à rejoindre Orga Alfiya',
                 f'Vous êtes invité(e) à rejoindre Orga Alfiya. Activez votre compte dans les 7 jours :\n\n{PUBLIC_URL}/#invite={secret}\n\nCe lien est personnel et à usage unique.')
        except Exception:
            raise HTTPException(503, 'Envoi impossible : vérifiez la configuration SMTP') from None
    return {'message': 'Invitation envoyée'}


@app.post('/api/admin/users/{user_id}/access')
def update_access(user_id: int, body: AccessInput, request: Request, user=Depends(admin)):
    require_request(request)
    project_ids = list(set(body.project_ids))
    with db() as conn:
        target = conn.execute('SELECT id FROM users WHERE id=%s', (user_id,)).fetchone()
        if not target:
            raise HTTPException(404, 'Membre introuvable')
        found = conn.execute('SELECT id FROM projects WHERE id=ANY(%s)', (project_ids,)).fetchall() if project_ids else []
        if {x['id'] for x in found} != set(project_ids):
            raise HTTPException(422, 'Projet inconnu')
        conn.execute('DELETE FROM project_access WHERE user_id=%s', (user_id,))
        for p in project_ids:
            conn.execute('INSERT INTO project_access(user_id,project_id) VALUES (%s,%s)', (user_id,p))
        conn.execute('DELETE FROM user_poles WHERE user_id=%s AND pole_id NOT IN (SELECT id FROM poles WHERE project_id=ANY(%s))', (user_id, project_ids))
    return {'status': 'updated'}


@app.post('/api/admin/users/{user_id}/disable')
def disable_user(user_id: int, request: Request, user=Depends(admin)):
    require_request(request)
    if user_id == user['id']:
        raise HTTPException(400, 'Impossible de désactiver son propre compte')
    with db() as conn:
        row = conn.execute('SELECT role FROM users WHERE id=%s', (user_id,)).fetchone()
        if not row or row['role'] == 'superadmin':
            raise HTTPException(400, 'Compte introuvable ou protégé')
        conn.execute('UPDATE users SET active=false WHERE id=%s', (user_id,))
        conn.execute('DELETE FROM sessions WHERE user_id=%s', (user_id,))
        conn.execute('DELETE FROM auth_tokens WHERE user_id=%s', (user_id,))
    return {'status': 'disabled'}
