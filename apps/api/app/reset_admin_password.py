"""Réinitialiser le mot de passe du super-admin localement via le terminal du NAS.

sudo docker compose exec api python -m app.reset_admin_password
Aucun mot de passe affiché ni envoyé par mail.
"""
import getpass
import sys
from .main import db, PASSWORD_HASHER


def main():
    if not sys.stdin.isatty():
        raise SystemExit("Un terminal interactif est nécessaire.")
    with db() as conn:
        admin = conn.execute("SELECT id,email FROM users WHERE role='superadmin' LIMIT 1").fetchone()
    if not admin:
        raise SystemExit("Super-administrateur introuvable.")
    print("Réinitialisation locale du mot de passe super-administrateur.")
    print("Utilisateur :", admin["email"])
    first=getpass.getpass("Nouveau mot de passe (minimum 16 caractères) : ")
    again=getpass.getpass("Confirmer : ")
    if len(first)<16 or len(first)>128 or first!=again:
        raise SystemExit("Mot de passe trop court, trop long ou confirmation différente.")
    with db() as conn:
        conn.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                     (PASSWORD_HASHER.hash(first),admin["id"]))
        conn.execute("DELETE FROM sessions WHERE user_id=%s",(admin["id"],))
        conn.execute("DELETE FROM auth_tokens WHERE user_id=%s",(admin["id"],))
    print("Mot de passe réinitialisé et sessions révoquées.")


if __name__=="__main__":
    main()
