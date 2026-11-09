# Orga Alfiya — blocs 1 à 8

Application d'organisation du BDE Alfiya, hébergée sur NAS Synology, accessible à terme sur `https://orga-alfiya.amvei.synology.me/`.

## Fonctionnalités disponibles (blocs 1 à 8)

- Invitation **uniquement par le super-administrateur** ; lien individuel à usage unique valable 7 jours, à copier et transmettre manuellement.
- Le membre renseigne son nom, son prénom et choisit son premier pôle parmi ceux des projets autorisés.
- Connexion par identifiant (adresse e-mail) et mot de passe personnel (haché avec Argon2) ; session enregistrée 90 jours sur l'appareil, sans envoi d'e-mail.
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

**Limites actuelles :** le chargement des images et documents, les commentaires, l'historique des actions et les notifications arriveront dans les prochains blocs. Les tableaux et modèles sont codés pour PostgreSQL, mais des tests d'utilisation sur ton NAS restent nécessaires.

### Bloc 5 — Bibliothèque de modèles et checklists

- Bibliothèque **commune à tous les projets**, accessible aux membres connectés ; deux modèles officiels initiaux : « Événement avec intervenant » et « Événement sans intervenant ».
- Les modèles officiels peuvent être modifiés uniquement par le super-administrateur et ne peuvent pas être supprimés.
- Les autres membres peuvent créer leurs propres modèles, et les modifier/supprimer eux-mêmes ; le super-administrateur peut également gérer les modèles personnalisés.
- Dans une colonne Kanban, sélectionner « Saisie libre » ou un modèle de la bibliothèque, renseigner uniquement **le titre de la carte**, puis la créer immédiatement.
- Les champs de description et d'informations sont facultatifs ; ils apparaissent dans la fiche de carte, classés par rubriques et remplissables ultérieurement.
- Checklists « Préparation avant le jour J » et « Post-événement » fournies avec les deux modèles officiels, non cochées par défaut.
- Checklists opérationnelles par carte : cocher/décocher, ajouter/supprimer des tâches et créer/supprimer des listes ; l'auteur de la validation d'une tâche est enregistré.
- Une copie indépendante de chaque modèle est créée dans la carte ; les modifications ultérieures du modèle ne modifient **jamais les anciennes cartes**.
- Migration automatique à l'initialisation pour les cartes « speaker » / « no_speaker » créées au bloc 4 : copie de la définition du modèle officiel courant et création des checklists.
- Une suppression de modèle personnalisé n'efface pas les cartes déjà créées.

**Actions manuelles à ce stade :** Google Agenda et Eventbrite figurent dans les checklists mais ne sont pas encore reliés automatiquement ; l'envoi de messages de restriction à des participants n'est jamais déclenché automatiquement.

### Bloc 6 — Collaboration et documents

- Commentaires par carte avec **nom et prénom de l'auteur**, sa couleur issue du **premier pôle attribué**, et date de publication.
- Chaque membre peut modifier ou supprimer **ses propres commentaires** ; le super-administrateur peut supprimer ceux des autres membres.
- Mentions sélectionnables depuis la liste des **membres et pôles du même projet**, enregistrées avec leurs identifiants et vérifiées côté serveur. **Les notifications de mentions arrivent au bloc 7**.
- Ajout de photos et documents aux cartes avec stockage privé dans le volume Docker `uploads` sur le NAS. Formats acceptés : JPG/JPEG, PNG, WebP, GIF, PDF, DOCX, XLSX, PPTX et TXT ; limite **15 Mo par fichier**, 40 fichiers par carte.
- Les fichiers sont servis par l'API **uniquement si la session dispose d'un accès au projet**. Les images peuvent être choisies comme couverture : elles apparaissent en haut des cartes Kanban.
- Les fichiers peuvent être retirés par leur auteur ou le super-administrateur. La suppression définitive d'une carte efface également ses fichiers du volume après validation de la transaction.
- Journal d'activité pour les créations, modifications, déplacements, mises à la corbeille, restaurations, attributions, commentaires, pièces jointes, couvertures et checklists.
- Protection contre la suppression d'un pôle contenant encore des cartes, y compris dans la corbeille.

**À noter :** l'affichage des commentaires et documents ne nécessite aucun service externe. Les notifications automatiques et les envois de courriels pour les mentions ne sont pas encore actifs. Des tests d'intégration PostgreSQL/Docker et une vérification de sécurité restent nécessaires avant une ouverture publique. Les fichiers téléchargés ne sont pas analysés par antivirus dans cette version : ne partagez que des documents de sources fiables et prévoyez une analyse antivirus avant le déploiement en production.


### Bloc 7 — Notifications et échéances

