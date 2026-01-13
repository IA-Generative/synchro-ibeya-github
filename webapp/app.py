import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from flask import Flask, render_template, request, jsonify
import requests
import yaml
import uuid
import logging
import pandas as pd
import math

# session_store peut être importé soit via le package webapp (si webapp est un package),
# soit directement depuis le répertoire courant (si app.py est exécuté comme script).
# En dernier recours (si le fichier n'existe pas dans le projet), on fallback sur un store mémoire.
try:
    from webapp.session_store import session_store  # type: ignore
except ModuleNotFoundError:
    try:
        from session_store import session_store  # type: ignore
    except ModuleNotFoundError:
        class _InMemorySessionStore:
            """Fallback minimal pour éviter un crash au démarrage.

            ⚠️ Non persistant : les sessions sont perdues au redémarrage.
            """

            def __init__(self):
                self._store = {}

            def get_or_create_session(self, session_id):
                if not session_id:
                    session_id = str(uuid.uuid4())
                data = self._store.get(session_id)
                if data is None:
                    data = {
                        "grist_doc_id": None,
                        "grist": [],
                        "iobeya": [],
                        "github": [],
                        "iobeya_diff": [],
                        "github_diff": [],
                    }
                    self._store[session_id] = data
                return session_id, data

            def set(self, session_id, data):
                self._store[session_id] = data

        session_store = _InMemorySessionStore()

## Import des fonctions de synchronisation des différents services

from sync.sync import (
    compute_diff,
    synchronize_all
)

from sync.sync_grist import (
    grist_get_doc_name,
    grist_get_epics,
    grist_get_epic_objects,
    grist_get_epic
)
from sync.sync_iobeya import (
    iobeya_get_rooms,
    iobeya_get_boards,
    iobeya_get_board_objects
)

from sync.sync_github import (
    github_get_organizations,
    github_get_projects,
    github_get_project_objects
)

# --- Initialisation de l'application Flask ---

app = Flask(__name__)

# --- Activation et configuration des logs ---

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
app.logger.setLevel(logging.INFO)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)
logging.getLogger("watchdog").setLevel(logging.WARNING)
logging.getLogger("watchdog.observers").setLevel(logging.WARNING)
print("🪵 Logging initialisé : niveau WARNING activé pour Flask et Werkzeug")

# --- JSON-safe helpers ---

def _json_safe(value):
    """Convert values that are not valid JSON (NaN/Inf, pandas NA) to JSON-safe equivalents."""
    try:
        # pandas missing values
        if value is pd.NA:
            return None
    except Exception:
        pass

    # floats: NaN/Inf are not valid JSON
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    # pandas / numpy scalars sometimes appear in dicts
    try:
        if hasattr(value, "item") and callable(value.item):
            return _json_safe(value.item())
    except Exception:
        pass

    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, tuple):
        return [_json_safe(v) for v in value]

    return value


def df_to_records_jsonsafe(df):
    """Convert a pandas DataFrame to JSON-safe list of records (no NaN/Inf)."""
    if df is None:
        return []
    try:
        if hasattr(df, "empty") and df.empty:
            return []
        # Replace pandas missing values and numpy.nan with None
        df2 = df.copy()
        df2 = df2.where(pd.notnull(df2), None)
        return _json_safe(df2.to_dict(orient="records"))
    except Exception:
        # Fallback: best-effort conversion
        try:
            return _json_safe(df.to_dict(orient="records"))
        except Exception:
            return []

# Load configuration from config.yaml or config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

# --- Configuration variables

# Grist configuration

grist_conf = config.get("grist", {})
GRIST_API_URL = grist_conf.get("api_url", "")
GRIST_API_TOKEN = grist_conf.get("api_token", "")
GRIST_DOC_ID = grist_conf.get("default_doc_id", "")
GRIST_TABLE_NAME = grist_conf.get("default_table", "Features")
GRIST_EPIC_TABLE_NAME = grist_conf.get("default_epic_table", "Epics")
GRIST_FEATURE_TABLE_NAME = grist_conf.get("default_feature_table", "Features")

# iObeya configuration
iobeya_conf = config.get("iobeya", {})
IOBEYA_API_URL = iobeya_conf.get("base_url", "")
IOBEYA_API_TOKEN = iobeya_conf.get("token", "")
IOBEYA_TYPES_CARD_FEATURES = iobeya_conf.get("types_card_features", [])

# GitHub configuration
github_conf = config.get("github", {})
GITHUB_TOKEN_ENV_VAR = github_conf.get("token_env_var", "")
GITHUB_ORGANIZATIONS = github_conf.get("organizations", [])

