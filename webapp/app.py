import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from flask import Flask, render_template, request, jsonify, make_response
import requests
import yaml
import os
from webapp.session_store import session_store
import uuid

from sync.sync import (
    get_grist_features,
    get_grist_epics,
    get_iobeya_features,
    get_github_features,
    compute_diff,
    synchronize_all,
)


app = Flask(__name__)

# --- Activation et configuration des logs ---
import logging

# --- Configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
app.logger.setLevel(logging.DEBUG)
logging.getLogger('werkzeug').setLevel(logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.WARNING)
print("🪵 Logging initialisé : niveau DEBUG activé pour Flask et Werkzeug")

# Load configuration from config.yaml or config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

# Configuration variables
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

##

def list_epics():
    try:
        epics = get_grist_epics(GRIST_API_URL, GRIST_DOC_ID, GRIST_API_TOKEN, GRIST_EPIC_TABLE_NAME)
        if not epics:
            app.logger.warning("⚠️ Aucune donnée reçue depuis Grist (Epics).")
            return [{"id": "error", "name": "[Erreur : aucune donnée Epics récupérée]"}]
        app.logger.info(f"✅ {len(epics)} epics récupérés depuis Grist.")
        return epics
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des Epics : {e}", exc_info=True)
        return [{"id": "error", "name": f"[Erreur récupération Epics : {str(e)}]"}]

def list_rooms():
    """
    Récupère la liste des rooms iObeya via l'API REST.
    Retourne une liste d'objets {id, name}.
    """
    iobeya_conf = config.get("iobeya", {})
    base_url = iobeya_conf.get("base_url")
    token = iobeya_conf.get("token")
    if not base_url or not token:
        app.logger.warning("⚠️ Configuration iObeya incomplète.")
        return [{"id": "none", "name": "[Erreur : configuration iObeya manquante]"}]
    
    url = f"{base_url}/s/j/rooms"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        rooms = [
            {"id": r.get("id") or r.get("roomId"), "name": r.get("name") or r.get("title")}
            for r in data if (r.get("id") or r.get("roomId")) and (r.get("name") or r.get("title"))
        ]
        app.logger.info(f"✅ {len(rooms)} rooms récupérées depuis iObeya.")
        return rooms
    except requests.RequestException as e:
        app.logger.error(f"⚠️ Erreur API iObeya (rooms) : {e}", exc_info=True)
        return [{"id": "error", "name": f"[Erreur connexion iObeya : {str(e)}]"}]

def list_boards(room_id):
    """
    Récupère la liste des boards pour une room iObeya via l'API REST.
    Retourne une liste d'objets {id, name}.
    """
    iobeya_conf = config.get("iobeya", {})
    base_url = iobeya_conf.get("base_url")
    token = iobeya_conf.get("token")
    if not base_url or not token:
        app.logger.warning("⚠️ Configuration iObeya incomplète.")
        return [{"id": "none", "name": "[Erreur : configuration iObeya manquante]"}]
    
    url = f"{base_url}/s/j/rooms/{room_id}/details"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        boards = [
            {"id": b.get("id"), "name": b.get("name")}
            for b in data if b.get("@class") == "com.iobeya.dto.BoardDTO" and b.get("id") and b.get("name")
        ]
        app.logger.info(f"✅ {len(boards)} boards récupérés depuis iObeya pour la room {room_id}.")
        return boards
    except requests.RequestException as e:
        app.logger.error(f"⚠️ Erreur API iObeya (boards) : {e}", exc_info=True)
        return [{"id": "error", "name": f"[Erreur connexion iObeya : {str(e)}]"}]



def list_organizations():
    github_conf = config.get("github", {})
    organizations = github_conf.get("organizations", [])
    org_list = []
    for org in organizations:
        org_list.append({"id": org, "name": org})
    return org_list

def list_projects(): return ["GitHub Project X", "GitHub Project Y"]

@app.before_request
def ensure_session():
    """Assure qu’un identifiant de session est présent sans interrompre le flux de requête."""
    if not request.cookies.get("session_id"):
        request.new_session_id = str(uuid.uuid4())


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

@app.route("/")
def index():
    g_list_epics = list_epics()
    req=request 
    return render_template("index.html", epics=g_list_epics,
                           rooms=list_rooms(), projects=list_projects(),
                           organizations=list_organizations())

