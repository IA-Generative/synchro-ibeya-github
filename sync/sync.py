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

def get_iobeya_features(base_url, board_id, api_key):
    """
    Récupère la liste des cartes/features depuis l'API iObeya pour un board donné.
    Retourne un DataFrame pandas avec les colonnes alignées sur Grist.
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    url = f"{base_url}/boards/{board_id}/cards"
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        features = []
        for card in data.get("cards", []):
            feature = {
                "id": card.get("id"),
                "id_Epic": card.get("epicId"),
                "Nom_Feature": card.get("name"),
                "Etat": card.get("state"),
                "Description": card.get("description"),
                "Type": card.get("type"),
                "Gains": card.get("gains", 0),
                "Commentaires": card.get("comments", "")
            }
            features.append(feature)

        df = pd.DataFrame(features)
        print(f"✅ {len(df)} features récupérées depuis iObeya.")
        return df

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération des features iObeya : {e}")
        return pd.DataFrame(columns=["id", "id_Epic", "Nom_Feature", "Etat", "Description", "Type", "Gains", "Commentaires"])

def get_github_features(org, repo, token):
    """
    Récupère la liste des issues du dépôt GitHub comme features.
    Retourne un DataFrame pandas avec les colonnes alignées sur Grist.
    """
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    url = f"https://api.github.com/repos/{org}/{repo}/issues"
    params = {
        "state": "all"
    }

    try:
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()
        issues = response.json()

        features = []
        for issue in issues:
            if "pull_request" in issue:
                # Ignorer les pull requests
                continue
            feature = {
                "id": issue.get("number"),
                "id_Epic": None,
                "Nom_Feature": issue.get("title"),
                "Etat": issue.get("state"),
                "Description": issue.get("body"),
                "Type": "Issue",
                "Gains": 0,
                "Commentaires": ""
            }
            features.append(feature)

        df = pd.DataFrame(features)
        print(f"✅ {len(df)} features récupérées depuis GitHub.")
        return df

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération des features GitHub : {e}")
        return pd.DataFrame(columns=["id", "id_Epic", "Nom_Feature", "Etat", "Description", "Type", "Gains", "Commentaires"])