# --- Allowed object types for diffing (explicit allowlists)
IOBEYA_ALLOWED_OBJECT_TYPES = {
    "Features",
    "Risques",
    "Objectives",
    "Dependances",
    "Issues"
}

GITHUB_ALLOWED_OBJECT_TYPES = {
    "Features",
    "Issues"
}

# --- Vérification de clés d'accès sécurisées à l'application ---

# L'accès aux endpoints non publics nécessite une clé d'accès valide
# Au vu du peu d'utilisateurs attendus, une liste statique de clés est suffisante
# La gestion d'accès se fait via un cookie sécurisé ou un paramètre de requête `key`
# Note : une clé unique peux être définie également via la variable d'environnement ACCESS_KEY
# ce qui permet de l'intégrer facilement dans des environnements cloud ou conteneurisés

security_conf = config.get("security", {})
ACCESS_KEYS = security_conf.get("access_keys", [])
env_key = os.getenv("ACCESS_KEY")
if env_key:
    ACCESS_KEYS.append(env_key)

# --- Gestion des sessions utilisateurs ---

@app.before_request
def ensure_session():
    """Assure qu’un identifiant de session est présent sans interrompre le flux de requête."""
    if not request.cookies.get("session_id"):
        request.new_session_id = str(uuid.uuid4())

@app.before_request
def verify_access_key():
    """Vérifie qu'une des clés d'accès valides est transmise ou stockée dans un cookie sécurisé,
    sauf pour les routes publiques et les fichiers statiques."""
    
    # --- Routes publiques ou statiques ---
    public_paths = [
        "/", "/healthz", "/favicon.ico",
        "/static/", "/verify", "/sync",
        "/github-projects", "/iobeya-boards"
    ]
    
    # Autorise toutes les routes qui commencent par /static/ ou correspondent à la liste blanche
    if any(request.path.startswith(p) for p in public_paths):
        return  # pas de vérification
    
    cookie_key = request.cookies.get("access_key")
    query_key = request.args.get("key")

    # Si une clé est passée dans la requête et qu'elle est valide, on la marque pour ajout ultérieur
    if query_key in ACCESS_KEYS:
        request.valid_access_key = query_key
        return  # on continue la requête

    # Si aucune clé valide n'est trouvée (ni cookie, ni query)
    if cookie_key not in ACCESS_KEYS:
        app.logger.warning(f"🚫 Clé d'accès invalide ou absente sur {request.path}")
        return jsonify({"error": "Access denied: invalid or missing key"}), 403

@app.after_request
def add_session_cookie(response):
    """Ajoute le cookie de session si nécessaire après la génération de la réponse."""
    if hasattr(request, "new_session_id"):
        response.set_cookie(
            "session_id",
            request.new_session_id,
            httponly=True,
            secure=True,
            samesite="None"  # nécessaire pour fonctionnement dans un iframe (ex : widget Grist)
        )
    return response

@app.after_request
def add_access_cookie(response):
    """Ajoute le cookie de clé d'accès si une clé valide a été passée dans la requête."""
    if hasattr(request, "valid_access_key"):
        response.set_cookie(
            "access_key",
            request.valid_access_key,
            httponly=True,
            secure=True,
            samesite="None"  # nécessaire pour utilisation en iframe (ex: widget Grist)
        )
    return response

# --- Endpoint de supervision pour kubernetes---

@app.route("/healthz")
def healthz():
    
    """Healthcheck ultra simple : 200 si la config minimale est présente, sinon 412."""

    checks = {
        "grist": bool(GRIST_API_URL and GRIST_API_TOKEN and GRIST_DOC_ID),
        "iobeya": bool(IOBEYA_API_URL and IOBEYA_API_TOKEN),
        "github": bool(GITHUB_TOKEN_ENV_VAR),
        "access_keys": bool(ACCESS_KEYS),
    }

    ok = all(checks.values())
    return jsonify({"ok": ok, "checks": checks, "version": "0.9.0-alpha"}), (200 if ok else 412)

#############    Endpoints principaux de l'application  ###########

