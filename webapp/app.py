from flask import Flask, render_template, request, jsonify, make_response
import requests
import yaml
import os
from sync.sync import get_grist_features, get_grist_epics, get_iobeya_features, get_github_features, compute_diff, synchronize_all  # si déjà dans ce fichier, pas besoin du point
from webapp.session_store import session_store
import uuid


app = Flask(__name__)

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
    epics = get_grist_epics(GRIST_API_URL, GRIST_DOC_ID, GRIST_API_TOKEN, GRIST_EPIC_TABLE_NAME)
    return ["[Erreur lors de la récupération des données Epics]"] if not epics else epics

def list_rooms():
    """
    Récupère la liste des rooms iObeya via l'API REST.
    Retourne une liste d'objets {id, name}.
    """
    iobeya_conf = config.get("iobeya", {})
    base_url = iobeya_conf.get("base_url")
    token = iobeya_conf.get("token")
    if not base_url or not token:
        print("⚠️ Configuration iObeya incomplète.")
        return [{"id": "none", "name": "[Erreur config iObeya]"}]
    
    url = f"{base_url}/s/j/rooms"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        rooms = []
        for room in data:
            room_id = room.get("id") or room.get("roomId")
            room_name = room.get("name") or room.get("title")
            if room_id and room_name:
                rooms.append({"id": room_id, "name": room_name})

        print(f"✅ {len(rooms)} rooms récupérées depuis iObeya.")
        return rooms

    except requests.RequestException as e:
        print(f"⚠️ Erreur API iObeya : {e}")
        return [{"id": "error", "name": "[Erreur connexion iObeya]"}]

def list_boards(room_id):
    """
    Récupère la liste des boards pour une room iObeya via l'API REST.
    Retourne une liste d'objets {id, name}.
    """
    iobeya_conf = config.get("iobeya", {})
    base_url = iobeya_conf.get("base_url")
    token = iobeya_conf.get("token")
    if not base_url or not token:
        print("⚠️ Configuration iObeya incomplète.")
        return [{"id": "none", "name": "[Erreur config iObeya]"}]
    
    url = f"{base_url}/s/j/rooms/{room_id}/details"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        boards = []
        for board in data:
            if board.get("@class") == "com.iobeya.dto.BoardDTO":
                board_id = board.get("id")
                board_name = board.get("name")
                if board_id and board_name:
                    boards.append({"id": board_id, "name": board_name})

        print(f"✅ {len(boards)} boards récupérés depuis iObeya pour la room {room_id}.")
        return boards

    except requests.RequestException as e:
        print(f"⚠️ Erreur API iObeya (boards) : {e}")
        return [{"id": "error", "name": "[Erreur connexion iObeya]"}]



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
    """Assure qu’un identifiant de session est présent."""
    if not request.cookies.get("session_id"):
        session_id = str(uuid.uuid4())
        resp = make_response()
        resp.set_cookie("session_id", session_id, httponly=True)
        return resp

@app.route("/")
def index():
    g_list_epics = list_epics()
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

    print(f"Received params: grist_doc_id={grist_doc_id}, iobeya_board_id={iobeya_board_id}, github_project_id={github_project_id}, pi={pi}, epic={epic}, room={room}, project={project}, rename_deleted={rename_deleted}")

    session_id = request.cookies.get("session_id")
    session_id, session_data = session_store.get_or_create_session(session_id)

    # récupérer les features depuis grist
    
    try:
        df, last_update = get_grist_features(GRIST_API_URL, grist_doc_id, GRIST_API_TOKEN, grist_table,epic)
        session_data["grist"] = df.to_dict(orient="records") if not df.empty else []
        print(f"✅ {len(session_data['grist'])} features récupérées depuis Grist (app.py).")
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des features Grist : {e}")
        session_data["grist"].clear()
    
    # récupérer les features depuis iObeya

    try:
        session_data["iobeya"] = get_iobeya_features(IOBEYA_API_URL, iobeya_board_id, IOBEYA_API_TOKEN,IOBEYA_TYPES_CARD_FEATURES)
        print(f"✅ {len(session_data['iobeya'])} features récupérées depuis iObeya (app.py).")
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des features iobeya : {e}")
        session_data["iobeya"].clear()
    
    # récupérer les features depuis GitHub
    
    try:
        session_data["github"] = get_github_features(github_project_id, GITHUB_TOKEN_ENV_VAR)
        print(f"✅ {len(session_data['github'])} features récupérées depuis GitHub (app.py).")
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des features GitHub : {e}")
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
        print(f"✅ {len(session_data['iobeya_diff'])} différences récupérées depuis iObeya (app.py).")
        
        session_data["github_diff"] = compute_diff(session_data["grist"], session_data["github"], rename_deleted, id_epic_value)
        print(f"✅ {len(session_data['github_diff'])} différences récupérées depuis GitHub (app.py).")

        # NOTE : Pour se rappeller >> la synchronisation bidirectionnelle doit également synchroniser les features "not_present" entre iobeya et github (voir sync.py)

    except Exception as e:
        print(f"❌ Erreur lors de la récupération des features GitHub : {e}")
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

    print("🔁 Paramètres reçus pour synchronisation :")
    print(f"  iobeya_board_id = {iobeya_board_id}")
    print(f"  github_project_id = {github_project_id}")
    print(f"  epic_id = {epic_id}")
    print(f"  rename_deleted = {rename_deleted}")
    print(f"  force_overwrite = {force_overwrite}")
    print(f"  pi = {pi}")

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
        print("❌ Token GitHub manquant ou non défini dans l'environnement")
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
            print(f"⚠️ Aucune organisation trouvée : {org_name}")
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

        print(f"✅ {len(project_list)} projets récupérés pour {org_name}.")
        return jsonify(project_list)

    except requests.RequestException as e:
        print(f"⚠️ Erreur API GitHub GraphQL : {e}")
        return jsonify({"error": f"Échec de la récupération des projets : {e}"}), 500

@app.route("/iobeya-boards")
def iobeya_boards():
    room_id = request.args.get("room_id")
    if not room_id:
        return jsonify({"error": "Paramètre 'room_id' manquant"}), 400
    boards = list_boards(room_id)
    return jsonify(boards)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
