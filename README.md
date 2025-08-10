# iObeya → GitHub Projects (MVP, Features Only)

**Objectif :** synchronisation *one-way* des **Features** depuis iObeya vers **GitHub Projects (v2)**.  
Les équipes gèrent ensuite leurs **Stories** dans leurs outils. Ce dépôt fournit un **MVP** en trois étapes : **Extract → Map → Load**.

## Architecture rapide
- **extract_iobeya.py** : lit les Features du board iObeya (API REST/Facade), exporte en `features_raw.json`.
- **map_features.py** : transforme le JSON iObeya vers un schéma commun (`features_normalized.json`).
- **load_github.py** : crée/maj des **Draft Issues** dans un **Project v2** via l’API **GraphQL** + renseigne les **custom fields**.
- **common/** : utilitaires (logs, stockage idempotent).
- **.github/workflows/sync.yml** : exécution planifiée (cron) ou manuelle (workflow_dispatch).

> **MVP = unidirectionnel** iObeya → GitHub. Pas d’écriture vers iObeya. Ajoutez progressivement la bidirectionnalité après stabilisation.

## Pré-requis
- Accès API iObeya (URL base, identifiants, droits lecture).
- Un **GitHub Project (v2)** existant (org ou repo) avec **custom fields** créés :  
  `Feature Key (Text)`, `State (Single-select)`, `WSJF (Number)`, `PI (Text/Iteration)`, `Owner (Text)`, `Tags (Text/Labels)`, `Last Sync At (Date)`.
- Un **token GitHub** (scope: `project`, `repo`, `read:org` selon le contexte) et un **token iObeya**.
- Python 3.10+ (si vous convertissez le pseudo-code en code).

## Démarrage (mode local)
1. Copiez `config.example.yaml` en `config.yaml` et renseignez vos valeurs.
2. Exécutez le pipeline MVP :
   ```bash
   ./scripts/run_mvp.sh
   ```
   Le script appelle `src/extract_iobeya.py → src/map_features.py → src/load_github.py`.

## Déploiement (GitHub Actions)
- Renseignez les **secrets** (`IOBEYA_BASE_URL`, `IOBEYA_USER`, `IOBEYA_PASS`, `GITHUB_TOKEN`, `GITHUB_PROJECT_ID`, `IOBEYA_BOARD_ID`) dans votre dépôt/organisation.
- Activez le workflow `.github/workflows/sync.yml` (planification quotidienne par défaut).

## Idempotence
- Table de correspondance (simple fichier ou SQLite) : `iobeya_feature_id → github_item_id`.
- Si l’élément existe déjà : mise à jour, sinon création. Pas de doublon.

## Limites MVP
- Synchronisation du **niveau Feature** uniquement.
- Pas de gestion des dépendances complexes ni des fichiers joints.
- La structure de l’API iObeya peut varier selon versions/métamodèle : adaptez `extract_iobeya.py`.

## Roadmap suggérée
- V1: MVP batch (journalisation + retries).
- V1.1: Delta updates (filtrage par date de modification).
- V2: Webhooks GitHub → notifications / réconciliation.
- V2.1: Écriture iObeya (statuts, liens de dépendance) après validation sécurité.

## Licence
MIT (voir `LICENSE`).