@app.route("/")
def index():
    
    # Lire doc_id depuis la query string, ou fallback sur les préférences
    doc_id_param = request.args.get("doc_id", "").strip()
    grist_doc_id = doc_id_param or GRIST_DOC_ID
    app.logger.debug(f"📘 Doc Grist actif : {grist_doc_id}")
    doc_name = grist_get_doc_name(GRIST_API_URL, grist_doc_id, GRIST_API_TOKEN)
    grist_display_name = f"📘 Grist – {doc_name}"
    grist_display_id = f"( Doc id : {grist_doc_id} )"
    
    # récuperation de la liste des epics pour l'affichage
    g_list_epics = grist_get_epics(GRIST_API_URL, grist_doc_id, GRIST_API_TOKEN)
    organizations=github_get_organizations(GITHUB_ORGANIZATIONS)
    rooms=iobeya_get_rooms(IOBEYA_API_URL, IOBEYA_API_TOKEN)
        
    # Création/stockage session + grist_doc_id
    session_id = request.cookies.get("session_id")
    session_id, session_data = session_store.get_or_create_session(session_id)
    session_data["grist_doc_id"] = grist_doc_id
    session_store.set(session_id, session_data)

    return render_template(
        "index.html",
        epics=g_list_epics,
        rooms=rooms,
        organizations=organizations,
        projects=None,
        grist_display_name=grist_display_name,
        grist_display_id=grist_display_id
    )

@app.route("/github-projects")
def github_projects():
    org_name = request.args.get("org")
    
    if not org_name or not GITHUB_TOKEN_ENV_VAR:
        app.logger.error("❌ Token GitHub manquant ou non défini dans l'environnement")
        return jsonify({"error": "Token GitHub manquant ou non défini dans l'environnement"}), 401
    
    try:
        project_list = github_get_projects(GITHUB_TOKEN_ENV_VAR, org_name)
        app.logger.info(f"✅ {len(project_list)} projets récupérés pour {org_name}.")
        return jsonify(project_list)

    except requests.RequestException as e:
        app.logger.error(f"⚠️ Erreur API GitHub GraphQL : {e}")
        return jsonify({"error": f"Échec de la récupération des projets : {e}"}), 500

@app.route("/iobeya-boards")
def iobeya_boards():
    room_id = request.args.get("room_id")
    if not room_id:
        return jsonify({"error": "Paramètre 'room_id' manquant"}), 400
    
    boards = iobeya_get_boards(room_id)
    return jsonify(boards)

###########    Endpoint de vérification et synchronisation  ###########

