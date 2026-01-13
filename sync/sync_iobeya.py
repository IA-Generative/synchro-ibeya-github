## Import des modules nécessaires

import pandas as pd
import random
import requests
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))) ##include the parent directory for module imports
import yaml
from datetime import datetime, timezone
import logging
import json

# --- Import des fonctions utilitaires ---

from sync.sync_utils import (
    extract_feature_id_and_clean,
    extract_id_and_clean_for_kind,
    extract_objective_id_and_clean
)

# --- Activation et configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("sync_iobeya")
logger.setLevel(logging.DEBUG)

# Chargement de la configuration depuis config.yaml ou config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

###########    
###########  Methodes pour gérer les interactions avec iObeya  ###########
###########

def iobeya_get_rooms(base_url, token):
    """
    Récupère la liste des rooms iObeya via l'API REST.
    Retourne une liste d'objets {id, name}.
    """

    if not base_url or not token:
        logger.warning("⚠️ Configuration iObeya incomplète.")
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
        logger.info(f"✅ {len(rooms)} rooms récupérées depuis iObeya.")
        return rooms
    except requests.RequestException as e:
        logger.error(f"⚠️ Erreur API iObeya (rooms) : {e}", exc_info=True)
        return [{"id": "error", "name": f"[Erreur connexion iObeya : {str(e)}]"}]

def iobeya_get_boards(room_id):
    """
    Récupère la liste des boards pour une room iObeya via l'API REST.
    Retourne une liste d'objets {id, name}.
    """
    iobeya_conf = config.get("iobeya", {})
    base_url = iobeya_conf.get("base_url")
    token = iobeya_conf.get("token")
    if not base_url or not token:
        logger.warning("⚠️ Configuration iObeya incomplète.")
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
        
        boards = [];
        
        for b in data :
            
            class_object = b.get("@class")
                                    
            if class_object == "com.iobeya.dto.BoardDTO" \
            and b.get("id") and b.get("name") and b.get("isModel") == False : # filtre les boards modèles

                id = b.get("id")
                name = b.get("name")

                board =  {
                    "id": id,
                    "name": name,
                    "containerId": (
                        b.get("container", {}).get("id")
                        if isinstance(b.get("container"), dict)
                        else None
                    )
                 }
                boards.append(board)
                    
        logger.info(f"✅ {len(boards)} boards récupérés depuis iObeya pour la room {room_id}.")
        
        # Tri alpha sur le nom du board (insensible à la casse)
        boards_sorted = sorted(
            boards,
            key=lambda b: ((b.get("name") or "").strip().lower(), (b.get("id") or ""))
        )

        return boards_sorted
    except requests.RequestException as e:
        logger.error(f"⚠️ Erreur API iObeya (boards) : {e}", exc_info=True)
        return [{"id": "error", "name": f"[Erreur connexion iObeya : {str(e)}]"}]

