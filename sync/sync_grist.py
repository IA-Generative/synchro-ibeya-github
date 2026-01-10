import pandas as pd
import random
import requests
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import yaml
from datetime import datetime, timezone

# --- Activation et configuration des logs ---
import logging

# --- Configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("sync_grist")

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

# Load configuration from config.yaml or config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

def grist_get_epics(grist_doc_id=None):
    
    grist_conf = config.get("grist", {})
    GRIST_API_URL = grist_conf.get("api_url", "")
    GRIST_API_TOKEN = grist_conf.get("api_token", "")
    GRIST_DOC_ID = grist_conf.get("default_doc_id", "")
    GRIST_TABLE_NAME = grist_conf.get("default_table", "Features")
    GRIST_EPIC_TABLE_NAME = grist_conf.get("default_epic_table", "Epics")
    GRIST_FEATURE_TABLE_NAME = grist_conf.get("default_feature_table", "Features")
    
    # Permet de passer un doc_id personnalisé, sinon utilise la config par défaut.

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



# --- Utilitaire pour récupérer le nom du document Grist ---
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

# Nouvelle fonction pour créer dans Grist les features absentes (action = 'not_present') à partir des diffs iObeya et GitHub
def grist_create_missing_features(grist_conf, context):
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

    # Fusion des diffs iObeya et GitHub
    combined_diffs = []
    nitem = {}
    
    for item in context.get("iobeya_diff", []):
        if item.get("action") == "not_present":
            combined_diffs.append(item["feature"])
            nitem.clear()
            nitem = item.copy()
            nitem["action"] = "create"  # permet d'indiquer création également dans github
            context.get("github_diff").append(nitem)

    for item in context.get("github_diff", []):
        if item.get("action") == "not_present":
            combined_diffs.append(item["feature"])
            nitem.clear()
            nitem = item.copy()
            nitem["action"] = "create"  # permet d'indiquer création également dans iobeya
            context.get("iobeya_diff").append(nitem)

    # NOTE : Pour se rappeller >> si synchronisation est bidirectionnelle elle doit également tenir compte des updates entre les deux systèmes iobeya et github... ( lancer une deuximère synchronisation après la création des éléments manquants ? )

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
        id_num = (lambda v: int(v.split('-')[-1]) if '-' in v and v.split('-')[-1].isdigit() else random.randint(1000, 9999))(str(id_feature))
        import re
        # Extraction du numéro de PI (valeur entre les lettres 'FP' et le tiret '-')
        match_pi = re.search(r'FP(\d+)-', str(id_feature))
        
        # récupère le pi_num dans le contexte de la session si disponible
        pi_num_context = 0
        session_data = context.get("session_data", {})
        if session_data:
            pi_num_context = session_data.get("pi_num", 0)
            
        # récupère le pi_num dans le contexte de num de la feature si disponible

        if match_pi:
            pi_num = int(match_pi.group(1))
        else:
            try:
                pi_num = int(pi_num_context)# si pas de match, utilise le contexte
            except (ValueError, TypeError):
                pi_num = 0 # valeur par défaut si tout échoue
                
        print(f"🔢 PI_num déterminé : {pi_num} pour feature {id_feature}")
        
        # 🔍 Recherche de l'ID interne de l'Epic correspondant à l'id_Epic
        epics_list = get_grist_epics(api_url, doc_id, api_token, "Epics")
        matching_epic = None
        if id_epic:
            for epic in epics_list:
                if str(epic.get("id_epic")) == str(id_epic):
                    matching_epic = epic
                    break

        if matching_epic:
            id_epic_internal = matching_epic.get("id")
            print(f"🔗 Epic trouvé : id_epic={id_epic} → id interne={id_epic_internal}")
        else:
            id_epic_internal = None
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
            
    ## Ici ajouter les fonction de CRUD dans iobeya et github   
        
            

    print(f"✅ {len(created)} features créées dans Grist.")
    return created


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

