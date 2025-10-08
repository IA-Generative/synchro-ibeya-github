# Synchronisation Grist ↔ iObeya ↔ GitHub (Interface Web complète)

## Description
Ce projet permet de synchroniser automatiquement les **features** issues de **Grist**
vers un **panneau iObeya** et un **projet GitHub**, via une interface Web Flask.

### Fonctionnalités
- Sélection de l'épic, de la source Grist, de la room iObeya et du projet GitHub.
- Vérification des changements avant synchronisation.
- Synchronisation normale ou forcée (écrasement complet des destinations).
- Option pour renommer les éléments supprimés avec le préfixe `del_`.

## Installation
```bash
pip install -r requirements.txt
```

## Lancement
```bash
python -m webapp.app
```
Puis ouvrez [http://localhost:8080](http://localhost:8080)