def iobeya_get_board_objects(base_url, board_id, api_key, type_features_card_list=None):
    """
    Récupère la liste des cartes/features depuis l'API iObeya pour un board donné.
    Retourne un DataFrame pandas avec les colonnes alignées sur Grist.
    type_features_card: liste de types de cartes à filtrer (ex: ["com.iobeya.dto.CardDTO"])
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    try:
        url = f"{base_url}/s/j/boards/{board_id}/details"
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        
        
                # --- Debug: break early on a specific object id (useful to isolate problematic payloads)
        BREAK_ON_OBJECT_ID = "a946ce26-86a4-4dd8-bf94-72a774f798f2"

        # Filtrage des cartes selon le type spécifié
        filtered_cards = []
        objects = []
                
        for item in data:
            item_class = item.get("@class")

            # 🔎 Break requested: stop processing as soon as we hit this object id
            if item.get("id") == BREAK_ON_OBJECT_ID:
                logger.debug(f"🛑 Break: object id {BREAK_ON_OBJECT_ID} encountered, item @class = {item_class}.")
               
            # - si carte de type objective (BoardFreetextDTO) on determine si c’est un objectif (commité ou non)
            
            if   item_class == "com.iobeya.dto.BoardFreetextDTO":      
                content_label = item.get("contentLabel","")
                
                # on regarde le contenu du titre pour déterminer s’il s’agit d’un objectif (tobj ou utobj)
                cleaned_text, pi_number, item_number, commitment = extract_objective_id_and_clean(content_label)
                
                if commitment is not None:
                    
                    # Attention il faut extraire ligne par ligne car on peut avoir plusieurs objectifs dans une même entitée
                    lignes= content_label.splitlines()
                    
                    for ligne in lignes:
                        cleaned_text, pi_number, item_number, commitment = extract_objective_id_and_clean(ligne)
                
                        objectives = {
                                "type": "Objectives",
                                "uid": item.get("id"),
                                "Nom": cleaned_text,
                                "timestamp": item.get("modificationDate"),
                                "id_Num": item_number,
                                "Commited": "committed" if commitment == "committed" else "uncommitted",
                                "pi_Num": pi_number,
                            }
                        objects.append(objectives)
                        
                        
            if  item_class == "com.iobeya.dto.BoardNoteDTO": # pour dépendances ou risques
                l_props= item.get("props", {})
                
                if l_props and isinstance(l_props, dict):
                    content_label = l_props.get("content","")
                    cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(content_label, kind=None)
                else :
                    logger.warning(f"❌ card d'object inattendu (props manquants)")
    
                if detected_kind == "Features" or detected_kind == "Dependances" or detected_kind == "Risques":
                    feature = {
                        "type": detected_kind,
                        "uid": item.get("id"),
                        "Nom": cleaned_text,
                        "timestamp": item.get("modificationDate"),
                        "id_Num": item_number,
                        "pi_Num": pi_number,
                    }    
                    objects.append(feature)
                                                                                    
            # - si carte de type BoardCardDTO on creer un array de cartes à traiter après
            if   item_class == "com.iobeya.dto.BoardCardDTO":
                filtered_cards.append(item)
        
        ## Parcours des cartes filtrées pour extraire les informations pertinentes
        
        for l_card in filtered_cards:
            
            featuretypeflag = False
            # Todo use "props" pour determiner automatiquement le type de card ?
            # pour l'instant si card feature > traitement particulier sinon on regarde juste le contenu du titre
            
            l_entity_type = l_card.get("entityType", "")
            appendchecklist = ""
 
            # Log complet uniquement pour les FeatureCards
            if l_entity_type == "FeatureCard":           
                for type_feature in type_features_card_list:
                    if l_entity_type == type_feature:
                        featuretypeflag = True
                    break
                
            l_props= l_card.get("props", {})

            if featuretypeflag == "FeatureCard" and l_props and isinstance(l_props, dict):
                
                clean_title, pi_number, item_id = extract_feature_id_and_clean(l_props.get("title"))

                # si carte de type FeatureCard, récupére la liste des checklists filtrée sur les tâches non terminées
                # on sait par défaut que sont des types features et que les hypothèses sont dans la checklist de type "hypothesis"
                if clean_title:
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
                        "type": "Features",
                        "uid": l_card.get("id"),
                        "Nom": clean_title,
                        "Description": appendchecklist,
                        "timestamp": l_card.get("modificationDate"),
                        "id_Num": item_id,
                        "pi_Num": pi_number,
                    }
                    
            else : # si carte d’un autre type que FeatureCard

                    # on regarde le contenu du titre pour extraire le type et les données
                    if l_props and isinstance(l_props, dict):
                        cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(l_props.get("title"), kind=None)
                    else :
                        logger.warning(f"❌ card de format inattendu (props manquants)")
                
                    if detected_kind == "Features" or detected_kind == "Dependances" or detected_kind == "Risques" or detected_kind == "Issues":
                        dependance = {
                            "type": detected_kind,
                            "uid": l_card.get("id"),
                            "Nom": cleaned_text,
                            "timestamp": l_card.get("modificationDate"),
                            "id_Num": item_number,
                            "pi_Num": pi_number,
                        }    
                        objects.append(dependance)                   
                                              
                    if detected_kind == "committed" or detected_kind == "uncommitted":
                        objective = {
                            "type": "Objectives",
                            "uid": l_card.get("id"),
                            "Nom": cleaned_text,
                            "Commited": "committed" if detected_kind == "committed" else "uncommitted",
                            "timestamp": l_card.get("modificationDate"),
                            "id_Num": item_number,
                            "pi_Num": pi_number,
                        }    
                        objects.append(objective)
                           
        returnObject = pd.DataFrame(objects)
        logger.info(f"✅ {len(returnObject)} objects récupérées depuis iObeya.")
        return returnObject

    except requests.exceptions.RequestException as e:
        logger.warning(f"❌ Erreur lors de la récupération des objects iObeya : {e}")
        return None

def iobeya_board_create_objects(iobeya_conf, context):
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