@app.route("/prepare", methods=["GET", "POST"])
def verify():
    
    # Vérification session_id et récupération grist_doc_id depuis la session
    session_id = request.cookies.get("session_id")
    if not session_id:
        return jsonify({"error": "Session non trouvée ou invalide"}), 400
    session_id, session_data = session_store.get_or_create_session(session_id)
    grist_doc_id = session_data.get("grist_doc_id") or GRIST_DOC_ID
    
    # ⚠️ Fallback au GRIST_DOC_ID par défaut si aucune session active n'a été trouvée
    
    if grist_doc_id == GRIST_DOC_ID:
        app.logger.warning(f"⚠️ Aucun doc_id actif trouvé en session. Utilisation du GRIST_DOC_ID par défaut : {grist_doc_id} .")

    # Lire doc_id depuis la query string ou POST, ou fallback sur la session/config
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        doc_id_param = data.get("doc_id", "").strip()
        if doc_id_param:
            grist_doc_id = doc_id_param
        iobeya_board_id = data.get("iobeya_board_id", None)
        #iobeya_container_id = data.get("iobeya_container_id", None)
        #iobeya_room_id = data.get("iobeya_room_id", None)
        github_project_id = data.get("github_project_id")
        pi = data.get("pi")
        epic = data.get("epic")
        room = data.get("room")
        project = data.get("project")
        rename_deleted = data.get("rename_deleted")
    else:
        doc_id_param = request.args.get("doc_id", "").strip()
        if doc_id_param:
            grist_doc_id = doc_id_param
        iobeya_board_id = request.args.get("iobeya_board_id", default_iobeya_board_id)
        #iobeya_container_id = request.args.get("iobeya_container_id", None)
        #iobeya_room_id = request.args.get("iobeya_room_id", None)  
        github_project_id = request.args.get("github_project_id")
        pi = request.args.get("pi")
        epic = request.args.get("epic")
        room = request.args.get("room")
        project = request.args.get("project")
        rename_deleted = request.args.get("rename_deleted")
        
    app.logger.debug(f"📘 Doc Grist actif : {grist_doc_id}")
    app.logger.debug(f"Received params: grist_doc_id={grist_doc_id}, iobeya_board_id={iobeya_board_id}, github_project_id={github_project_id}, pi={pi}, epic={epic}, room={room}, project={project}, rename_deleted={rename_deleted}")

    # session_id et session_data déjà récupérés plus haut
    session_data["grist_doc_id"] = grist_doc_id

    # récupérer les objets depuis grist
    
    try:
        epic_obj = grist_get_epic(GRIST_API_URL, grist_doc_id, GRIST_API_TOKEN, epic )       
        df = grist_get_epic_objects(GRIST_API_URL, grist_doc_id, GRIST_API_TOKEN, epic, pi or 0)
        session_data["grist"] = df_to_records_jsonsafe(df)
        app.logger.info(f" >> ✅ {len(session_data['grist'])} objets récupérées depuis Grist (app.py).")
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des features Grist : {e}")
        session_data["grist"].clear()

    # récupérer les objets depuis iObeya
    try:
        df = iobeya_get_board_objects(IOBEYA_API_URL, iobeya_board_id, IOBEYA_API_TOKEN, IOBEYA_TYPES_CARD_FEATURES)
        session_data["iobeya"] = df_to_records_jsonsafe(df)
        app.logger.info(f" >>✅ {len(session_data['iobeya'])} objets récupérées depuis iObeya (app.py).")
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des features iobeya : {e}")
        session_data["iobeya"].clear()

    # récupérer les objets depuis GitHub
    try:
        # `GITHUB_TOKEN_ENV_VAR` contient le nom de la variable d'environnement (ex: "GITHUB_TOKEN")
        github_objects = github_get_project_objects(github_project_id, GITHUB_TOKEN_ENV_VAR)
        if isinstance(github_objects, list):
            session_data["github"] = _json_safe(github_objects)
        else:
            # Compat: si la fonction renvoie un DataFrame à l'avenir
            df = github_objects
            session_data["github"] = df_to_records_jsonsafe(df)
        app.logger.info(f" >>✅ {len(session_data['github'])} objets récupérés depuis GitHub (app.py).")  
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des objets GitHub : {e}")
        session_data["github"].clear()

    # récupérer les diffs
    
    session_data["iobeya_diff"].clear()
    session_data["github_diff"].clear()

    try:
        # récupère la liste des epics pour filtrer les diffs en fonction de l'epic sélectionné
        id_epic_value = grist_get_epic(GRIST_API_URL,grist_doc_id,GRIST_API_TOKEN,epic,"Epics")

        # Calcul des diffs iObeya et GitHub vs grist
        session_data["iobeya_diff"] = compute_diff(
            session_data["grist"],
            session_data["iobeya"],
            rename_deleted,
            epic_obj,
            allowed_types=IOBEYA_ALLOWED_OBJECT_TYPES,
        )
        app.logger.info(f"✅ {len(session_data['iobeya_diff'])} différences récupérées depuis iObeya (app.py).")
        session_data["github_diff"] = compute_diff(
            session_data["grist"],
            session_data["github"],
            rename_deleted,
            epic_obj,
            allowed_types=GITHUB_ALLOWED_OBJECT_TYPES,
        )
        app.logger.info(f"✅ {len(session_data['github_diff'])} différences récupérées depuis GitHub (app.py).")
        # NOTE : Pour se rappeller >> la synchronisation bidirectionnelle doit également synchroniser les features "not_present" entre iobeya et github (voir sync.py)
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des features GitHub : {e}")
        session_data["github"].clear()

    session_store.set(session_id, session_data)

    return jsonify({
        "grist": _json_safe(session_data["grist"]),
        "iobeya": _json_safe(session_data["iobeya"]),
        "github": _json_safe(session_data["github"]),
        "iobeya_diff": _json_safe(session_data["iobeya_diff"]),
        "github_diff": _json_safe(session_data["github_diff"])
    })

