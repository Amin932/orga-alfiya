# Déploiement Orga Alfiya sur NAS Synology (DSM 7)

> D'abord en local, ensuite HTTPS public. Ne jamais envoyer les secrets dans un chat ou les committer sur GitHub.

## 1 — Prérequis

- NAS Synology allumé, Docker/Container Manager opérationnel, SSH si installation en ligne de commande.
- Un accès GitHub à \`Amin932/orga-alfiya\`.
- Un compte de messagerie SMTP avec autorisation d'envoyer des e-mails de connexion/invitation.
- Une sauvegarde DSM fonctionnelle, de l'espace disque et un accès internet sortant depuis le NAS.
- Pour l'accès externe : le DNS de \`orga-alfiya.amvei.synology.me\` doit pointer vers une adresse joignable depuis Internet. Le fait d'avoir une Flybox 5G ne garantit pas une entrée IPv4 publique ou une redirection de port utilisable ; tester le point depuis un téléphone **hors Wi-Fi** et vérifier que l'opérateur ne bloque pas le trafic entrant.

Le certificat HTTPS présenté dans DSM doit couvrir précisément \`orga-alfiya.amvei.synology.me\`. Le wildcard \`*.amvei.synology.me\` couvre ce nom s'il est toujours valide.

## 2 — Télécharger les fichiers

Se connecter en SSH au NAS :

\`\`\`sh
cd /volume1/docker
git clone https://github.com/Amin932/orga-alfiya.git
cd orga-alfiya
cp .env.example .env
mkdir -p secrets
\`\`\`

Si le dépôt existe déjà, utiliser \`git pull --ff-only\` **avant la mise à jour**. Ne pas recopier .env.example sur le .env existant.

## 3 — Configurer les variables locales

Éditer uniquement \`/volume1/docker/orga-alfiya/.env\`, sur le NAS :

- POSTGRES_PASSWORD : choisir une valeur robuste, de préférence 64 caractères hexadécimaux via \`openssl rand -hex 32\` pour éviter les caractères réservés dans l'URL PostgreSQL de cette version. **Ne jamais transmettre cette valeur.**
- SUPERADMIN_EMAIL : adresse réelle du compte super-administrateur.
- ORGA_PUBLIC_URL : \`https://orga-alfiya.amvei.synology.me\` (sans slash final).
- ORGA_HTTP_BIND : \`127.0.0.1\` ; ORGA_HTTP_PORT : \`8092\`.
- COOKIE_SECURE : \`true\`.
- SMTP_HOST, SMTP_PORT (465 SSL ou 587 STARTTLS), SMTP_USERNAME, SMTP_PASSWORD et SMTP_FROM : utiliser les paramètres exacts du fournisseur mail ; ne pas inventer de serveur.
- VAPID_CONTACT : une adresse e-mail de contact valide sous la forme \`mailto:...\` (si push activé).

Créer la clé privée VAPID sur le NAS (à ne pas publier) :

\`\`\`sh
openssl ecparam -name prime256v1 -genkey -noout -out secrets/vapid_private.pem
sudo chown 10001:10001 secrets/vapid_private.pem
sudo chmod 600 secrets/vapid_private.pem
\`\`\`

La clé sera montée **en lecture seule** dans les deux conteneurs qui en ont besoin. Les e-mails, la base et les alertes internes peuvent être testés sans la clé push.

## 4 — Pré-vérifier et lancer en local

\`\`\`sh
sudo sh scripts/nas_preflight.sh
sudo docker compose up -d --build
sudo docker compose ps
curl --fail http://127.0.0.1:8092/api/health/database
\`\`\`

Résultat de santé attendu : \`{"status":"ok","database":"connected"}\`.

Si besoin de diagnostiquer :

\`\`\`sh
sudo docker compose logs --tail=100 api
sudo docker compose logs --tail=100 web
sudo docker compose logs --tail=100 notification-worker
\`\`\`

**Ne jamais partager la sortie complète de \`docker compose config\` : elle peut inclure les secrets.** Utiliser \`docker compose config --quiet\`.

Le site écoute **seulement sur 127.0.0.1:8092 du NAS**, pas sur toutes les interfaces. Aucun port PostgreSQL n'est publié.

## 5 — Reverse proxy HTTPS dans DSM

Dans DSM : **Panneau de configuration → Portail de connexion → Avancé → Proxy inversé → Créer**.

| Champ | Valeur |
|---|---|
| Description | Orga Alfiya |
| Source : protocole | HTTPS |
| Source : nom d'hôte | \`orga-alfiya.amvei.synology.me\` |
| Source : port | 443 |
| Destination : protocole | HTTP |
| Destination : nom d'hôte | \`127.0.0.1\` |
| Destination : port | 8092 |

Dans **Panneau de configuration → Sécurité → Certificat → Paramètres**, attribuer le certificat approprié au service/nom d'hôte de la règle. Activer HSTS une fois HTTPS validé.

Sur le routeur : ne rediriger **que le port TCP 443** si un accès entrant public est réellement possible. N'ouvrir ni 5432 (PostgreSQL), ni 8000 (API), ni 8092 (web interne), ni 5001 (DSM) spécifiquement pour cette application.

Tester depuis le réseau mobile (Wi-Fi désactivé) :
\`https://orga-alfiya.amvei.synology.me/api/health/database\`

Si la connexion externe ne marche pas mais la connexion locale fonctionne, vérifier DNS IPv4/IPv6, IP WAN du routeur, éventuel CGNAT et règles de pare-feu Synology. **Ne pas abaisser la sécurité des cookies ni exposer directement les conteneurs** pour contourner le problème.

## 6 — Recette fonctionnelle avant ouverture

1. Ouvrir le site HTTPS. Demander le lien de connexion à l'adresse SUPERADMIN_EMAIL ; réception SMTP, activation et session conservée au redémarrage du navigateur.
2. Créer un projet « BDE Alfiya », puis deux pôles de couleurs différentes.
3. Inviter **un seul compte de test**, lui donner accès au projet et vérifier qu'il ne peut pas créer de pôle.
4. Se connecter avec ce compte et créer une carte « Test » à partir du modèle officiel sans remplir les autres champs.
5. Ajouter une date, remplir les rubriques, cocher les checklists, joindre une image et la choisir en couverture.
6. Vérifier le glisser-déposer sur ordinateur et sur smartphone.
7. Commenter, mentionner un autre membre, puis vérifier que le bon nom/couleur apparaît.
8. Attribuer un responsable, suivre la carte, vérifier les notifications internes et un e-mail de test.
9. Autoriser le push sur un appareil compatible, vérifier sa réception, puis se déconnecter.
10. Vérifier le passage en « Terminé », les droits de suppression, la corbeille et la restauration.
11. S'assurer qu'une personne sans accès au projet **ne peut pas consulter** ses cartes ni ses fichiers, même via une URL directe.

Les rappels J-3/J-1/J0/J+1 sont prévus à partir de 9 h, heure Europe/Paris. Leur test complet nécessite des dates adaptées et la vérification du journal du notification-worker.

## 7 — Sauvegardes

Script prévu : \`sudo sh scripts/backup_nas.sh\`. Il arrête temporairement le site, l'API et le worker, sauvegarde PostgreSQL et les pièces jointes, puis redémarre les services. Résultat par défaut dans \`backups/AAAAmmjjTHHMMSSZ/\` (ignoré par Git).

Il faut **conserver des copies chiffrées hors du NAS**, planifier une sauvegarde régulière dans le Planificateur de tâches DSM, contrôler l'espace libre, et tester la restauration **sur un environnement d'essai** avant la production. Les sauvegardes contiennent des données personnelles, et les archives ne sont pas chiffrées par le script lui-même.

Ne jamais utiliser une commande de restauration sur la base de production sans une sauvegarde préalable récente : elle peut écraser toutes les données.

## 8 — Mise à jour ultérieure

Effectuer une sauvegarde, puis :

\`\`\`sh
cd /volume1/docker/orga-alfiya
git pull --ff-only
sudo docker compose up -d --build
sudo docker compose ps
\`\`\`

Les migrations sont lancées par l'API au démarrage. Faire la mise à jour pendant une période peu active et conserver une sauvegarde antérieure à la mise à jour.

## État de la mise en service

Les tests GitHub Actions valident la compilation, l'API et PostgreSQL. Cela **ne prouve pas** que le certificat, le reverse proxy, le SMTP, les push ou la Flybox fonctionnent depuis Internet. Cette vérification ne peut être faite qu'après le démarrage sur ton NAS.