- Centre de notifications dans le site, compteur non lu et lien direct vers les cartes.
- Alertes sur : attribution de carte, mention de membre ou de pôle, commentaires pour abonnés, passage à Terminé, nouveaux accès à un projet.
- Rappels activés par défaut J-3, J-1, J0, puis une fois à J+1 en cas de retard. Aucun rappel pour les cartes terminées, sans échéance ou supprimées.
- Cases de configuration propres à chaque carte pour J-7/J-3/J-1/J0/J+1 ; calcul après 9 heures (Europe/Paris).
- Préférences personnelles par catégorie et par canal e-mail/push.
- Notifications dans l'application et push VAPID avec un conteneur dédié "notification-worker", reprise sur échec et dédoublonnage.
- PWA avec service worker push ; aucun cache local des documents confidentiels.

#### Mise en place des notifications push

Sur le NAS, dans /volume1/docker/orga-alfiya :

```bash
mkdir -p secrets
openssl ecparam -name prime256v1 -genkey -noout -out secrets/vapid_private.pem
chmod 600 secrets/vapid_private.pem
```

La clé ne doit jamais être ajoutée à GitHub. Le conteneur utilise l'UID 10001 ; ajuster les droits de lecture du fichier en toute sécurité si nécessaire. Compléter le .env local avec :

```dotenv
VAPID_PRIVATE_KEY_FILE=/app/secrets/vapid_private.pem
VAPID_CONTACT=mailto:une-adresse-valide@exemple.fr
```

Puis, toujours sur le NAS :

```bash
git pull
docker compose config
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 notification-worker
```

Pour les push, l'utilisateur doit autoriser les notifications ; un navigateur compatible et une origine HTTPS sont requis. Sur iPhone, installer la PWA sur l'écran d'accueil. Les notifications par e-mail sont désactivées. Sans clé VAPID, le centre de notifications fonctionne, mais pas le push.

**Sécurité :** ne pas exposer ce service aux membres avant tests réels de PostgreSQL, du envoi d'e-mails, des push et des sauvegardes.

## Bloc 8 — Préparation de la mise en service Synology

**Guide de déploiement détaillé : [DEPLOIEMENT_SYNOLOGY.md](DEPLOIEMENT_SYNOLOGY.md).**

- Conteneurs API, PostgreSQL et Nginx munis de contrôles de santé ; démarrage du frontend et du worker après disponibilité de l'API.
- Test automatisé avec un **PostgreSQL réel** pour valider la création de projet, pôle, carte, modèle, commentaires, checklists et notifications.
- Workflow Docker qui compile et lance les conteneurs ensemble, puis vérifie les points d'entrée de l'application.
- Script `scripts/nas_preflight.sh` pour vérifier les prérequis et les paramètres locaux sans publier les secrets.
- Script `scripts/backup_nas.sh` pour sauvegarder la base et les documents en maintenance et redémarrer les services.
- Les fichiers `.env`, les clés privées et les dossiers de sauvegarde ne doivent jamais être transférés sur GitHub.

**Déploiement effectif sur le NAS : pas encore réalisé depuis ce dépôt.** L'URL HTTPS ne doit pas être présentée comme opérationnelle tant qu'un test réel depuis l'extérieur n'a pas réussi.

## Circuit de travail entre pôles (nouvelle fonctionnalité)

- Toute nouvelle carte est créée **dans « À faire »**, même si un ancien client transmet un autre statut.
- Les premières actions de travail (modification du contenu, checklist, commentaire, attribution, pièce jointe) font automatiquement passer une carte « À faire » à **« En cours »**. Une carte « Terminé » n'est pas rouverte par ces actions.
- Depuis la fiche d'une carte d'un pôle autre que Communication, bouton **« Envoyer au pôle communication »** en bas : validation explicite, source classée « Terminé » et **nouvelle carte indépendante « À faire »** dans le pôle Communication du même projet.
- Le modèle officiel d'origine conserve uniquement **Description de la carte complétée** et **Ajouter les mails des membres à l’événement dans Google Agenda une fois la date validée** dans sa checklist de préparation. Les cinq tâches de Communication (visuel, Eventbrite créé, Eventbrite publié, mail programmé, liste des participants BDE et rôles) n'apparaissent que dans la carte reçue après transmission.
- Les anciennes cartes issues des modèles officiels sont nettoyées des tâches Communication non cochées au redémarrage ; les tâches déjà cochées restent pour conserver l'historique, ainsi que les modifications personnalisées.
- La nouvelle carte reprend titre, description, dates, données du modèle et liens utiles de la carte d'origine, avec une checklist Communication indépendante.
- Chaque carte possède une section **Liens utiles** (URL http/https validée, titre libre, ajout et suppression autorisés). Exemple : Zoom, Eventbrite et Google Agenda. Les liens déjà renseignés sont transmis en copie au pôle Communication.
- Les checklists d'origine, les commentaires et les documents joints ne sont pas dupliqués : le pôle Communication peut consulter les documents dans la carte d'origine via le lien prévu. Les mises à jour ultérieures de l'une des cartes ne modifient pas automatiquement l'autre.
- Un même événement ne peut pas être envoyé deux fois ; la carte d'origine reste clôturée après transmission, même si son contenu est consulté ou modifié.
- Les membres actifs affectés au pôle Communication reçoivent une notification interne (et une push s'ils l'ont activée), sans SMTP.
- Le pôle destination doit contenir le mot **« Communication »** dans son nom (par exemple « Communication » ou « Pôle Communication »), sans plusieurs correspondances dans un même projet.
- Sur appareil tactile, l'avancement s'effectue via le sélecteur de statut de la fiche ; sur ordinateur, le glisser-déposer reste possible pour les cartes non transférées.
- **Déploiement :** une mise à jour du code et une recréation de l'API + du web sont nécessaires ; les évolutions de schéma PostgreSQL sont appliquées automatiquement au démarrage, sans effacer les anciennes cartes. Faire une sauvegarde préalable et tester avec un projet non critique.