@app.route("/sync", methods=["POST"])
def sync():
    # Vérification session_id et récupération grist_doc_id depuis la session
    session_id = request.cookies.get("session_id")
    if not session_id:
        return jsonify({"error": "Session non trouvée ou invalide"}), 400
    session_id, session_data = session_store.get_or_create_session(session_id)
    grist_doc_id = session_data.get("grist_doc_id") or GRIST_DOC_ID
    # ⚠️ Fallback au GRIST_DOC_ID par défaut si aucune session active n'a été trouvée
    if grist_doc_id == GRIST_DOC_ID:
        app.logger.warning("⚠️ Aucun doc_id actif trouvé en session. Utilisation du GRIST_DOC_ID par défaut.")

    # Récupérer explicitement les paramètres nécessaires
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        iobeya_board_id = data.get("iobeya_board_id")
        iobeya_container_id = data.get("iobeya_container_id")
        iobeya_room_id = data.get("iobeya_room_id")
        github_project_id = data.get("github_project_id")
        epic_id = data.get("epic_id")
        rename_deleted = data.get("rename_deleted")
        force_overwrite = data.get("force_overwrite")
        pi = data.get("pi")
    else:
        iobeya_board_id = request.args.get("iobeya_board_id")
        iobeya_container_id = request.args.get("iobeya_container_id")
        iobeya_room_id = request.args.get("iobeya_room_id")
        github_project_id = request.args.get("github_project_id")
        epic_id = request.args.get("epic_id")
        rename_deleted = request.args.get("rename_deleted")
        force_overwrite = request.args.get("force_overwrite")
        pi = request.args.get("pi")

    app.logger.debug("🔁 Paramètres reçus pour synchronisation :")
    app.logger.debug(f"  iobeya_board_id = {iobeya_board_id}")
    app.logger.debug(f"  github_project_id = {github_project_id}")
    app.logger.debug(f"  epic_id = {epic_id}")
    app.logger.debug(f"  rename_deleted = {rename_deleted}")
    app.logger.debug(f"  force_overwrite = {force_overwrite}")
    app.logger.debug(f"  pi = {pi}")

    grist_params = {
        "api_url": GRIST_API_URL,
        "doc_id": grist_doc_id,
        "api_token": GRIST_API_TOKEN,
        "feature_table_name": GRIST_FEATURE_TABLE_NAME
    }

    iobeya_params = {
        "api_url": IOBEYA_API_URL,
        "board_id": iobeya_board_id,
        "container_id": iobeya_container_id,
        "room_id": iobeya_room_id,
        "api_token": IOBEYA_API_TOKEN
    }

    github_params = {
        "project_id": github_project_id,
        "token_env_var": GITHUB_TOKEN_ENV_VAR
    }

    # Met à jour le grist_doc_id actif dans le contexte avant synchronisation
    session_data["grist_doc_id"] = data.get("doc_id") if request.method == "POST" and data.get("doc_id") else grist_doc_id

    # Update sync_context with parameters from request
    session_data["epic_id"] = epic_id
    session_data["rename_deleted"] = rename_deleted
    session_data["force_overwrite"] = force_overwrite
    session_data["pi"] = pi

    # Appel effectif à synchronize_all avec les dictionnaires de paramètres
    result = synchronize_all(
        grist_params,
        iobeya_params,
        github_params,
        session_data
    )

    return jsonify({
        "status": "ok",
        "iobeya_board_id": iobeya_board_id,
        "github_project_id": github_project_id,
        "epic_id": epic_id,
        "rename_deleted": rename_deleted,
        "force_overwrite": force_overwrite,
        "pi": pi,
        "result": result
    })



# --- Lancement de l'application ---
# Par défaut, l'application est configurée pour être servie en HTTPS.
# Pour passer à HTTP uniquement (sans chiffrement), commentez la ligne HTTPS et décommentez celle avec "app.run" ci-dessous.
# Exemple :
# 🔒 HTTPS (recommandé pour usage en production ou intégration dans Grist)
# 🔓 HTTP (développement local sans certificats)
#
# HTTPS : nécessite la présence de fichiers "fullchain.pem" et "privkey.pem" dans le dossier ../certs/
# Ces fichiers peuvent être générés via le script "deploy/generate-certs.sh".


# --- Bloc principal robuste avec watchdog pour reload automatique ---
import socket
import subprocess
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ReloadOnChange(FileSystemEventHandler):
    def __init__(self, on_change, paths=None):
        super().__init__()
        self.on_change = on_change
        self.paths = paths or []

    def on_any_event(self, event):
        if event.is_directory:
            return

        # --- Filtrage POSITIF : on ne surveille que webapp/ et sync/ ---
        src = os.path.abspath(event.src_path)
        project_root = os.getcwd()
        allowed_roots = (
            os.path.join(project_root, "webapp"),
            os.path.join(project_root, "sync"),
        )

        if not src.startswith(allowed_roots):
            return

        # 🔒 Ignore fichiers temporaires ou non pertinents
        if src.endswith((".pyc", ".tmp", ".log")):
            return

        # 🔁 Redémarrage uniquement sur fichiers utiles
        if any(event.src_path.endswith(ext) for ext in [".py", ".yaml", ".html"]):
            app.logger.info(f"♻️ Fichier modifié : {event.src_path} → redémarrage du serveur...")
            try:
                self.on_change(event.src_path)
            except Exception as e:
                app.logger.error(f"❌ Échec du redémarrage après modification de {event.src_path} : {e}")