# 
#$id2 = il faut parser et extraire le numéro de la feature
#$id_Epic = un identifiant numérique et pas identifiatnt de type E-XX

    payload = {
        "records": [
            {
            "fields": {
                #"uid": str(uuid.uuid4()),
                "Nom_Feature": name,
                "Description": description,
                "Hypothese_de_gain": gains,
                "Commentaires": commentaires,
                "id2": id_feature,
                "id_Epic": id_epic,
                "PI_Num": pi_num,                
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

# 
#$id2 = il faut parser et extraire le numéro de la feature
#$id_Epic = un identifiant numérique et pas identifiatnt de type E-XX

    payload = {
        "records": [
            {
            "fields": {
                #"uid": str(uuid.uuid4()),
                "Nom_Feature": name,
                "Description": description,
                "Hypothese_de_gain": gains,
                "Commentaires": commentaires,
                "id2": id_feature,
                "id_Epic": id_epic,
                "PI_Num": pi_num,                
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
               
def grist_get_data(base_url, doc_id, api_key, filter_epic_id=None , pi=0):

    features = pd.DataFrame()
    risks = pd.DataFrame()
    dependances = pd.DataFrame()
    objectives = pd.DataFrame()
    issues = pd.DataFrame()
    last_update = None
    last_update_f = None
    last_update_r = None
    last_update_d = None
    last_update_o = None
    last_update_i = None

    features, last_update_f = grist_get_data_table(base_url, doc_id, api_key, "Features", filter_epic_id , pi)
    risks, last_update_r = grist_get_data_table(base_url, doc_id, api_key, "Risques", filter_epic_id , pi)
    dependances, last_update_d = grist_get_data_table(base_url, doc_id, api_key, "Dependances", filter_epic_id , pi)
    objectives, last_update_o = grist_get_data_table(base_url, doc_id, api_key, "Objectives", filter_epic_id , pi)
    issues, last_update_i = grist_get_data_table(base_url, doc_id, api_key, "Issues", filter_epic_id , pi)

    # Initialize records as DataFrame
    records = pd.DataFrame()
    # Concat (DataFrames) -> single DataFrame (expected by app.py)
    dfs = [df for df in (features, risks, dependances, objectives, issues)
           if isinstance(df, pd.DataFrame) and not df.empty]
    records = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    # Compute the most recent last_update among all tables
    candidates = [last_update_f, last_update_r, last_update_d, last_update_o, last_update_i]
    candidates = [c for c in candidates if c is not None]
    last_update = max(candidates) if candidates else None

    return records, last_update
    
def grist_get_data_table(base_url, doc_id, api_key, table_name, filter_epic_id=None , pi=0):
    filter_by_epic=None

    if filter_epic_id is not None:
        # Détermine le champ de liaison Epic et récupère les informations de l'Epic correspondant
        # Récupère les informations de l'Epic correspondant
        theepic = get_grist_epic_by_id(base_url, doc_id, api_key, filter_epic_id)
        fields = {
                "id": theepic.get("id"),
                **theepic.get("fields", {})
            }  
        filter_by_epic = fields.get("id_Epic")
        print(f"🔗 Champ de liaison trouvé : {filter_epic_id} = {filter_by_epic}")

    """
    Récupère l'ensemble des données depuis la source de données Grist.
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
                "type": table_name, # permet de différencier les types d'items
                "id": rec.get("id"),
                **rec.get("fields", {})
            }
            if table_name == "Features":
                # Normalise l'identifiant Grist vers id_feature pour la synchronisation.
                fields["id_feature"] = (
                    fields.get("id_feature")
                    or fields.get("id_Feature")
                    or fields.get("id2")
                )
            # Track the most recent update timestamp
            ts = _extract_last_update_epoch(rec)
            if ts is not None:
                last_update = ts if last_update is None else max(last_update, ts)
            #vérifie le PI si demandé
            try:
                pi_val = int(pi)
            except (ValueError, TypeError):
                pi_val = 0

            # Met à jour le dernier timestamp si nécessaire                
            # Si pi < 1, on considère que le filtre n'est pas appliqué (condition passante)
            if pi_val < 1 or str(fields.get("PI_Num")) == str(pi_val):

                if filter_epic_id is not None:
                    str1 = str(fields.get("id_Epic"))
                    str2 = str(filter_epic_id)
                    if str1 == str2:
                        records.append(fields)
                else:
                    records.append(fields)

        df = pd.DataFrame(records)
        print(f"✅ {len(df)} {table_name} récupérées depuis Grist .")
        if last_update:
            print(f"🕒 Dernière mise à jour (Unix): {last_update}")
        return df, last_update

    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la récupération des données Grist : {e}")
        return pd.DataFrame(), None

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
        if str(value) == str(item_id):
            return item

    print(f"⚠️ Aucun élément trouvé avec {field} = {item_id}")
    return None
