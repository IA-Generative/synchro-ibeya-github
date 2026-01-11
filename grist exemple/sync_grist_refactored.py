## Import des modules nécessaires

import pandas as pd
import random
import re  # ✅ Déplacé en haut avec les autres imports
import requests
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import yaml
from datetime import datetime, timezone
import logging

# --- Activation et configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("sync_grist")

# Chargement de la configuration depuis config.yaml ou config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)

###########    
###########    Méthodes pour gérer les interactions avec Grist  ###########
###########

### Récupération des Epics

def get_grist_epics(base_url, doc_id, api_key, table_name="Epics"):
    """Récupère la liste de tous les Epics depuis Grist."""
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
            epic_name = fields.get("Epic") or fields.get("Titre") or fields.get("Name") or fields.get("Nom")
            id_epic = fields.get("id_Epic") or fields.get("id2") or fields.get("id_epic")
            if epic_name:
                epics.append({
                    "id": record_id,
                    "id_epic": id_epic,
                    "name": epic_name
                })

        print(f"✅ {len(epics)} épiques récupérés depuis Grist.")
        return epics
    
    except requests.RequestException as e:
        print(f"⚠️ Erreur API Grist : {e}")
        return []

def grist_get_epics(grist_doc_id=None):
    """Wrapper pour récupérer les Epics avec configuration."""
    grist_conf = config.get("grist", {})
    GRIST_API_URL = grist_conf.get("api_url", "")
    GRIST_API_TOKEN = grist_conf.get("api_token", "")
    GRIST_DOC_ID = grist_conf.get("default_doc_id", "")
    GRIST_EPIC_TABLE_NAME = grist_conf.get("default_epic_table", "Epics")
    
    doc_id = grist_doc_id or GRIST_DOC_ID
    
    try:
        epics = get_grist_epics(GRIST_API_URL, doc_id, GRIST_API_TOKEN, GRIST_EPIC_TABLE_NAME)
        if not epics:
            logger.warning("⚠️ Aucune donnée reçue depuis Grist (Epics).")
            return [{"id": "error", "name": "[Erreur : aucune donnée Epics récupérée]"}]
        logger.info(f"✅ {len(epics)} epics récupérés depuis Grist.")
        return epics
    except Exception as e:
        logger.error(f"❌ Erreur lors de la récupération des Epics : {e}", exc_info=True)
        return [{"id": "error", "name": f"[Erreur récupération Epics : {str(e)}]"}]

def grist_get_doc_name(api_url, doc_id, api_token):
    """Retourne le nom du document Grist à partir de son ID."""
    url = f"{api_url}/api/docs/{doc_id}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json"
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("name", f"(Doc {doc_id} sans nom)")
    except Exception as e:
        logger.warning(f"⚠️ Erreur récupération nom du doc Grist ({doc_id}) : {e}")
        return f"(Doc {doc_id} inconnu)"

def get_grist_epic(base_url, doc_id, api_key, epic_id, table_name="Epics"):
    """Récupère le contenu complet d'un Epic à partir de son identifiant."""
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
            the_epic = find_item_by_id(data["records"], epic_id, "id")
            if the_epic:
                print(f"✅ Epic {epic_id} récupéré avec succès depuis Grist.")
            return the_epic
        return None

    except requests.RequestException as e:
        print(f"❌ Erreur lors de la récupération de l'Epic {epic_id} : {e}")
        return None


### ✅ REFACTORISÉ : Fonction générique consolidée pour récupérer les données
def grist_get_data(base_url, doc_id, api_key, table_name="Features", filter_epic_id=None, pi=0):
    """
    Récupère l'ensemble des données depuis une table Grist.
    
    Args:
        base_url: URL de base de l'API Grist
        doc_id: ID du document Grist
        api_key: Token d'authentification
        table_name: Nom de la table à récupérer (Features, Risques, etc.)
        filter_epic_id: Optionnel - filtre par Epic ID
        pi: Optionnel - filtre par numéro de PI
        
    Returns:
        tuple: (DataFrame pandas, dernier_timestamp)
    """
    filter_by_epic = None

    if filter_epic_id is not None:
        theepic = get_grist_epic(base_url, doc_id, api_key, filter_epic_id)
        if theepic:
            fields = {
                "id": theepic.get("id"),
                **theepic.get("fields", {})
            }  
            filter_by_epic = fields.get("id_Epic")
            print(f"🔗 Champ de liaison trouvé : {filter_epic_id} = {filter_by_epic}")

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
        pi_val = int(pi) if pi else 0

        for rec in data.get("records", []):
            fields = {
                "type": table_name,  # permet de différencier les types d'items
                "id": rec.get("id"),
                **rec.get("fields", {})
            }
            
            if table_name == "Features":
                # Normalise l'identifiant pour la synchronisation
                fields["id_feature"] = (
                    fields.get("id_feature") or
                    fields.get("id_Feature") or
                    fields.get("id2")
                )
            
            # Track the most recent update timestamp
            ts = _extract_last_update_epoch(rec)
            if ts is not None:
                last_update = ts if last_update is None else max(last_update, ts)
            
            # Applique les filtres
            if pi_val > 0 and str(fields.get("PI_Num")) != str(pi_val):
                continue
                
            if filter_epic_id is not None:
                if str(fields.get("id_Epic")) != str(filter_epic_id):
                    continue

            records.append(fields)

        df = pd.DataFrame(records)
        print(f"✅ {len(df)} {table_name} récupérées depuis Grist.")
        if last_update:
            print(f"🕒 Dernière mise à jour (Unix): {last_update}")
        return df, last_update

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération des données Grist : {e}")
        return pd.DataFrame(), None