## Configuration sur Synology

1. Cloner `https://github.com/Amin932/orga-alfiya.git` dans `/volume1/docker/orga-alfiya`.
2. Copier `.env.example` vers `.env`, remplacer `POSTGRES_PASSWORD` avec un mot de passe aléatoire robuste (sans caractères spéciaux d'URL non encodés), `SUPERADMIN_EMAIL` par **ton adresse e-mail** et définir `SUPERADMIN_INITIAL_PASSWORD` (16 caractères minimum) pour la première connexion de l'administrateur. Aucun compte SMTP n'est nécessaire. Ne jamais publier `.env`.
3. Vérifier `ORGA_PUBLIC_URL` : c'est l'origine exacte utilisée dans le navigateur. Pour la mise en service, configurer le reverse proxy Synology en HTTPS (source `orga-alfiya.amvei.synology.me:443` vers `127.0.0.1:8092`) et un certificat valide avant de tester l'authentification. Ne pas exposer PostgreSQL ni l'API directement.
4. Exécuter `docker compose config` puis `docker compose up -d --build` ; tester `docker compose ps` et `curl http://127.0.0.1:8092/api/health`.
5. Sur l'URL HTTPS, se connecter avec `SUPERADMIN_EMAIL` et le mot de passe initial défini dans `.env`. Le super-administrateur est créé lors du premier démarrage. Créer un projet et ses pôles, puis générer des liens d'invitation personnels à partager manuellement.

**Sécurité :** par défaut, les sessions nécessitent HTTPS (`COOKIE_SECURE=true`). Les requêtes de modification requièrent un en-tête spécifique et une origine autorisée ; les liens d'invitation ne sont pas enregistrés dans les journaux du proxy (jeton dans le fragment d'URL). Ne pas configurer `COOKIE_SECURE=false` pour un site exposé : ce mode ne convient qu'à un essai strictement local et doit aussi être explicitement autorisé avec `ALLOW_INSECURE_LOCAL=yes`.

Le domaine visé peut nécessiter une configuration réseau complémentaire selon la connexion Internet du NAS. Ne pas ouvrir le port PostgreSQL sur Internet. Sauvegarder régulièrement le volume `pgdata` et les documents.

## Vérifications automatiques

À chaque commit, GitHub Actions est configuré pour effectuer un build TypeScript/React et des tests unitaires de protections de l'API (`.github/workflows/verify.yml`). Les tests réels du déploiement sur NAS et des notifications push restent indispensables avant ouverture publique.

## À compléter aux prochains blocs

- Historique et commentaires enrichis, amélioration de l'ergonomie et tests d'intégration réels.
- Prévoir une analyse antivirus des pièces jointes avant l'ouverture aux membres.
- Tests complets sur le NAS : Docker, PostgreSQL, push et sauvegardes.
- Tests d'intégration et revue de sécurité avant ouverture aux 25 membres.

### Modification : aucun envoi d'e-mail

Les invitations sont générées dans l'interface d'administration sous forme de liens privés valables 7 jours, à transmettre manuellement. Chaque membre choisit son mot de passe à l'activation ; les sessions restent mémorisées pendant 90 jours. L'application propose des notifications internes et push uniquement, sans SMTP ni connexion Gmail.

La première installation nécessite un `SUPERADMIN_INITIAL_PASSWORD` local dans `.env`. Après le premier démarrage, il est conseillé de changer son mot de passe depuis le profil et de vider la variable d'initialisation dans le fichier local. Pour récupérer un accès super-admin sans courrier : `sudo docker compose exec api python -m app.reset_admin_password`.
