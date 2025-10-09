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

## Utilisation et logique du projet

Une fois le serveur lancé avec :

```bash
python -m webapp.app
```

ouvrez votre navigateur à l’adresse [http://localhost:8080](http://localhost:8080).  
Vous accéderez alors à l’interface Web complète de synchronisation entre **Grist**, **iObeya** et **GitHub**.

![Interface Web de synchronisation](images/screen.png)

### 1. Logique générale

Le projet vise à centraliser la gestion des **features** (fonctionnalités, user stories, etc.) présentes dans trois outils distincts :  
- **Grist** (base de référence)  
- **iObeya** (suivi visuel sur les panneaux)  
- **GitHub** (suivi technique dans les projets ou issues)

La synchronisation repose sur une logique de comparaison :
- Les données sont d’abord **récupérées depuis chaque source**.
- Les différences (ajouts, suppressions, modifications) sont **analysées et affichées**.
- L’utilisateur décide ensuite de **synchroniser dans un sens ou dans l’autre**, selon les besoins.

### 2. Étapes d’utilisation

1. **Sélection des paramètres**
   - Indiquez sur quel incrément de planning (PI) la synchronisation doit s'effectuer.
   - Choisissez :
     - l’**Epic** concerné,
     - le document et la table **Grist** à utiliser,
     - la **Room iObeya** et le **Board** cible,
     - le **projet GitHub** correspondant.  
   Ces menus sont automatiquement alimentés via les API respectives.

2. **Préparation**
   - Cliquez sur le bouton **« Préparer »** pour charger et comparer les données entre les trois systèmes, sans effectuer de synchronisation.
   - Un tableau récapitulatif s’affiche, indiquant les différences détectées (ajouts, modifications, suppressions).
   - Vous pouvez ainsi visualiser les écarts avant toute action.
   - le bouton **Télécharger JSON...** permet de télécharger l'ensemble des différences pour aider à la vérification ou sauvegarde des données manipulées.

3. **Synchronisation**
   - **« Synchroniser »** : met à jour les éléments des systèmes cibles uniquement là où des différences existent.  
   - **« Synchronisation forcée »** : écrase totalement les données des destinations avec celles de Grist (⚠️ à utiliser avec prudence).  
   - Si la case **« Renommer les éléments supprimés »** est cochée, les éléments supprimés seront renommés avec le préfixe `del_` au lieu d’être supprimés définitivement.

4. **Sauvegarde des préférences**
   - Les sélections (Epic, room, projet, etc.) peuvent être enregistrées dans un **cookie** via le bouton **« Sauvegarder les préférences »**, puis restaurées avec **« Charger les préférences »** au prochain démarrage.
   - Le bouton **« Supprimer les préférences »** efface le cookie enregistré.
