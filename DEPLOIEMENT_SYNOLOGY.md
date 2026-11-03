# Déploiement Orga Alfiya sur Synology (sans SMTP)

Orga Alfiya utilise **deux canaux de notifications seulement** : le centre de notifications dans le tableau de bord et, si activées, les notifications push sur les téléphones et ordinateurs compatibles. Aucun service de messagerie (Gmail, SMTP, Hostinger) n'est requis.

## 1. Mise à jour du dépôt

Sur ce NAS, Git n'est pas installé directement dans DSM. Depuis SSH :

```sh
cd /volume1/docker/orga-alfiya
sudo docker run --rm -v /volume1/docker/orga-alfiya:/repo -w /repo alpine/git -c safe.directory=/repo pull --ff-only
```

Ne pas supprimer le dossier existant, les volumes Docker ni le fichier `.env`.

## 2. Variables locales

Éditer le fichier `/volume1/docker/orga-alfiya/.env` avec `vi .env`.

```dotenv
POSTGRES_DB=orga_alfiya
POSTGRES_USER=orga_alfiya
POSTGRES_PASSWORD=REMPLACER_PAR_LE_MOT_DE_PASSE_POSTGRES
ORGA_HTTP_BIND=127.0.0.1
ORGA_HTTP_PORT=8092
ORGA_PUBLIC_URL=https://orga-alfiya.amvei.synology.me
COOKIE_SECURE=true
SUPERADMIN_EMAIL=VOTRE_IDENTIFIANT_ADMIN
SUPERADMIN_INITIAL_PASSWORD=REMPLACER_PAR_UN_MOT_DE_PASSE_INITIAL_16_CARACTERES_MINIMUM
VAPID_PRIVATE_KEY_FILE=/app/secrets/vapid_private.pem
VAPID_CONTACT=mailto:une-adresse-de-contact-valide@example.org
```

Les valeurs `REMPLACER` doivent être remplacées par des valeurs réelles et les deux mots de passe doivent être différents. Générer un secret robuste avec `openssl rand -hex 32`. **Ne jamais publier ces valeurs, ni les coller dans un chat.**

**Supprimer toutes les lignes commençant par `SMTP_`** éventuellement présentes dans l'ancien `.env`. Il ne faut pas y mettre de mot de passe Gmail. `SUPERADMIN_EMAIL` reste un **identifiant**, pas une adresse destinataire de courriels envoyés par le site. Le premier compte super-admin est initialisé avec `SUPERADMIN_INITIAL_PASSWORD`. Après le démarrage initial, changer son mot de passe dans l'application et vider la variable initiale dans `.env`.

## 3. Clé de notification push

Pour activer les notifications sur les appareils compatibles :

```sh
cd /volume1/docker/orga-alfiya
mkdir -p secrets
openssl ecparam -name prime256v1 -genkey -noout -out secrets/vapid_private.pem
sudo chown 10001:10001 secrets/vapid_private.pem
sudo chmod 600 secrets/vapid_private.pem
```

La clé doit rester sur le NAS, dans `secrets/`, et être lisible par l'utilisateur UID 10001 du conteneur. L'application fonctionne sans push si la clé est absente. Sur les téléphones, l'utilisateur doit autoriser les notifications ; sur iPhone, la PWA doit être ajoutée à l'écran d'accueil et ouverte comme application.

## 4. Vérifications et lancement

```sh
cd /volume1/docker/orga-alfiya
sudo sh scripts/nas_preflight.sh
sudo docker compose up -d --build
sudo docker compose ps
curl --fail http://127.0.0.1:8092/api/health/database
```

Réponse attendue :

```json
{"status":"ok","database":"connected"}
```

En cas d'erreur :

```sh
sudo docker compose logs --tail=100 api
sudo docker compose logs --tail=100 web
sudo docker compose logs --tail=100 notification-worker
```

Ne jamais partager `docker compose config` sans l'option `--quiet`, car la sortie peut exposer des secrets.

## 5. Reverse proxy HTTPS DSM

Dans **Panneau de configuration → Portail de connexion → Avancé → Proxy inversé** :

| Paramètre | Valeur |
|---|---|
| Source | HTTPS `orga-alfiya.amvei.synology.me` port `443` |
| Destination | HTTP `127.0.0.1` port `8092` |

Attribuer le certificat valide `*.amvei.synology.me` à la règle. L'ouverture externe du port 443 dépend aussi du DNS, du routeur Flybox et d'une éventuelle restriction CGNAT/IPv4 de l'opérateur. Tester depuis le réseau mobile hors Wi-Fi. Ne jamais exposer les ports PostgreSQL 5432, API 8000 ou web interne 8092 sur Internet.

## 6. Invitations et connexion sans e-mail

- Première connexion du super-admin : saisir `SUPERADMIN_EMAIL` et le mot de passe initial.
- Depuis l'administration, créer les projets/pôles puis **générer un lien d'invitation** pour chaque membre.
- **Copier le lien et le partager personnellement** via un canal de confiance (message, face à face, etc.). Il est valable **7 jours** et utilisable **une fois**. Aucun e-mail automatique n'est envoyé.
- Le membre renseigne son prénom, son nom, son premier pôle et choisit un mot de passe personnel de 12 caractères minimum.
- Sur un appareil déjà connecté, la session persiste jusqu'à 90 jours. Sur un nouvel appareil, le membre utilise son identifiant et son mot de passe.
- Si un membre oublie son mot de passe, l'administrateur crée dans sa fiche un lien privé de **réinitialisation valable 30 minutes**, à partager manuellement.
- Si l'administrateur oublie le sien, la réinitialisation locale se fait depuis le terminal SSH :

```sh
sudo docker compose exec api python -m app.reset_admin_password
```

## 7. Tests avant l'ouverture aux membres

Tester sur un compte d'essai : invitation à usage unique, connexion persistante, accès par projet, création de cartes, checklist, commentaire, mention, glisser-déposer, pièces jointes, corbeille. Vérifier que la personne sans accès ne peut ouvrir ni une carte ni un fichier via son URL directe. Tester les notifications **dans l'application**, puis les push après installation de la PWA. Les rappels sont calculés en Europe/Paris et envoyés à partir de 9 h.

Les tests de compilation GitHub et les tests Docker/PostgreSQL ne remplacent **pas** ces vérifications réelles sur le NAS.

## 8. Sauvegardes

`sudo sh scripts/backup_nas.sh` crée une archive de la base PostgreSQL et des pièces jointes pendant une courte maintenance, puis redémarre les services. Le script ne chiffre pas les archives. Conserver une copie chiffrée hors du NAS et tester la restauration sur un environnement isolé.

Avant chaque mise à jour du code : sauvegarder, mettre à jour le dépôt avec `alpine/git`, puis relancer `sudo docker compose up -d --build`.
