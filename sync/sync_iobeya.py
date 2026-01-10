import json
import pandas as pd
import requests
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import yaml
from datetime import datetime   
from sync.sync_utils import extract_feature_id_and_clean

# --- Activation et configuration des logs ---
import logging

# --- Configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
app = logging.getLogger("sync_iobeya")
app.setLevel(logging.DEBUG)

# Load configuration from config.yaml or config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

def iobeya_list_rooms():
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

def iobeya_list_boards(room_id):
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
        
        ## note n: les boards sont dans data en tant que liste d'objets divers
        ## on récupère uniquement ceux de type BoardDTO avec id et name valides
        ## ainsi que l'id du container parent si disponible ( nécessaire pour créer des cartes )
        boards = [
            {
                "id": b.get("id"),
                "name": b.get("name"),
                "containerId": (
                    b.get("container", {}).get("id")
                    if isinstance(b.get("container"), dict)
                    else None
                )
            }
            for b in data
            if b.get("@class") == "com.iobeya.dto.BoardDTO"
            and b.get("id")
            and b.get("name")
        ]
        
        app.logger.info(f"✅ {len(boards)} boards récupérés depuis iObeya pour la room {room_id}.")
        
        return boards
    except requests.RequestException as e:
        app.logger.error(f"⚠️ Erreur API iObeya (boards) : {e}", exc_info=True)
        return [{"id": "error", "name": f"[Erreur connexion iObeya : {str(e)}]"}]