### ✅ REFACTORISÉ : Récupération complète de toutes les tables
def grist_get_all_data(base_url, doc_id, api_key, filter_epic_id=None, pi=0):
    """
    Récupère et fusionne les données de toutes les tables.
    
    Returns:
        tuple: (DataFrame fusionné, dernier_timestamp)
    """
    tables = ["Features", "Risques", "Dependances", "Objectives", "Issues"]
    dfs = []
    last_updates = []

    for table_name in tables:
        df, last_update = grist_get_data(base_url, doc_id, api_key, table_name, filter_epic_id, pi)
        if not df.empty:
            dfs.append(df)
        if last_update is not None:
            last_updates.append(last_update)

    records = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
    last_update = max(last_updates) if last_updates else None

    return records, last_update


### Création des objets dans Grist

def grist_create_data(grist_conf, context):
    """
    Crée dans Grist les features présentes dans iObeya ou GitHub
    mais absentes de Grist (action = 'not_present').
    """
    created = []
    api_url = grist_conf.get("api_url")
    doc_id = (
        context.get("session_data", {}).get("grist_doc_id")
        or context.get("grist_doc_id")
        or grist_conf.get("doc_id")
    )
    print(f"📘 Doc_id actif utilisé pour la création : {doc_id}")
    api_token = grist_conf.get("api_token")
    table_name = grist_conf.get("feature_table_name", "Features")

    # ✅ REFACTORISÉ : Fusion unique des diffs
    combined_diffs = []
    iobeya_diff = context.get("iobeya_diff", [])
    github_diff = context.get("github_diff", [])

    for item in iobeya_diff:
        if item.get("action") == "not_present":
            combined_diffs.append(item["feature"])
            new_item = item.copy()
            new_item["action"] = "create"
            github_diff.append(new_item)

    for item in github_diff:
        if item.get("action") == "not_present":
            if item["feature"] not in combined_diffs:  # Évite les doublons
                combined_diffs.append(item["feature"])
                new_item = item.copy()
                new_item["action"] = "create"
                iobeya_diff.append(new_item)

    print(f"🧩 {len(combined_diffs)} features à créer dans Grist (not_present).")

    for feat in combined_diffs:
        name = feat.get("Nom_Feature", "Sans titre")
        description = feat.get("Description", "")
        state = feat.get("Etat", "open")
        type_feature = feat.get("Type", "Feature")
        gains = feat.get("Gains", 0)
        commentaires = feat.get("Commentaires", "")
        extra = feat.get("extra")
        id_epic = feat.get("id_Epic")
        id_feature = feat.get("id_feature") or feat.get("id_Feature") or f"FPX-{random.randint(1000, 9999)}"

        # ✅ REFACTORISÉ : Extraction du numéro ID et PI
        id_num, pi_num = _extract_feature_identifiers(id_feature, context)
        
        # 🔍 Recherche de l'ID interne de l'Epic correspondant
        epics_list = get_grist_epics(api_url, doc_id, api_token, "Epics")
        id_epic_internal = _find_epic_internal_id(epics_list, id_epic)

        if id_epic_internal:
            print(f"🔗 Epic trouvé : id_epic={id_epic} → id interne={id_epic_internal}")
        else:
            print(f"⚠️ Aucun Epic trouvé avec id_Epic={id_epic}, la feature sera créée sans lien Epic.")

        result = create_grist_feature(
            base_url=api_url,
            doc_id=doc_id,
            api_key=api_token,
            table_name=table_name,
            name=name,
            description=description,
            state=state,
            type_feature=type_feature,
            gains=gains,
            commentaires=commentaires,
            extra=extra,
            id_epic=id_epic_internal,
            id_feature=id_num,
            pi_num=pi_num
        )

        if result:
            created.append(result)

    print(f"✅ {len(created)} features créées dans Grist.")
    return created


