import requests
from datetime import datetime
import pandas as pd
import uuid
import random
import json

# Fonction utilitaire pour retrouver un élément par identifiant dans une liste de dictionnaires
def find_item_by_id(items, item_id, field="id"):
    """
    Retourne le dictionnaire dont le champ 'field' correspond à item_id.
    Si aucun élément ne correspond, retourne None.
    Ajoute des logs détaillés pour le débogage.
    """
    print(f"🔍 Recherche de l'élément avec {field} = {item_id} parmi {len(items)} éléments...")

    for idx, item in enumerate(items):
        value = item.get(field)
        print(f"➡️  Vérification élément {idx} : {field}={value}")
        if str(value) == str(item_id):
            print(f"✅ Élément trouvé : {item}")
            return item

    print(f"⚠️ Aucun élément trouvé avec {field} = {item_id}")
    return None

def get_github_features(projectId, github_token):
    """
    Version compatible GitHub API v4 (GraphQL) fin 2024 / 2025.
    Récupère correctement les titres et descriptions des items Projects V2.
    Utilise extract_feature_id_and_clean() pour extraire Nom_Feature et id_feature.
    """
    import requests, re

    if not projectId or not github_token:
        print("⚠️ Paramètres GitHub manquants (projectId ou token).")
        return []

    url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    query = """
    query($projectId: ID!) {
    node(id: $projectId) {
        ... on ProjectV2 {
        id
        title
        items(first: 100) {
            nodes {
            id
            fieldValues(first: 8) {
                nodes {
                ... on ProjectV2ItemFieldTextValue {
                    text
                    field { ... on ProjectV2FieldCommon { name } }
                }
                ... on ProjectV2ItemFieldDateValue {
                    date
                    field { ... on ProjectV2FieldCommon { name } }
                }
                ... on ProjectV2ItemFieldSingleSelectValue {
                    name
                    field { ... on ProjectV2FieldCommon { name } }
                }
                }
            }
            content {
                __typename
                ... on DraftIssue { title body }
                ... on Issue {
                title
                number
                url
                assignees(first: 10) { nodes { login } }
                }
                ... on PullRequest {
                title
                number
                url
                assignees(first: 10) { nodes { login } }
                }
            }
            }
        }
        }
    }
    }
    """

    variables = {"projectId": projectId}

    try:
        r = requests.post(url, headers=headers, json={"query": query, "variables": variables}, timeout=15)
        r.raise_for_status()
        data = r.json()
        if "errors" in data:
            print("⚠️ Erreurs GraphQL :", data["errors"])
            return []

        nodes = (
            data.get("data", {})
            .get("node", {})
            .get("items", {})
            .get("nodes", [])
        )
        features = []

        for node in nodes:
            content = node.get("content") or {}
            typename = content.get("__typename", "Unknown")
            title = content.get("title")
            body = content.get("body")
            state = content.get("state", "N/A")
            url_issue = content.get("url", "")
            number = content.get("number", "")
            updated = node.get("updatedAt")

            # Si pas de titre dans content, essayer de le trouver dans fieldValues
            if not title:
                for fv in node.get("fieldValues", {}).get("nodes", []):
                    field = fv.get("field", {}).get("name")
                    if field and field.lower() in ("title", "name", "nom"):
                        title = fv.get("value")
                    if field and field.lower() in ("description", "body", "texte"):
                        body = body or fv.get("value")

            cleaned_name, id_feature = extract_feature_id_and_clean(title or "")

            features.append({
                "id_GitHub": node.get("id"),
                "Nom_Feature": cleaned_name or "(Sans titre)",
                "id_feature": id_feature,
                "Description": (body or "").strip(),
                "Etat": state,
                "extra": url_issue,
                "number": number,
                "timestamp": updated,
                "type_contenu": typename
            })

        print(f"✅ {len(features)} items récupérés depuis GitHub.")
        return features

    except requests.RequestException as e:
        print(f"❌ Erreur API GitHub : {e}")
        return []