def iobeya_get_data(base_url, board_id, api_key, type_features_card_list=None):
    """
    Récupère la liste des cartes/features depuis l'API iObeya pour un board donné.
    Retourne un DataFrame pandas avec les colonnes alignées sur Grist.
    type_features_card: liste de types de cartes à filtrer (ex: ["com.iobeya.dto.CardDTO"])
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }
    url = f"{base_url}/s/j/boards/{board_id}/details"

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Filtrage des cartes selon le type spécifié
        filtered_cards , filtered_objectives= []
        
        for item in data:
            item_class = item.get("@class")
            if   item_class == "com.iobeya.dto.BoardCardDTO":
                        filtered_cards.append(item)
            if   item_class == "class com.iobeya.entity.Freetext":      
                        filtered_objectives.append(item)
                        
        features = []
        featuretypeflag = False
        
        for l_card in filtered_cards:
            # todo use "props
            l_entity_type = l_card.get("entityType", "")
            appendchecklist = ""
 
            # Log complet uniquement pour les FeatureCards
            if l_entity_type == "FeatureCard":
            #    try:
            #        print("🟦 FeatureCard détectée :", json.dumps(l_card, indent=2, ensure_ascii=False))
            #    except Exception as e:
            #        print(f"⚠️ Impossible de logger la FeatureCard : {e}")
            
                for type_feature in type_features_card_list:
                    if l_entity_type == type_feature:
                        featuretypeflag = True
                    break
                
            if featuretypeflag :
                l_props= l_card.get("props", {})
                
                clean_title, pi_number, item_id = extract_feature_id_and_clean(l_props.get("title"))
                if_feature = item_id

                # si carte de type FeatureCard, récupére la liste des checklists filtrée sur les tâches non terminées
                if l_entity_type == "FeatureCard":
                    lchecklist = l_card.get("checklist",[])
                    for lchcklst in lchecklist:
                        kind = lchcklst.get("kind","")
                        if kind == "hypothesis":   
                            label = lchcklst.get("label", "")
                            if label:
                                if appendchecklist:
                                    appendchecklist += "\n"  # ajoute un retour chariot avant si ce n’est pas le premier
                                appendchecklist += label
                    
                    feature = {
                        "uid": l_card.get("id"),
                        "Nom_Feature": clean_title,
                        "Description": appendchecklist,
                        "timestamp": l_card.get("modificationDate"),
                        "id_feature": if_feature,
                        "pi_num": pi_number,
                    }
                else :
                    feature = {
                        "uid": l_card.get("id"),
                        "Nom_Feature": clean_title,
                        "Description": l_props.get("description"),
                        "timestamp": l_card.get("modificationDate"),
                        "id_feature": if_feature,
                        "pi_num": pi_number,
                    }    
                    
                features.append(feature)

        #df = pd.DataFrame(features)
        print(f"✅ {len(features)} features récupérées depuis iObeya.")
        return features #df

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération des features iObeya : {e}")
        return pd.DataFrame(columns=["id", "id_Epic", "Nom_Feature", "Etat", "Description", "Type", "Gains", "Commentaires"])


def iobeya_create_missing_cards(iobeya_conf, context):
    """
    Crée dans iObeya les cards marquées 'create' dans iobeya_diff.
    """
    base_url = iobeya_conf.get("api_url")
    board_id = iobeya_conf.get("board_id")
    api_key = iobeya_conf.get("api_token")
    room_id= iobeya_conf.get("room_id")
    container_id= iobeya_conf.get("container_id")
    
    created = []
    for item in context.get("iobeya_diff", []):
        if item.get("action") == "create":
            feature = item.get("feature")
            if feature:
                x_pos, y_pos = get_next_card_position()
                result = iobeya_create_feature_card(base_url, room_id, board_id, container_id, api_key, feature, x=x_pos, y=y_pos)
                if result:
                    created.append(result)

    print(f"🟦 {len(created)} cards créées dans iObeya.")
    return created


def iobeya_create_feature_card(base_url, room_id, board_id, container_id, api_key, feature, x=300, y=300):
    """
    Crée une FeatureCard iObeya avec une structure complète
    conforme au modèle constaté sur l'API iObeya.
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }

    # Extraction des champs
    title = feature.get("Nom_Feature", "Sans titre")
    description = feature.get("Description", "")
    id_feature = feature.get("id_feature")

    # Nom affiché dans la carte
    card_title = f"[{id_feature}] : {title}" if id_feature else title

    payload = {
        "@class": "com.iobeya.dto.BoardCardDTO",
        #"id": None,
        "name": card_title,
        "entityType": "FeatureCard",
        "setName": "Cartes feature",
        "x": x,
        "y": y,
        "width": 380,
        "height": 300,
        "zOrder": 10,
        "isAnchored": False,
        "isLocked": False,
        "color": 10141941,
        "boardId": board_id,
        "roomId": room_id,
        "fontFamily": "arial",
        "container": {
            "@class": "com.iobeya.dto.EntityReferenceDTO",
            "isReadOnly": False,
            "id": board_id,   #container_id,
            "type": "BlankBoardElementContainer"
        },
        "props": {
            "title": card_title,
            "description": description or "",
            "wsjfProps": {
                "businessValue": 0,
                "timeCriticality": 0,
                "rROE": 0,
                "jobSize": 0,
                "wsjf": 0
            },
            "editorProps": {
                "activatedTab": "hypothesisView",
                "hypothesisHasContent": 0,
                "criteriaHasContent": 0,
                "wSJFHasContent": False
            }
        },
        "checklist": []
    }


    ##url = f"{base_url}/s/j/boards/{board_id}/cards"
    url = f"{base_url}/s/j/elements"
    payload = [payload] #iboeya API expects a list of elements
    
    try:
        print("📤 Payload envoyé à iObeya :", json.dumps(payload, indent=2, ensure_ascii=False))
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"🟦 FeatureCard créée dans iObeya : {data.get('id')} ({card_title})")
        return data
    except requests.RequestException as e:
        print(f"❌ Erreur lors de la création d'une FeatureCard iObeya : {e}")
        return None

# --- Placement paramétrable en quinconce ---
PLACEMENT = {
    "start_x": 20,
    "start_y": 1656,
    "offset_x": 420,
    "offset_y": 402,
    "workspace_width": 6187
}
_next_x = PLACEMENT["start_x"]
_next_y = PLACEMENT["start_y"]

def get_next_card_position():
    global _next_x, _next_y
    _next_x += PLACEMENT["offset_x"]

    if _next_x > PLACEMENT["workspace_width"]:
        _next_x = PLACEMENT["start_x"]
        _next_y += PLACEMENT["offset_y"]

    return _next_x, _next_y
