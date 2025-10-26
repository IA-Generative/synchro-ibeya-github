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
Puis ouvrez avec votre navigateur l'emplacement [http://localhost:8080](http://localhost:8080) si utilisation en local ou à l'emplacement hébergé sur un serveur.

## Utilisation et logique du projet

Vous accédez alors à l’interface Web complète de synchronisation entre **Grist**, **iObeya** et **GitHub**.

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

0. **Accéder à l'url du front**
    La page se charge et récupère via les API respectives les premières informations.
    Si vous avez enregistré précédemment les sélections dans un cookie, ces valeurs seront rechargées automatiquement. (un message s'affiche l'indiquant)

1. **Sélection des paramètres**
   - Indiquez sur quel incrément de planning (PI) la synchronisation doit s'effectuer.
   - Choisissez :
     - l’**Epic** concerné,
     - la **Room iObeya**, puis le **Board** cible. (les rooms et les boards sont chargés dynamiquement),
     - l'organisation, puis le **projet GitHub** correspondant.  (les projets sont chargés dynamiquement depuis l'organisation sélectionnée)
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

---

## Exécution en HTTPS

Le projet peut être exécuté en HTTPS sur le port 443 pour un usage sécurisé.

### Certificats

Deux modes sont possibles pour générer les certificats TLS dans le dossier `certs/` :
- **Développement local (macOS)** : via [`mkcert`](https://github.com/FiloSottile/mkcert) ou, à défaut, **OpenSSL** (auto-signé).
- **Production (VM Linux)** : via **Let's Encrypt** et `certbot`.

### Script d’automatisation

Un script `deploy/generate-certs.sh` est fourni pour automatiser la génération :
```bash
# Pour un environnement local
./deploy/generate-certs.sh localhost local

# Pour un serveur de production
sudo ./deploy/generate-certs.sh mon-domaine.fr prod
```

Les certificats `fullchain.pem` et `privkey.pem` seront créés dans le dossier `certs/` et automatiquement utilisés par Docker Compose pour le lancement HTTPS.

---

### Notes sur le script de génération de certificats

Le script `deploy/generate-certs.sh` vérifie automatiquement si le répertoire `certs/` existe.  
S'il n'est pas trouvé, il est créé avant la génération des certificats.  

> ℹ️ **Bonnes pratiques Git** : pensez à ajouter le dossier `certs/` dans votre fichier `.gitignore` pour éviter de versionner les fichiers de clés ou de certificats sensibles :
> ```bash
> certs/
> ```

---

## 🔧 Dépendances et installation

### Environnement local

Le projet utilise un environnement Python virtuel (`.venv`) pour isoler les dépendances.  
Avant de démarrer, assurez-vous d’installer toutes les bibliothèques requises :

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

### Fichier `requirements.txt`

Ce fichier contient l’ensemble des dépendances nécessaires, notamment :

```
flask
pyyaml
requests
watchdog
```

Le module **`watchdog`** est indispensable au rechargement automatique du serveur Flask lors des modifications de fichiers (`.py`, `.yaml`, `.html`).  

Si ce module n’est pas installé, vous verrez une erreur de type :
```
ModuleNotFoundError: No module named 'watchdog'
```
Dans ce cas, exécutez simplement :
```bash
pip install watchdog
```

### Docker et build d’image

Pour garantir que les dépendances soient bien installées dans le conteneur Docker,  
vérifiez que votre fichier `deploy/Dockerfile` contient les lignes suivantes :

```dockerfile
COPY . .
RUN pip install --no-cache-dir -r requirements.txt
```

Ainsi, `watchdog` (et toutes les autres dépendances) seront installés automatiquement lors du `docker compose build`.

---

💡 **Astuce :**  
Si vous développez sur macOS, il peut arriver que `watchdog` ne s’installe pas par défaut.  
Dans ce cas :

```bash
echo "watchdog" >> requirements.txt
pip install -r requirements.txt
```

Ensuite relancez le serveur avec :
```bash
python -m webapp.app
```

---

## ⚙️ Lancement rapide

### Démarrage en local
```bash
source .venv/bin/activate
python -m webapp.app
```

### Démarrage via Docker Compose
Depuis le dossier `deploy/` :
```bash
docker compose up --build
```

L’application sera alors disponible en :
- HTTPS : https://localhost  
- ou HTTP fallback (port 28080)

---

## 🧰 Dépannage (FAQ)

### ❓ *Erreur :* `No module named app`
**Cause :** Flask essaie de relancer le serveur avec `python -m app`, mais le module réel est `webapp.app`.  
**Solution :**
- Lancez toujours votre application via :
  ```bash
  python -m webapp.app
  ```
- Ou utilisez VSCode avec le `launch.json` suivant :
  ```json
  {
      "type": "python",
      "request": "launch",
      "module": "webapp.app",
      "console": "integratedTerminal"
  }
  ```

---

### ❓ *Erreur :* `KeyError: 'WERKZEUG_SERVER_FD'`
**Cause :** conflit entre le reloader interne de Flask et HTTPS.  
**Solution :**
- Cette erreur est corrigée dans la version actuelle grâce à **Watchdog**, qui remplace le reloader Flask.
- Si elle réapparaît, assurez-vous que `use_reloader=False` n’est pas activé **en même temps** que `run_with_reloader()`.

---

### ❓ *Avertissement :* `NotOpenSSLWarning` ou problème avec LibreSSL
**Cause :** macOS utilise la version de Python livrée avec Xcode (compilée avec LibreSSL).  
**Solution :**
- Installez Python via Homebrew pour bénéficier d’OpenSSL complet :
  ```bash
  brew install python@3.11
  ```
- Puis recréez votre environnement virtuel :
  ```bash
  python3.11 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  ```

---

### ❓ *Erreur :* `ModuleNotFoundError: No module named 'sync'`
**Cause :** le module `sync/` est placé à la racine et non dans `webapp/`.  
**Solution :**
Ajoutez cette ligne en haut du fichier `webapp/app.py` :
```python
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
```

---

### ❓ *Problèmes de certificat HTTPS (fichiers manquants)*
**Cause :** les certificats `fullchain.pem` et `privkey.pem` ne sont pas trouvés.  
**Solution :**
- Générez des certificats locaux :
  ```bash
  cd deploy
  ./generate-certs.sh
  ```
- Les fichiers seront créés dans `certs/`. Le serveur redémarrera automatiquement en HTTPS.