# Nouvelle fonction pour récupérer un Epic spécifique par son identifiant
def get_grist_epic_by_id(base_url, doc_id, api_key, epic_id, table_name="Epics"):
    """
    Récupère le contenu complet d'un Epic à partir de son identifiant.
    Retourne un dictionnaire contenant les champs de l'Epic.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    try:
        url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records"
        url = url.replace('://', '§§').replace('//', '/').replace('§§', '://')
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        if data:
            the_epic = find_item_by_id(data["records"], epic_id,"id")
            print(f"✅ Epic {epic_id} récupéré avec succès depuis Grist.")
            return the_epic
        else : 
            return None


    except requests.RequestException as e:
        print(f"❌ Erreur lors de la récupération de l'Epic {epic_id} : {e}")
        return None

def get_grist_epics(base_url, doc_id, api_key, table_name="Epics"):
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }    
    
    try:
        url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records"
        url = url.replace('://', '§§').replace('//', '/').replace('§§', '://')
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        epics = []
        
        for record in data.get("records", []):
            record_id = record.get("id")
            fields = record.get("fields", {})
            epic_name = fields.get("Epic") or fields.get("Titre") or fields.get("Name")
            if epic_name:
                epics.append({"id": record_id, "name": epic_name})

        print(f"✅ {len(epics)} épiques récupérés depuis Grist.")
        return epics
    
    except requests.RequestException as e:
        print(f"⚠️ Erreur API Grist : {e}")
        return []
        
def get_grist_features(base_url, doc_id, api_key, table_name="Features", filter_epic_id=None):
    filter_by_epic=None

    if filter_epic_id is not None:
        # Détermine le champ de liaison Epic et récupère les informations de l'Epic correspondant
        print(f"🔍 Filtrage activé : récupération de l'Epic {filter_epic_id} via le champ {filter_by_epic}")
        # Récupère les informations de l'Epic correspondant
        theepic = get_grist_epic_by_id(base_url, doc_id, api_key, filter_epic_id)
        fields = {
                "id": theepic.get("id"),
                **theepic.get("fields", {})
            }  
        filter_by_epic = fields.get("id_Epic")
        print(f"🔗 Champ de liaison trouvé : {filter_epic_id} = {filter_by_epic}")

    """
    Récupère l'ensemble des features depuis la source de données Grist.
    Retourne un tuple (DataFrame pandas, dernier_timestamp).
    """

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records"
    url = url.replace('://', '§§').replace('//', '/').replace('§§', '://')

    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        records = []
        last_update = None

        for rec in data.get("records", []):
            fields = {
                "id": rec.get("id"),
                **rec.get("fields", {})
            }

            if filter_by_epic is not None:
                if (fields.get("id_Epic") == filter_by_epic):
                    records.append(fields)
            else:
                records.append(fields)

        df = pd.DataFrame(records)
        print(f"✅ {len(df)} features récupérées depuis Grist (sync.py).")
        if last_update:
            print(f"🕒 Dernière mise à jour (Unix): {last_update}")
        return df, last_update

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération des données Grist : {e}")
        return pd.DataFrame(), None


# Nouvelle fonction pour créer une feature dans Grist
def create_grist_feature(
    base_url,
    doc_id,
    api_key,
    table_name="Features",
    name="Nouvelle feature",
    description="Description par défaut",
    state="open",
    type_feature="Story",
    gains=0,
    commentaires="Aucun commentaire",
    extra=None,
    id_epic=None,
    **kwargs
):
    """
    Crée un élément dans la table 'Features' de Grist.
    Tous les champs sont optionnels avec des valeurs par défaut.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "records": [
            {
                "fields": {
                    "uid": str(uuid.uuid4()),
                    "timestamp": datetime.now().isoformat(),
                    "name": name,
                    "description": description,
                    "state": state,
                    "Type": type_feature,
                    "Gains": gains,
                    "Commentaires": commentaires,
                    "extra": extra,
                    "id_Epic": id_epic,
                    **kwargs
                }
            }
        ]
    }

    url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records"
    url = url.replace("//api", "/api").replace(":/", "://")

    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Feature créée avec succès dans Grist : {data}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la création de la feature : {e}")
        return None

