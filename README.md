# Orga Alfiya — blocs 1 et 2

Application d'organisation du BDE Alfiya, hébergée sur NAS Synology, accessible à terme sur `https://orga-alfiya.amvei.synology.me/`.

## Ce qui fonctionne dans le bloc 2

- Invitation **uniquement par le super-administrateur** ; lien individuel à usage unique valable 7 jours.
- Le membre renseigne son nom, son prénom et choisit son premier pôle parmi ceux des projets autorisés.
- Connexion par lien e-mail valable 20 minutes ; session enregistrée 90 jours sur l'appareil.
- Déconnexion et révocation immédiate des sessions lors de la désactivation du compte.
- Gestion initiale des projets, pôles et invitations dans le panneau d'administration.
- Accès aux projets filtré **côté API**, sans droit sur les projets non autorisés.
- PostgreSQL (comptes, invitations, sessions et affectations). Secrets de session stockés **hachés**.

Les cartes Kanban et leurs données ne sont **pas encore actives** : elles seront implémentées dans les blocs suivants. La page des tableaux est un squelette, non un outil de suivi fonctionnel.

## Configuration sur Synology

1. Cloner `https://github.com/Amin932/orga-alfiya.git` dans `/volume1/docker/orga-alfiya`.
2. Copier `.env.example` vers `.env`, remplacer `POSTGRES_PASSWORD` avec un mot de passe aléatoire robuste (sans caractères spéciaux d'URL non encodés), `SUPERADMIN_EMAIL` par **ton adresse e-mail** et configurer `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` avec les paramètres de ton hébergeur mail. Ne jamais publier `.env`.
3. Vérifier `ORGA_PUBLIC_URL` : c'est l'origine exacte utilisée dans le navigateur. Pour la mise en service, configurer le reverse proxy Synology en HTTPS (source `orga-alfiya.amvei.synology.me:443` vers `127.0.0.1:8092`) et un certificat valide avant de tester l'authentification. Ne pas exposer PostgreSQL ni l'API directement.
4. Exécuter `docker compose config` puis `docker compose up -d --build` ; tester `docker compose ps` et `curl http://127.0.0.1:8092/api/health`.
5. Sur l'URL HTTPS, saisir l'adresse `SUPERADMIN_EMAIL` et demander un lien de connexion. Le super-administrateur est créé lors du premier démarrage. En recevant le lien, accéder à l'administration, créer un projet et ses pôles, puis envoyer les invitations.

**Sécurité :** par défaut, les sessions nécessitent HTTPS (`COOKIE_SECURE=true`). Les requêtes de modification requièrent un en-tête spécifique et une origine autorisée ; les liens d'invitation ne sont pas enregistrés dans les journaux du proxy (jeton dans le fragment d'URL). Ne pas configurer `COOKIE_SECURE=false` pour un site exposé : ce mode ne convient qu'à un essai strictement local et doit aussi être explicitement autorisé avec `ALLOW_INSECURE_LOCAL=yes`.

Le domaine visé peut nécessiter une configuration réseau complémentaire selon la connexion Internet du NAS. Ne pas ouvrir le port PostgreSQL sur Internet. Sauvegarder régulièrement le volume `pgdata` et les documents.

## À compléter aux prochains blocs

- Gestion visuelle avancée des membres et de leurs affectations multiples (ordre des pôles, couleur du premier), suppression / modification des pôles.
- Cartes, glisser-déposer sur ordinateur et mobile, filtres, gestion des modèles.
- Checklists, commentaires, fichiers, historique et corbeille.
- Notifications internes, SMTP et push, rappels d'échéance.
- Tests d'intégration et revue de sécurité avant ouverture aux 25 membres.