def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("0.0.0.0", port)) != 0

import threading
import time
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lancement du serveur Flask avec ou sans Watchdog.")
    parser.add_argument("--dev", action="store_true", help="Active le mode développement (watchdog parent + serveur enfant redémarré).")
    # Interne : lance uniquement le serveur Flask (pas de watchdog)
    parser.add_argument("--runserver", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    cert_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../certs"))
    cert_file = os.path.join(cert_dir, "fullchain.pem")
    key_file = os.path.join(cert_dir, "privkey.pem")

    ssl_ctx = (cert_file, key_file) if os.path.exists(cert_file) and os.path.exists(key_file) else None

    # En mode debug/dev, on force un port non privilégié et stable (8443).
    # Si le port est déjà utilisé, on échoue explicitement : on ne change pas de port en dev.
    if args.dev and not args.runserver:
        active_port = 8443
        if not is_port_available(active_port):
            raise RuntimeError(
                f"Port {active_port} déjà utilisé. Arrête l'autre process (ou libère le port) puis relance."
            )
    else:
        # Mode serveur (enfant) ou mode non-dev : logique existante
        active_port = args.port or (443 if ssl_ctx and is_port_available(443) else 8443 if ssl_ctx else 28080)

    def run_flask_server(port: int, debug: bool):
        """Lance uniquement le serveur Flask (process enfant en dev)."""
        app.logger.info(f"🚀 (server) Flask sur le port {port} {'(HTTPS)' if ssl_ctx else '(HTTP)'}")
        app.run(
            host="0.0.0.0",
            port=port,
            debug=debug,
            ssl_context=ssl_ctx,
            use_reloader=False,
        )

    def spawn_server_process(port: int, debug: bool):
        """Démarre le serveur Flask comme sous-processus (pour permettre un restart propre et même port)."""
        cmd = [sys.executable, __file__, "--runserver", "--port", str(port)]
        if debug:
            cmd.append("--debug")
        app.logger.info(f"🧪 (watcher) Démarrage serveur enfant: {' '.join(cmd)}")
        # Nouveau process group pour pouvoir terminer proprement l'enfant
        return subprocess.Popen(cmd, preexec_fn=os.setsid)

    def stop_server_process(proc: subprocess.Popen):
        import signal
        if proc is None:
            return
        if proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=5)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass

    # --- Mode enfant : on lance seulement Flask ---
    if args.runserver:
        run_flask_server(active_port, debug=args.debug)
        sys.exit(0)

    # --- Mode dev : watchdog (parent) + serveur enfant redémarré proprement sur le même port ---
    if args.dev:
        import signal

        server_proc = {"proc": spawn_server_process(active_port, debug=True)}

        def restart_server(_changed_path: str):
            app.logger.info("♻️ (watcher) Restart demandé, arrêt du serveur enfant...")
            stop_server_process(server_proc["proc"])
            app.logger.info("♻️ (watcher) Redémarrage du serveur enfant...")
            server_proc["proc"] = spawn_server_process(active_port, debug=True)

        observer = Observer()
        handler = ReloadOnChange(restart_server, ["webapp", "sync"])

        # Ne surveille QUE les répertoires utiles (évite le bruit .git, caches, etc.)
        watch_roots = [
            os.path.join(os.getcwd(), "webapp"),
            os.path.join(os.getcwd(), "sync"),
        ]
        for root in watch_roots:
            if os.path.isdir(root):
                observer.schedule(handler, path=root, recursive=True)

        observer.start()
        app.logger.info("👀 Watchdog activé (parent). Surveillance limitée à webapp/ et sync/.")

        try:
            while True:
                # Si le serveur enfant meurt, on le relance.
                if server_proc["proc"].poll() is not None:
                    app.logger.warning("⚠️ (watcher) Serveur enfant arrêté. Relance...")
                    server_proc["proc"] = spawn_server_process(active_port, debug=True)
                time.sleep(1)
        except KeyboardInterrupt:
            app.logger.info("🛑 Arrêt demandé (Ctrl+C).")
        finally:
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception:
                pass
            stop_server_process(server_proc["proc"])
        sys.exit(0)

    # --- Mode non-dev : lancement direct dans le process courant ---
    try:
        run_flask_server(active_port, debug=False)
    except Exception as e:
        app.logger.error(f"❌ Erreur au démarrage du serveur Flask : {e}")