### ✅ REFACTORISÉ : Fonction CRUD unique pour créer/mettre à jour une feature
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
    id_feature=None,
    pi_num=None,
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
                    "Nom_Feature": name,
                    "Description": description,
                    "Hypothese_de_gain": gains,
                    "Commentaires": commentaires,
                    "id2": id_feature,
                    "id_Epic": id_epic,
                    "PI_Num": pi_num,
                    **kwargs
                }
            }
        ]
    }

    url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records"
    url = url.replace('://', '§§').replace('//', '/').replace('§§', '://')

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


### ============ Fonctions utilitaires ============

def find_item_by_id(items, item_id, field="id"):
    """
    Retourne le dictionnaire dont le champ 'field' correspond à item_id.
    Si aucun élément ne correspond, retourne None.
    Ajoute des logs détaillés pour le débogage.
    """
    print(f"🔍 Recherche de l'élément avec {field} = {item_id} parmi {len(items)} éléments...")

    for idx, item in enumerate(items):
        value = item.get(field)
        if str(value) == str(item_id):
            return item

    print(f"⚠️ Aucun élément trouvé avec {field} = {item_id}")
    return None


def _extract_feature_identifiers(id_feature, context):
    """
    ✅ REFACTORISÉ : Extrait le numéro de feature et le numéro de PI à partir de l'ID.
    
    Returns:
        tuple: (id_num, pi_num)
    """
    id_num = (lambda v: int(v.split('-')[-1]) if '-' in v and v.split('-')[-1].isdigit() 
              else random.randint(1000, 9999))(str(id_feature))
    
    # Extraction du numéro de PI (valeur entre les lettres 'FP' et le tiret '-')
    match_pi = re.search(r'FP(\d+)-', str(id_feature))
    
    if match_pi:
        pi_num = int(match_pi.group(1))
    else:
        # Récupère le pi_num du contexte de session si disponible
        pi_num_context = context.get("session_data", {}).get("pi_num", 0)
        try:
            pi_num = int(pi_num_context)
        except (ValueError, TypeError):
            pi_num = 0
    
    print(f"🔢 PI_num déterminé : {pi_num} pour feature {id_feature}")
    return id_num, pi_num


def _find_epic_internal_id(epics_list, id_epic):
    """
    ✅ REFACTORISÉ : Recherche l'ID interne d'un Epic à partir de son id_epic.
    
    Returns:
        int ou None: L'ID interne de l'Epic, ou None si non trouvé
    """
    if not id_epic or not epics_list:
        return None
    
    for epic in epics_list:
        if str(epic.get("id_epic")) == str(id_epic):
            return epic.get("id")
    
    return None


### Parser les timestamps

def _parse_timestamp_to_epoch(value):
    """Parse a timestamp-like value to epoch seconds.

    Accepts:
      - int/float epoch seconds or milliseconds
      - ISO 8601 strings (e.g., 2026-01-10T12:34:56Z)
    Returns float epoch seconds, or None if it cannot be parsed.
    """
    if value is None:
        return None
    # numeric epoch seconds/ms
    if isinstance(value, (int, float)):
        v = float(value)
        # Heuristic: if it's in milliseconds (very large), convert to seconds.
        if v > 1e12:
            v = v / 1000.0
        return v
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Handle trailing Z
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except Exception:
            return None
    return None


def _extract_last_update_epoch(rec):
    """Try multiple locations/keys to find a last-update timestamp for a Grist record."""
    # Some APIs may expose updatedAt/createdAt at top-level.
    for key in ("updatedAt", "modifiedAt", "lastModified", "createdAt"):
        ts = _parse_timestamp_to_epoch(rec.get(key))
        if ts is not None:
            return ts
    fields = rec.get("fields", {}) or {}
    # Try common field names (French + English + variants)
    for key in (
        "updatedAt", "UpdatedAt", "modifiedAt", "ModifiedAt", "lastUpdate", "LastUpdate",
        "last_modified", "Last_Modified", "Derniere_MAJ", "Dernière_MAJ", "DerniereMAJ", "DernièreMAJ",
        "Date_MAJ", "date_maj", "timestamp", "Timestamp"
    ):
        ts = _parse_timestamp_to_epoch(fields.get(key))
        if ts is not None:
            return ts
    return None