def update_grist_feature(base_url, doc_id, api_key, record_id, table_name="Features", **kwargs):
    """
    Met à jour un enregistrement existant dans la table 'Features' de Grist.
    Tous les champs à modifier sont passés via **kwargs.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    payload = {
        "records": [
            {
                "id": record_id,
                "fields": kwargs
            }
        ]
    }

    url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records"
    url = url.replace('://', '§§').replace('//', '/').replace('§§', '://')

    try:
        response = requests.patch(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Feature {record_id} mise à jour avec succès : {data}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la mise à jour de la feature {record_id} : {e}")
        return None


# Nouvelle fonction pour supprimer une feature dans Grist
def delete_grist_feature(base_url, doc_id, api_key, record_id, table_name="Features"):
    """
    Supprime une ligne (enregistrement) dans la table 'Features' de Grist.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records/{record_id}"
    url = url.replace("//api", "/api").replace(":/", "://")

    try:
        response = requests.delete(url, headers=headers)
        response.raise_for_status()
        print(f"🗑️ Feature {record_id} supprimée avec succès.")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la suppression de la feature {record_id} : {e}")
        return False


import re

def extract_feature_id_and_clean(text):
    """
    Recherche un motif [XXX] dans le texte, où XXX est le code de la feature.
    Si trouvé, retourne un tuple (texte_sans_pattern, feature_id).
    Si non trouvé, retourne (texte_original, None).
    Supprime aussi les caractères initiaux non alphanumériques du texte nettoyé.
    """
    if not isinstance(text, str):
        return text, None

    match = re.search(r'\[([^\[\]]+)\]', text)
    if match:
        feature_id = match.group(1).strip()
        # Supprimer la pattern du texte
        cleaned_text = re.sub(r'\[([^\[\]]+)\]', '', text)
        # Supprimer les caractères initiaux non alphanumériques
        cleaned_text = re.sub(r'^[^a-zA-Z0-9]+', '', cleaned_text)
        cleaned_text = cleaned_text.strip()
        return cleaned_text, feature_id
    else:
        cleaned_text = re.sub(r'^[^a-zA-Z0-9]+', '', text).strip()
        return cleaned_text, None

def get_iobeya_features(base_url, board_id, api_key, type_features_card_list=None):
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
        filtered_cards = []
        for item in data:
            item_class = item.get("@class")
            if   item_class == "com.iobeya.dto.BoardCardDTO":
                        filtered_cards.append(item)

        features = []
        featuretypeflag = False
        
        for l_card in filtered_cards:
            # todo use "props
            l_entity_type = l_card.get("entityType", "")
            appendchecklist = ""
            
            for type_feature in type_features_card_list:
                if l_entity_type == type_feature:
                    featuretypeflag = True
                    break
                
            if featuretypeflag :
                l_props= l_card.get("props", {})
                
                clean_title, if_feature = extract_feature_id_and_clean(l_props.get("title"))

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
                        "id_feature" :if_feature
                    }
                else :
                    feature = {
                        "uid": l_card.get("id"),
                        "Nom_Feature": clean_title,
                        "Description": l_props.get("description"),
                        "timestamp": l_card.get("modificationDate"),
                        "id_feature" :if_feature
                    }    
                    
                features.append(feature)

        #df = pd.DataFrame(features)
        print(f"✅ {len(features)} features récupérées depuis iObeya.")
        return features #df

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération des features iObeya : {e}")
        return pd.DataFrame(columns=["id", "id_Epic", "Nom_Feature", "Etat", "Description", "Type", "Gains", "Commentaires"])
