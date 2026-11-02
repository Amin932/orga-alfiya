# Orga Alfiya

Application de gestion des projets, pôles, événements et missions du BDE de l'Institut Alfiya.

> **Bloc 1 – socle technique.** L'interface présente uniquement des données **de démonstration**, sans sauvegarde des cartes ni authentification. Ne pas l'utiliser comme outil collaboratif en production avant la mise en place des invitations, autorisations et routes métier sécurisées.

## Architecture

- `apps/web` : React + TypeScript + Vite, compilé puis servi par Nginx.
- `apps/api` : FastAPI, endpoints de vérification technique seulement.
- PostgreSQL 16 : accessible uniquement sur le réseau Docker interne.
- `compose.yaml` : configuration Docker Compose pour le NAS Synology.
- `apps/web/public/logo-bde.png` : logo officiel fourni par le BDE.

## Déploiement initial sur Synology (test local uniquement)

1. Copier le contenu de ce ZIP dans le dépôt GitHub `Amin932/orga-alfiya` (ou transférer directement le dossier sur le NAS dans `/volume1/docker/orga-alfiya`). Une fois le dépôt rempli, on pourra aussi le cloner.
2. Copier `.env.example` vers `.env` et remplacer `POSTGRES_PASSWORD` par une chaîne aléatoire **sans `@`, `:`, `/`, `#`, `%` ni espace**, car elle est intégrée à une URL PostgreSQL. Ne jamais commiter `.env`.
3. Exécuter `docker compose up -d --build` depuis le répertoire du projet.
4. Tester sur le NAS : `curl http://127.0.0.1:8092/api/health` et `curl http://127.0.0.1:8092/api/health/database`.
5. Pour afficher l'interface depuis un poste de ton réseau local, lier temporairement `ORGA_HTTP_BIND` à l'IP LAN du NAS et accéder à `http://IP_DU_NAS:8092` (ne pas ouvrir ce port sur la box). Remettre `127.0.0.1` avant de passer par le reverse proxy.

## HTTPS et domaine cible (à configurer après les tests)

Dans **Panneau de configuration → Portail de connexion → Avancé → Proxy inversé** de DSM, créer une règle HTTPS `orga-alfiya.amvei.synology.me:443` vers HTTP `127.0.0.1:8092` ; attribuer le certificat wildcard valide à ce sous-domaine, vérifier sa résolution et les paramètres réseau. La règle doit être testée depuis l'extérieur avant de considérer l'URL fonctionnelle. Ne jamais publier directement PostgreSQL ou le port 8000 de l'API.

L'application n'a pas encore de système de connexion, donc **ne pas exposer publiquement ce socle avant le bloc 2** (authentification et vérification des droits).

## État du dépôt GitHub

Le dépôt initial est vide. Si la connexion GitHub utilisée ne dispose pas du droit `Contents: write`, le transfert initial devra être effectué depuis Git local ou GitHub Web. Le ZIP livré contient les fichiers prêts à importer, **y compris le logo officiel**.

## Commandes utiles

```bash
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 api
docker compose logs --tail=100 web
docker compose down
```

`docker compose down` ne supprime pas les volumes PostgreSQL et uploads. Ne jamais exécuter `docker compose down -v` sans sauvegarde.

## Étapes prévues

1. Socle technique et maquette visuelle (ce bloc).
2. Invitations uniquement, session durable/révocable, autorisations projet et super-admin.
3. Projets et pôles, affectations ordonnées, couleurs des membres.
4. Kanban avec glisser-déposer souris/tactile, cartes persistantes et filtres.
5. Bibliothèque globale de modèles et deux modèles officiels protégés.
6. Checklists, commentaires, fichiers, historique, corbeille.
7. Notifications internes, e-mail et push, rappels J-3/J-1/J/J+1.
8. Tests, sauvegardes et ouverture de l'accès HTTPS public.
