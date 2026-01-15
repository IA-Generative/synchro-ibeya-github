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
import uuid

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
                    "container": (
                        b.get("elementContainer") if isinstance(b.get("elementContainer"), dict)
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
        BREAK_ON_OBJECT_ID = "2CF60A73-E9C2-2B37-813A-C17D15CDED02"

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
                                "Commited": "Committed" if commitment == "committed" else "Uncommitted",
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
            # --- Debug: log raw card payload (can be verbose)
            try:
                logger.debug("🧾 l_card raw payload:\n%s", json.dumps(l_card, indent=2, ensure_ascii=False))
            except Exception as e:
                logger.debug("🧾 l_card raw payload: <unserializable> (%s)", e)
            
            featuretypeflag = False
            # Todo use "props" pour determiner automatiquement le type de card ?
            # pour l'instant si card feature > traitement particulier sinon on regarde juste le contenu du titre
            
            l_entity_type = l_card.get("entityType", "") 
            l_props= l_card.get("props", {})
            
            list_hypothesis = ""
            list_criterias = ""

            if l_entity_type == "FeatureCard" and l_props and isinstance(l_props, dict):
                
                clean_title, pi_number, item_id = extract_feature_id_and_clean(l_props.get("title"))

                # si carte de type FeatureCard, récupére la liste des checklists filtrée sur les tâches non terminées
                # on sait par défaut que sont des types features et que les hypothèses sont dans la checklist de type "hypothesis"
                # TODO : gérer les autres types de checklist si besoin
                
                if clean_title:
                    lchecklist = l_card.get("checklist",[])
                    
                    for lchcklst in lchecklist:
                        kind = lchcklst.get("kind","")
                        if kind == "hypothesis":   
                            label = lchcklst.get("label", "")
                            if label:
                                if list_hypothesis:
                                    list_hypothesis += "\n"  # ajoute un retour chariot avant si ce n’est pas le premier
                                list_hypothesis += label
                        if  kind == "criteria":   
                            label = lchcklst.get("label", "")
                            if label:
                                if list_criterias:
                                    list_criterias += "\n"  # ajoute un retour chariot avant si ce n’est pas le premier
                                list_criterias += label                  
                    
                    feature = {
                        "type": "Features",
                        "uid": l_card.get("id"),
                        "Nom": clean_title,
                        "Description": clean_title,
                        "Hypotheses_de_gain": list_hypothesis,
                        "Criteres_d_acceptation" : list_criterias,
                        "timestamp": l_card.get("modificationDate"),
                        "id_Num": item_id,
                        "pi_Num": pi_number,
                    }
                    
                    objects.append(feature)
                    
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
                            "Commited": "Committed" if detected_kind == "committed" else "Uncommitted",
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
    container = iobeya_conf.get("iobeya_board_container")

    try:
        created = []
        zorder = 100  # ordre d'empilement initial
        for item in context.get("iobeya_diff", []):
            if item.get("action") == "create":
                feature_name = item.get("Nom")
                # recupère l'objet feature complet depuis le grist_objects
                feature = next((f for f in context.get("grist_objects", []) if f.get("Nom") == feature_name and f.get("type") == "Features"), None)
                
                if feature:
                    x_pos, y_pos = get_next_card_position()
                    result = iobeya_create_feature_card(base_url, room_id, board_id, container, api_key, feature, x=x_pos, y=y_pos, zorder=zorder)
                    if result:
                        created.append(result)
                        zorder -= 1

        print(f"🟦 {len(created)} cards créées dans iObeya.")
        return created
    except Exception as e:
        logger.error(f"❌ Erreur lors de la création des cards iObeya : {e}", exc_info=True)
        return None

def iobeya_create_feature_card(base_url, room_id, board_id, container, api_key, feature, x=300, y=300, zorder=1):
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
    title = feature.get("Nom", "Sans titre")
    description = feature.get("Description", "")
    id_feature = feature.get("id_Num")
    pi_number = feature.get("pi_Num", "")

    # créer la checklist avec hypothèses et critères
    hypothesis = feature.get("Hypotheses_de_gain", "")
    criterias = feature.get("Criteres_d_acceptation", "")       

    checklist = [] 
    hypothesis = feature.get("Hypotheses_de_gain", "")  
    criterias = feature.get("Criteres_d_acceptation", "")
    
    index = 0   
    for line in hypothesis.splitlines():
        if line.strip():
            checklist.append({
                "@class": "com.iobeya.dto.ChecklistItemDTO",
                "isReadOnly": False,
                "label": line.strip(),
                "status": None,
                "index": index,
                "kind": "hypothesis"
            })
            index += 1
    
    index = 0     
            
    for line in criterias.splitlines():
        if line.strip():
            checklist.append({
                "@class": "com.iobeya.dto.ChecklistItemDTO",
                "isReadOnly": False,
                "label": line.strip(),
                "status": None,
                "index": index,
                "kind": "criteria"
            })
            index += 1
            
    # Nom affiché dans la carte @ uuid de la carte. Généré aléatoirement ici.
    card_title = f"[FP{pi_number}-{id_feature}] : {title}" if id_feature else f"[Feat]: {title}"
    uuid_id=uuid.uuid4() # action : creer un uuid pour l'id de la card

    payload = {
        "@class": "com.iobeya.dto.BoardCardDTO",
        "isReadOnly": False,
        "id": str(uuid_id),
        "isAnchored": False,
        "isLocked": False,
        "x": x,
        "y": y,
        "width": 379,
        "height": 297,
        "zOrder": zorder,
        "color": 10141941,
        "entityType": "FeatureCard",
        "name": "Carte Feature",
        "setName": "Cartes feature",
        "fontFamily": "arial",
        "linkLabel": "",
        "linkUrl": "",
        "assignees": [],
        "container":  container, # nécessaire pour créer la carte dans le bon panneau
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
        "checklist": checklist
    }

    ##url = f"{base_url}/s/j/boards/{board_id}/cards"
    url = f"{base_url}/s/j/elements"
    payload = [payload] #iboeya API expects a list of elements
    
    try:
        #logger.info("📤 Payload envoyé à iObeya : %s", json.dumps(payload, indent=2, ensure_ascii=False))
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info("🟦 FeatureCard créée dans iObeya : %s (%s)", uuid_id, card_title)
        return data
    except requests.RequestException as e:
        logger.warning("❌ Erreur lors de la création d'une FeatureCard iObeya : %s", e)
        return None

# --- Placement paramétrable en quinconce ---

# --- Placement paramétrable en quinconce (stagger) ---

PLACEMENT = {  # positionnement dans le rectangle de travail "Features backlog"
    "start_x": 5120,
    "start_y": 2520,
    "offset_x": 80,
    "offset_y": 80,
    "stagger_x": 80,          # quinconce: décale une ligne sur deux de 50px vers la droite
    "workspace_width": 2240,  # largeur de la zone de travail (px)
    "workspace_height":  541 # hauteur de la zone de travail (px) -> ajuste selon ta board
}

# Indices de placement (colonne/ligne) : on remplit VERTICALEMENT puis on passe à la colonne suivante.
_col_idx = 0
_row_idx = 0


def get_next_card_position():
    """Retourne (x, y) pour la prochaine carte.

    - Placement en colonnes: on incrémente Y à chaque carte.
    - Quand on atteint le bas de la zone (bottom), on repart à start_y et on décale X.
    - Quinconce: une ligne sur deux est décalée à droite de `stagger_x`.
    """
    global _col_idx, _row_idx

    start_x = PLACEMENT["start_x"]
    start_y = PLACEMENT["start_y"]
    offset_x = PLACEMENT["offset_x"]
    offset_y = PLACEMENT["offset_y"]
    stagger_x = PLACEMENT.get("stagger_x", 0)
    workspace_width = PLACEMENT["workspace_width"]
    workspace_height = PLACEMENT["workspace_height"]

    max_x = start_x + workspace_width
    max_y = start_y + workspace_height

    # Calcul position courante (avant incrément)
    x = start_x + (_col_idx * offset_x) + ((_row_idx % 2) * stagger_x)
    y = start_y + (_row_idx * offset_y)

    # Prépare l'index suivant
    _row_idx += 1

    # Si la prochaine ligne dépasserait le bas, on repart en haut et on passe à la colonne suivante
    if (start_y + (_row_idx * offset_y)) > max_y:
        _row_idx = 0
        _col_idx += 1

    # Si on dépasse la largeur, on revient au début (fallback)
    if (start_x + (_col_idx * offset_x)) > max_x:
        _col_idx = 0
        _row_idx = 0

    return x, y