@app.route("/verify", methods=["GET", "POST"])
def verify():
    # Defaults
    default_iobeya_board_id = None
    default_github_project_id = None

    # Read parameters from JSON (POST) or query args (GET)
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        grist_doc_id = data.get("grist_doc_id", GRIST_DOC_ID)
        grist_table = data.get("grist_table", GRIST_FEATURE_TABLE_NAME)
        iobeya_board_id = data.get("iobeya_board_id", default_iobeya_board_id)
        github_project_id = data.get("github_project_id")
        pi = data.get("pi")
        epic = data.get("epic")
        room = data.get("room")
        project = data.get("project")
        rename_deleted = data.get("rename_deleted")
    else:
        grist_doc_id = request.args.get("grist_doc_id", GRIST_DOC_ID)
        grist_table = request.args.get("grist_table", GRIST_FEATURE_TABLE_NAME)
        iobeya_board_id = request.args.get("iobeya_board_id", default_iobeya_board_id)
        github_project_id = request.args.get("github_project_id")
        pi = request.args.get("pi")
        epic = request.args.get("epic")
        room = request.args.get("room")
        project = request.args.get("project")
        rename_deleted = request.args.get("rename_deleted")
    app.logger.debug(f"Received params: grist_doc_id={grist_doc_id}, iobeya_board_id={iobeya_board_id}, github_project_id={github_project_id}, pi={pi}, epic={epic}, room={room}, project={project}, rename_deleted={rename_deleted}")

    session_id = request.cookies.get("session_id")
    session_id, session_data = session_store.get_or_create_session(session_id)

    # récupérer les features depuis grist
    
    try:
        df, last_update = get_grist_features(GRIST_API_URL, grist_doc_id, GRIST_API_TOKEN, grist_table,epic)
        session_data["grist"] = df.to_dict(orient="records") if not df.empty else []
        app.logger.info(f"✅ {len(session_data['grist'])} features récupérées depuis Grist (app.py).")
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des features Grist : {e}")
        session_data["grist"].clear()
    
    # récupérer les features depuis iObeya

    try:
        session_data["iobeya"] = get_iobeya_features(IOBEYA_API_URL, iobeya_board_id, IOBEYA_API_TOKEN,IOBEYA_TYPES_CARD_FEATURES)
        app.logger.info(f"✅ {len(session_data['iobeya'])} features récupérées depuis iObeya (app.py).")
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des features iobeya : {e}")
        session_data["iobeya"].clear()
    
    # récupérer les features depuis GitHub
    
    try:
        session_data["github"] = get_github_features(github_project_id, GITHUB_TOKEN_ENV_VAR)
        app.logger.info(f"✅ {len(session_data['github'])} features récupérées depuis GitHub (app.py).")
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des features GitHub : {e}")
        session_data["github"].clear()
        
    # récupérer les diffs
    session_data["iobeya_diff"].clear()
    session_data["github_diff"].clear()

    try:
        ### récupère la liste des epics pour filtrer les diffs en fonction de l'epic sélectionné
        g_list_epics = list_epics() 
        id_epic_value = None
        for e in g_list_epics:
            if int(e.get("id")) == int(epic):
                id_epic_value = e.get("id_epic")
                break     
        ### Calcul des diffs iObeya et GitHub vs grist
        session_data["iobeya_diff"] = compute_diff(session_data["grist"], session_data["iobeya"], rename_deleted, id_epic_value)
        app.logger.info(f"✅ {len(session_data['iobeya_diff'])} différences récupérées depuis iObeya (app.py).")
        session_data["github_diff"] = compute_diff(session_data["grist"], session_data["github"], rename_deleted, id_epic_value)
        app.logger.info(f"✅ {len(session_data['github_diff'])} différences récupérées depuis GitHub (app.py).")
        # NOTE : Pour se rappeller >> la synchronisation bidirectionnelle doit également synchroniser les features "not_present" entre iobeya et github (voir sync.py)
    except Exception as e:
        app.logger.error(f"❌ Erreur lors de la récupération des features GitHub : {e}")
        session_data["github"].clear()

    session_store.set(session_id, session_data)

    return jsonify({
        "grist": session_data["grist"],
        "iobeya": session_data["iobeya"],
        "github": session_data["github"],
        "iobeya_diff": session_data["iobeya_diff"],
        "github_diff": session_data["github_diff"]
    })

@app.route("/sync", methods=["POST"])
def sync():
    # Récupérer explicitement les paramètres nécessaires
    if request.method == "POST":
        data = request.get_json(silent=True) or request.form or {}
        iobeya_board_id = data.get("iobeya_board_id")
        github_project_id = data.get("github_project_id")
        epic_id = data.get("epic_id")
        rename_deleted = data.get("rename_deleted")
        force_overwrite = data.get("force_overwrite")
        pi = data.get("pi")
    else:
        iobeya_board_id = request.args.get("iobeya_board_id")
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
        "doc_id": GRIST_DOC_ID,
        "api_token": GRIST_API_TOKEN,
        "feature_table_name": GRIST_FEATURE_TABLE_NAME
    }

    iobeya_params = {
        "api_url": IOBEYA_API_URL,
        "board_id": iobeya_board_id,
        "api_token": IOBEYA_API_TOKEN
    }

    github_params = {
        "project_id": github_project_id,
        "token_env_var": GITHUB_TOKEN_ENV_VAR
    }

    session_id = request.cookies.get("session_id")
    _, session_data = session_store.get_or_create_session(session_id)

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

