# Architecture (MVP)

Flux : **Extract → Map → Load**

- **Extract (iObeya)** : appelle l'API (auth → read elements) et produit `features_raw.json`.
- **Map** : convertit la structure iObeya en `features_normalized.json` avec des clés stables.
- **Load (GitHub)** : crée/maj les items (Draft Issues) dans un **Project v2** et positionne les **custom fields**.

## Idempotence
- Store clé-valeur : `iobeya_feature_id → github_item_id`.
- Compare les hash/versions pour ne mettre à jour que les changements.

## Sécurité
- Secrets via variables d’environnement (GitHub Actions) / fichiers locaux non commités.
- Journalisation sobre (pas d’info sensible).
