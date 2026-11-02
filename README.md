# Orga Alfiya — blocs 1 à 4

Application d'organisation du BDE Alfiya, hébergée sur NAS Synology, accessible à terme sur `https://orga-alfiya.amvei.synology.me/`.

## Fonctionnalités disponibles (blocs 1 à 4)

- Invitation **uniquement par le super-administrateur** ; lien individuel à usage unique valable 7 jours.
- Le membre renseigne son nom, son prénom et choisit son premier pôle parmi ceux des projets autorisés.
- Connexion par lien e-mail valable 20 minutes ; session enregistrée 90 jours sur l'appareil.
- Déconnexion et révocation immédiate des sessions lors de la désactivation du compte.
- Administration des projets (création, renommage, description et suppression contrôlée), des pôles (création, couleur, édition et suppression contrôlée) et des invitations.
- Fiche membre : accès à plusieurs projets, appartenances à plusieurs pôles, ordre réglable ; **le premier pôle définit la couleur permanente du membre** dans l'interface.
- Annuaire des membres avec état actif / invitation en attente / désactivé ; réactivation d'un compte déjà activé.
- Un accès à un projet couvre tous ses pôles ; les affectations aux pôles ne donnent **aucun** accès supplémentaire.
- Accès aux projets filtré **côté API**, sans droit sur les projets non autorisés.
- PostgreSQL (comptes, invitations, sessions et affectations). Secrets de session stockés **hachés**.

### Bloc 4 — Tableaux Kanban

- Cartes réelles stockées dans PostgreSQL, visibles uniquement depuis les pôles de projets autorisés.
- Colonnes **À faire / En cours / Terminé**, ordre manuel enregistré, déplacement par glisser-déposer (souris, appui prolongé tactile et clavier).
- Création rapide dans chaque colonne : **seul le titre est obligatoire**. Choix entre saisie libre et les deux types officiels (« avec intervenant » / « sans intervenant ») ; le contenu structuré des modèles sera ajouté au bloc 5.
- Modification ultérieure du titre, de la description, de la date de début et de la date d'échéance, sans obligation de compléter immédiatement.
- Attribution de plusieurs membres déjà autorisés au projet ; étiquette couleur liée au premier pôle de chaque membre.
- Filtres **indépendants par colonne** : titre, plage de dates (début ou échéance), tri alphabétique ou chronologique. Les filtres ne suppriment jamais de cartes.
- Mise à la corbeille réservée au **créateur** ou au **super-admin** ; restauration et suppression définitive réservées au super-admin dans l'onglet Corbeille.
- Création et modifications vérifiées côté API ; protection des projets non autorisés et vérification des requêtes mutantes.

**Limites actuelles :** les champs spécialisés et checklists des modèles, le chargement d'images, les commentaires, l'historique et les notifications arriveront dans les prochains blocs. Une carte choisissant un modèle conserve actuellement sa référence au modèle, mais n'affiche pas encore les champs préremplis. Les tableaux sont fonctionnels une fois déployés sur une base PostgreSQL, mais des tests d'utilisation sur ton NAS restent nécessaires.

## Configuration sur Synology

1. Cloner `https://github.com/Amin932/orga-alfiya.git` dans `/volume1/docker/orga-alfiya`.
2. Copier `.env.example` vers `.env`, remplacer `POSTGRES_PASSWORD` avec un mot de passe aléatoire robuste (sans caractères spéciaux d'URL non encodés), `SUPERADMIN_EMAIL` par **ton adresse e-mail** et configurer `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` avec les paramètres de ton hébergeur mail. Ne jamais publier `.env`.
3. Vérifier `ORGA_PUBLIC_URL` : c'est l'origine exacte utilisée dans le navigateur. Pour la mise en service, configurer le reverse proxy Synology en HTTPS (source `orga-alfiya.amvei.synology.me:443` vers `127.0.0.1:8092`) et un certificat valide avant de tester l'authentification. Ne pas exposer PostgreSQL ni l'API directement.
4. Exécuter `docker compose config` puis `docker compose up -d --build` ; tester `docker compose ps` et `curl http://127.0.0.1:8092/api/health`.
5. Sur l'URL HTTPS, saisir l'adresse `SUPERADMIN_EMAIL` et demander un lien de connexion. Le super-administrateur est créé lors du premier démarrage. En recevant le lien, accéder à l'administration, créer un projet et ses pôles, puis envoyer les invitations.

**Sécurité :** par défaut, les sessions nécessitent HTTPS (`COOKIE_SECURE=true`). Les requêtes de modification requièrent un en-tête spécifique et une origine autorisée ; les liens d'invitation ne sont pas enregistrés dans les journaux du proxy (jeton dans le fragment d'URL). Ne pas configurer `COOKIE_SECURE=false` pour un site exposé : ce mode ne convient qu'à un essai strictement local et doit aussi être explicitement autorisé avec `ALLOW_INSECURE_LOCAL=yes`.

Le domaine visé peut nécessiter une configuration réseau complémentaire selon la connexion Internet du NAS. Ne pas ouvrir le port PostgreSQL sur Internet. Sauvegarder régulièrement le volume `pgdata` et les documents.

## Vérifications automatiques

À chaque commit, GitHub Actions est configuré pour effectuer un build TypeScript/React et des tests unitaires de protections de l'API (`.github/workflows/verify.yml`). Un lancement complet avec PostgreSQL et un service SMTP réel reste indispensable avant ouverture publique.

## À compléter aux prochains blocs

- Champs structurés des modèles officiels et bibliothèque de modèles personnalisés.
- Checklists, commentaires, fichiers, historique et corbeille.
- Notifications internes, SMTP et push, rappels d'échéance.
- Tests d'intégration et revue de sécurité avant ouverture aux 25 membres.