@app.route("/github-projects")
def github_projects():
    org_name = request.args.get("org")
    if not org_name:
        return jsonify({"error": "Paramètre 'org' manquant"}), 400
    
    if not GITHUB_TOKEN_ENV_VAR:
        app.logger.error("❌ Token GitHub manquant ou non défini dans l'environnement")
        return jsonify({"error": "Token GitHub manquant ou non défini dans l'environnement"}), 401

    # --- Requête GraphQL pour les ProjectsV2 ---
    graphql_query = {
        "query": f"""
        query {{
          organization(login: "{org_name}") {{
            projectsV2(first: 20) {{
              nodes {{
                id
                title
                shortDescription
                number
              }}
            }}
          }}
        }}
        """
    }

    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN_ENV_VAR}",
        "Accept": "application/vnd.github+json"
    }

    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json=graphql_query,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        # Extraire les projets
        org_data = data.get("data", {}).get("organization")
        if not org_data:
            app.logger.warning(f"⚠️ Aucune organisation trouvée : {org_name}")
            return jsonify([])

        projects = org_data.get("projectsV2", {}).get("nodes", [])
        project_list = [
            {
                "id": p.get("id"),
                "name": p.get("title"),
                "description": p.get("shortDescription"),
                "number": p.get("number")
            }
            for p in projects
        ]

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
    boards = list_boards(room_id)
    return jsonify(boards)

# --- Endpoint de supervision ---
@app.route("/healthz")
def healthz():
    """Endpoint de supervision – retourne 200 si tout est OK, 412 sinon."""
    checks = {
        "grist": bool(GRIST_API_URL and GRIST_API_TOKEN),
        "iobeya": bool(IOBEYA_API_URL and IOBEYA_API_TOKEN),
        "github": bool(GITHUB_TOKEN_ENV_VAR),
    }
    ok = all(checks.values())
    status_code = 200 if ok else 412
    response = {
        "ok": ok,
        "checks": checks,
        "version": "0.9.0-alpha"
    }
    app.logger.info(f"🩺 Health check: {response}")
    return jsonify(response), status_code

# --- Vérification de clés d'accès sécurisées ---
# Pour activer la protection, ajouter une ou plusieurs clés dans le fichier config.yaml :

#
# Vous pouvez également définir une clé unique via la variable d'environnement ACCESS_KEY
security_conf = config.get("security", {})
ACCESS_KEYS = security_conf.get("access_keys", [])
env_key = os.getenv("ACCESS_KEY")
if env_key:
    ACCESS_KEYS.append(env_key)


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
    def __init__(self, paths):
        super().__init__()
        self.paths = paths

    def on_any_event(self, event):
        if event.is_directory:
            return

        # 🔒 Ignore fichiers temporaires ou compilés
        ignored = [".pyc", ".tmp", ".log"]
        ignored_dirs = ["__pycache__", ".venv", "certs"]

        if any(event.src_path.endswith(ext) for ext in ignored):
            return
        if any(d in event.src_path for d in ignored_dirs):
            return

        # 🔁 Redémarrage uniquement sur fichiers utiles
        if any(event.src_path.endswith(ext) for ext in [".py", ".yaml", ".html"]):
            app.logger.info(f"♻️ Fichier modifié : {event.src_path} → redémarrage du serveur...")
            os.execv(sys.executable, ["python"] + sys.argv)

def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("0.0.0.0", port)) != 0

import threading
import time
import argparse

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Lancement du serveur Flask avec ou sans Watchdog.")
    parser.add_argument("--dev", action="store_true", help="Active le mode développement (rechargement automatique Watchdog).")
    args = parser.parse_args()

    cert_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "../certs"))
    cert_file = os.path.join(cert_dir, "fullchain.pem")
    key_file = os.path.join(cert_dir, "privkey.pem")

    ssl_ctx = (cert_file, key_file) if os.path.exists(cert_file) and os.path.exists(key_file) else None
    active_port = 443 if ssl_ctx and is_port_available(443) else 8443 if ssl_ctx else 28080

    app.logger.info(f"🚀 Lancement Flask sur le port {active_port} {'(HTTPS)' if ssl_ctx else '(HTTP)'}")
    app.logger.info(f"🔧 Mode développement : {'activé' if args.dev else 'désactivé'}")

    # --- Fonction pour démarrer Watchdog dans un thread séparé ---
    def start_watcher():
        observer = Observer()
        handler = ReloadOnChange(["webapp", "."])
        observer.schedule(handler, path=".", recursive=True)
        observer.start()
        app.logger.info("👀 Watchdog activé (surveillance des fichiers).")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()

    # --- Lancement conditionnel du thread Watchdog ---
    if args.dev:
        watcher_thread = threading.Thread(target=start_watcher, daemon=True)
        watcher_thread.start()

    # --- Lancement du serveur Flask (thread principal) ---
    try:
        app.run(
            host="0.0.0.0",
            port=active_port,
            debug=args.dev,
            ssl_context=ssl_ctx,
            use_reloader=False
        )
    except Exception as e:
        app.logger.error(f"❌ Erreur au démarrage du serveur Flask : {e}")
