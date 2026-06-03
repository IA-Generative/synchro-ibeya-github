## Import des modules nécessaires

import pandas as pd
import random
import re  
import requests
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))) ##include the parent directory for module imports
import yaml
from datetime import datetime, timezone
import logging

# --- Activation et configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("sync_grist")
    
from sync.sync_iobeya import (
    iobeya_update_object_title_prefix
)    

from sync.sync_github import (
    github_update_issue_title_gql,
    github_update_issue_title_gql_label
) 


###########    
###########    Methodes pour gérer les interactions avec Grist  ###########
###########

def grist_get_doc_name(base_url, doc_id, api_token):
    """Retourne le nom du document Grist à partir de son ID."""
    
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Accept": "application/json"
    }
    
    try:
        url = f"{base_url}/api/docs/{doc_id}"
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("name", f"(Doc {doc_id} sans nom)")
    
    except Exception as e:
        logger.warning(f"⚠️ Erreur récupération nom du doc Grist ({doc_id}) : {e}")
        return f"(Doc {doc_id} inconnu)"

### récupération des epics dans une list 

def grist_get_epics(base_url, doc_id, api_key, table_name="Epics"):
    
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
                    "id": record_id, # identifiant interne Grist
                    "id_epic": id_epic,
                    "name": epic_name
                })
                
        epics = _sort_epics_by_name(epics, key_name="name")
        logger.info(f"✅ {len(epics)} épics récupérés depuis Grist (triés par nom).")

        return epics
    
    except requests.RequestException as e:
        logger.warning(f"⚠️ Erreur API Grist : {e}")
        return []
    
def _sort_epics_by_name(epics, key_name="name"):
    """
    Trie une liste d'EPICS par ordre alphabétique selon le nom de l'epic.
    :param epics: liste de dictionnaires EPIC
                  ex: {"id": ..., "id_epic": ..., "name": ...}
    :param key_name: clé du nom à utiliser pour le tri (par défaut "name")
    :return: nouvelle liste triée (sans modifier l'originale)
    """
    if not isinstance(epics, list):
        return []

    return sorted(
        epics,
        key=lambda e: (e.get(key_name) or "").strip().lower()
    )    
    
# Fonction pour récupérer un objet Epic spécifique par l'un des identifiants possible
def grist_get_epic(base_url, doc_id, api_key, epic_id, table_name="Epics"):
    
    """
    Récupère le contenu complet d'un Epic à partir de son identifiant manuel id_epic.
    note : la colonne id_Epic est numérotée manuelle par l'utilisateur dans grist
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

        if not data:
            return None

        records = data.get("records", [])

        # 1) Tentative: epic_id est l'ID interne Grist (record id)
        the_epic = find_item_by_id(records, epic_id, "id")

        # 2) Fallback: epic_id correspond à l'identifiant manuel (id_Epic/id_epic/id2)
        if the_epic is None:
            for rec in records:
                fields = rec.get("fields", {}) or {}
                manual = fields.get("id_Epic") or fields.get("id_epic") or fields.get("id2")
                if manual is not None and str(manual) == str(epic_id):
                    the_epic = rec
                    break

        if the_epic is None:
            logger.warning(f"⚠️ Epic introuvable dans Grist pour epic_id={epic_id}.")
            return None

        # simplification de l'objet epic pour faciliter les comparaisons
        return {
            "id": the_epic.get("id"),
            **(the_epic.get("fields", {}) or {}),
        }

    except requests.RequestException as e:
        logger.warning(f"❌ Erreur lors de la récupération de l'Epic {epic_id} : {e}")
        return None

### récupération de tous les objets liés à un epic spécifique

def grist_get_epic_objects(base_url, doc_id, api_key, filter_epic_id=None , pi=0):

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

    try:
        features, last_update_f = grist_get_epic_object(base_url, doc_id, api_key, "Features", filter_epic_id , pi)
        risks, last_update_r = grist_get_epic_object(base_url, doc_id, api_key, "Risques", filter_epic_id , pi)
        dependances, last_update_d = grist_get_epic_object(base_url, doc_id, api_key, "Dependances", filter_epic_id , pi)
        objectives, last_update_o = grist_get_epic_object(base_url, doc_id, api_key, "Objectives", filter_epic_id , pi)
        issues, last_update_i = grist_get_epic_object(base_url, doc_id, api_key, "Issues", filter_epic_id , pi)             

        # Initialize records as DataFrame
        records = pd.DataFrame()
    
        # Concat (DataFrames) -> single DataFrame (expected by app.py)
    
        dfs = [df for df in (features, risks, dependances, objectives, issues)
            if isinstance(df, pd.DataFrame) and not df.empty]
        
        records = pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
        logger.info(f"✅ Total {len(records)} objets récupérés pour l'Epic {filter_epic_id} depuis Grist.")
            
        # Compute the most recent last_update among all tables ( computed mais pas utilisé pour l'instant )
        candidates = [last_update_f, last_update_r, last_update_d, last_update_o, last_update_i]
        candidates = [c for c in candidates if c is not None]
        last_update = max(candidates) if candidates else None

        return records
    
    except Exception as e:
        logger.warning(f"❌ Erreur lors de la récupération des objets de l'Epic {filter_epic_id} : {e}")
        return None

###
### Fonction pour récuperer / créer dans Grist les objets
###    
   
def grist_get_epic_object(base_url, doc_id, api_key, table_name, filter_epic_id=None , pi=0):
    """
    Récupère l'ensemble des données depuis la source de données Grist.
    Retourne un tuple (DataFrame pandas, dernier_timestamp).
    """
        
    # Détermine le champ de liaison Epic et récupère les informations de l'Epic correspondant
    # Récupère les informations de l'Epic correspondant
    
    if filter_epic_id is not None:
        epic = grist_get_epic(base_url, doc_id, api_key, filter_epic_id)
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    try:
        url = f"{base_url}/api/docs/{doc_id}/tables/{table_name}/records"
        url = url.replace('://', '§§').replace('//', '/').replace('§§', '://')
        
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()

        records = []
        last_update = None

        for rec in data.get("records", []):
            fields = {
                "type": table_name, # permet de différencier les types d'items
                "id": rec.get("id"),
                "id_Epic": epic.get("id_Epic") if filter_epic_id else None,
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
            if pi_val < 1 or str(fields.get("pi_Num")) == str(pi_val):

                if filter_epic_id is not None:
                    str1 = str(fields.get("Epic"))
                    str2 = str(epic.get("id"))
                    if str1 == str2:
                        records.append(fields)
                else:
                    records.append(fields)

        df = pd.DataFrame(records)
        logger.info(f"✅ {len(df)} {table_name} récupérées depuis Grist .")
        if last_update:
            try:
                last_update_dt = datetime.fromtimestamp(float(last_update), tz=timezone.utc)
                logger.info(
                    f"🕒 Dernière mise à jour: {last_update_dt.isoformat()} (UTC) | epoch={last_update}"
                )
            except Exception as e:
                logger.info(f"🕒 Dernière mise à jour (epoch): {last_update} (conversion date impossible: {e})")
        return df, last_update

    except requests.exceptions.RequestException as e:
        logger.warning(f"❌ Erreur lors de la récupération des données Grist : {e}")
        return pd.DataFrame(), None
    
### Création des objets lié à un EPIC / PI pi number
#   dans Grist si "action = 'not_present'" partir du fichier de diffs issue d'iObeya et GitHub    
# NOTE / TODO : Pour se rappeller 
# >> si synchronisation est bidirectionnelle 
# elle doit également tenir compte des updates entre les deux systèmes iobeya et github... 
# ex: lancer une deuxième synchronisation après la création des éléments manquants ? )

def grist_create_epic_objects(grist_conf, iobeya_conf,github_conf,context):
    """
    Crée dans Grist les features présentes dans iObeya ou GitHub
    mais absentes de Grist (action = 'not_present').
    """
    wrapper = context or {}
    # `sync.py` passe un wrapper contenant `session_data` (les listes) + des clés top-level
    session_data = wrapper.get("session_data", wrapper)
    iobeya_objects = session_data.get("iobeya_objects", [])
    github_objects = session_data.get("github_objects", [])
    grist_objects = session_data.get("grist_objects", [])

    if not grist_conf or session_data is None:
        logger.warning("❌ Configuration Grist ou données de session manquantes.")
        return []

    # Les listes peuvent être vides : ce n'est pas bloquant.
    iobeya_objects = iobeya_objects or []
    github_objects = github_objects or []
    grist_objects = grist_objects or []

    # récupère les variables de contexte nécessaires
    api_url = grist_conf.get("api_url")
    doc_id = grist_conf.get("doc_id")
    api_token = grist_conf.get("api_token")
    pi_Num = wrapper.get("pi_num", 0)
    
    # Epic sélectionné : pour que le put API fonctionne il faut utiliser le meme type de colonne que dans grist
    # Ici c'est la colonne Nom de la table Epics qui est utilisée

    epic_Name = None

    id_Epic = wrapper.get("id_Epic") or wrapper.get("epic_id")
    grist_epics = wrapper.get("grist_epics")   
    grist_epics = _ensure_list(grist_epics)
    the_epic = find_item_by_id(grist_epics, id_Epic, "id")

    if the_epic is None:
        logger.warning("❌ Aucun Epic sélectionné (id_Epic/epic_id absent du contexte).")
        return []
    
    epic_Name = the_epic.get("name") if isinstance(the_epic, dict) else None  # Grist utilisera le nom de l'epic pour faire le match d'une référence

    # Identifiant manuel de l'epic (utilisé dans certains préfixes). On le normalise (str + strip)
    # pour éviter les concat/espaces parasites.
    epic_id = (the_epic.get("id_epic") if isinstance(the_epic, dict) else None)
    epic_id = str(epic_id).strip() if epic_id is not None else ""

    # Normalisation PI (souvent reçu en int ou en str depuis l'UI/API)
    pi_Num = str(pi_Num).strip() if pi_Num is not None else ""
    
    #rename_deleted = context.get("rename_deleted", False)
    #force_overwrite = context.get("force_overwrite", False)    

    # initialisations
    created = []
    failed = []
    combined_diffs = []

    # on compile les id numériques max déjà utilisés par type d'objet dans grist (par epic / pi num)
    # (on calcule à partir des objets déjà présents dans Grist)
    max_ids = _compute_max_id_by_type(grist_objects, pi_num=pi_Num)

    # Fusion des diffs iObeya et GitHub pour créer les onjets manquants dans Grist
    # todo ajouter un champ source dans les diffs pour savoir d'où vient l'objet (iobeya/github) et l'id de l'objets source 
    
    for item in wrapper.get("iobeya_diff", []):
        if item.get("action") == "not_present":
            # ici il faut recupérer l'objet complet depuis la source ( on ignore l'id car vide )
            Nom = item.get("Nom")
            type = item.get("type")
            obj = _find_item(iobeya_objects, Nom, type)
            if not obj:
                logger.warning(f"⚠️ Objet iObeya introuvable pour création (Nom={Nom}, type={type}).")
                continue
            obj["source"] = "iobeya"
            combined_diffs.append(obj)

    for item in wrapper.get("github_diff", []):
        if item.get("action") == "not_present":
            # ici il faut recupérer l'objet complet depuis la source ( on ignore l'id car vide )
            Nom = item.get("Nom")
            type = item.get("type")
            obj = _find_item(github_objects, Nom, type)
            if not obj:
                logger.warning(f"⚠️ Objet GitHub introuvable pour création (Nom={Nom}, type={type}).")
                continue
            obj["source"] = "github"
            combined_diffs.append(obj)

    logger.info(f"🧩 {len(combined_diffs)} features à créer dans Grist (not_present).")

    # Création des objets manquants dans Grist
    # l'id_epic est implicite au contexte de la synchro 
    # La syntaxe des variables utilisé ici est volontairement identique de celle utilisée des objets dans Grist y/c la casse
     
    for object in combined_diffs:

        # valeurs obligatoires / communes
        type = object.get("type", "Features")  # le type est également le nom de la table Grist
        Nom = object.get("Nom", "Sans titre")
        Description = object.get("Description", "")
        timestamp = object.get("timestamp", datetime.now().timestamp())
        source = object.get("source", "∅")

        # valeurs optionnelles
        Hypotheses_de_gain = object.get("Hypotheses_de_gain", None)
        Criteres_d_acceptation = object.get("Criteres_d_acceptation", None)
        Committed = object.get("Committed", None)

        # calcul de l'identifiant numérique de l'objet à créer (on prend la valeur max + 1)
        next_id = int(max_ids.get(type, 0)) + 1
        max_ids[type] = next_id
        id_Num = next_id

        result = grist_create_object(
            base_url=api_url,
            doc_id=doc_id,
            api_key=api_token,
            type=type,
            Epic=epic_Name,
            pi_Num=pi_Num,
            id_Num=id_Num,
            timestamp=timestamp,
            Nom=Nom,
            Description=Description,
            Hypotheses_de_gain=Hypotheses_de_gain,
            Criteres_d_acceptation=Criteres_d_acceptation,
            Commentaires=f"Créé via synchronisation depuis {source}, le {datetime.now().strftime('%Y-%m-%d')}",
            Committed=Committed
        )
        
        # ajouter les informations de source / contexte si besoin
        # calcule de l'id_de l'objet du grist à partir de l'objet créé
        # TODO : à refactorer plus tard ( mettre dans une fonction dédiée dans sync utils par exemple )

        if result:
            id3_str = str(id_Num).zfill(3)  # formatage avec zéros initiaux

            id_objet_prefix = ""
            if type == "Features":
                id_objet_prefix = f"FP{pi_Num}-{id3_str}"
            if type == "Dependances":
                id_objet_prefix = f"DP{pi_Num}-{id3_str}"
            if type == "Objectives":
                cmt = str(Committed).strip().lower()
                
                COMMITTED_VALUES = {
                    "committed",
                    "yes",
                    "oui",
                    "true",
                    "1",
                    "x"
                }

                prefix = "TObjP" if cmt in COMMITTED_VALUES else "uTObjP"
                id_objet_prefix = f"{prefix}{pi_Num}-{id3_str}"
            if type == "Issues":
                id_objet_prefix = f"IssueP{pi_Num}-{id3_str}"
            if type == "Risques":
                id_objet_prefix = f"RP{pi_Num}-{id3_str}"
                                
                
            result["id_Objet"] = id_objet_prefix
            result["source"] = source

            # todo à refactorer plus tard ( mettre dans une fonction dédiée )
            # mise à jour des objects créés avec l'id_Objet calculé

            if source == "iobeya":
                result["source"] = source

                # on récupére l'objet iobeya correspondant pour faire la mise à jour
                #iobeya_object = find_item_by_id(iobeya_objects, Nom, "Nom")

                # on met à jour le titre de la carte iobeya pour y inclure
                iobeya_api_url = iobeya_conf.get("api_url", [])
                iobeya_api_token = iobeya_conf.get("api_token", [])
                object_id = object.get("uid", "")
                new_title = f"[{id_objet_prefix}] : {Nom}"
                res = iobeya_update_object_title_prefix(iobeya_api_url, iobeya_api_token, new_title, object_id)
                result["update_iobeyacard_title"] = res

            if source == "github":
                result["source"] = source
                # on met à jour le titre de l'issue de graphQl pour y inclure l'identifiant en prefixe
                github_token = github_conf.get("api_token", "")
                new_title = f"[{id_objet_prefix}] : {Nom}"
                object_id = object.get("id_Github_Issue", "")
                number = object.get("number", "")
                id_Github_IssueGQL = object.get("id_Github_IssueGQL", "")
                nameWithOwner = object.get("nameWithOwner", "")

                #res = github_update_issue_title_gql( github_token, id_Github_IssueGQL, new_title) 
                res = github_update_issue_title_gql_label(github_token, nameWithOwner, id_Github_IssueGQL, number, new_title, add_feature_label = True)
                result["update_github_issue_title"] = res
                
            # Si création réussie, on ajoute à la liste des créés et gardant depuis quel source
            created.append(result)
        else:
            # Échec de création (ex: 403 Forbidden sur la table cible) : ne pas l'avaler.
            failure = {
                "type": type,
                "Nom": Nom,
                "source": source,
                "number": object.get("number", ""),
                "nameWithOwner": object.get("nameWithOwner", ""),
                "doc_id": doc_id,
            }
            failed.append(failure)
            logger.warning(
                "⛔ Échec de création dans Grist : table=%s | Nom=%r | source=%s | github#%s | doc=%s "
                "(voir l'erreur HTTP ci-dessus ; 403 = droits d'écriture insuffisants sur la table %s).",
                type, Nom, source, failure["number"], doc_id, type,
            )
            
    ## todo : pensez à ajouter des fonction de CRUD dans iobeya et github ? (dans la methode appellante ) 
    
    if failed:
        logger.warning(
            "⚠️ Bilan création Grist : %d réussie(s), %d échec(s). Objets en échec : %s",
            len(created), len(failed),
            [f"{f['type']}:{f['Nom']!r}(github#{f['number']})" for f in failed],
        )
    else:
        logger.info(f"✅ {len(created)} features créées dans Grist (0 échec).")

    # Remonte le bilan dans le contexte de sync pour exposition côté résultat/UI.
    wrapper["grist_create_stats"] = {
        "created": len(created),
        "failed": len(failed),
        "failures": failed,
    }
    return created


###
### Ensemble des fonction CRUD pour les features
###

# fonction pour créer une feature dans Grist

def grist_create_object(
    base_url, doc_id, api_key, 
    type, Epic, pi_Num , id_Num, timestamp ,
    Nom , Description ,
    Hypotheses_de_gain , Criteres_d_acceptation ,
    Commentaires, Committed
):

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # Construction des champs en filtrant les valeurs None / vides
    fields = {
        "Epic": Epic,            
        "pi_Num": pi_Num,
        "id_Num": id_Num,
        "Nom": Nom,
        "Description": Description,
        "Hypotheses_de_gain": Hypotheses_de_gain,
        "Commentaires": Commentaires,
        "Criteres_d_acceptation": Criteres_d_acceptation,
        "Committed": Committed,
        "timestamp": timestamp,
    }

    # Supprime les champs None, vides ou chaînes vides
    fields = {
        k: v
        for k, v in fields.items()
        if v is not None and not (isinstance(v, str) and v.strip() == "")
    }

    payload = {
        "records": [
            {
                "fields": fields
            }
        ]
    }

    url = f"{base_url}/api/docs/{doc_id}/tables/{type}/records"
    url = url.replace('://', '§§').replace('//', '/').replace('§§', '://')

    response = None
    try:
        response = requests.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        logger.info(f"✅ objet créé avec succès dans Grist : {type} / {data}")
        return data

    except requests.exceptions.RequestException as e:
        # Log détaillé : statut + corps de la réponse Grist (qui nomme la colonne/raison)
        # + colonnes effectivement envoyées, pour diagnostiquer un modèle de table modifié.
        status = getattr(response, "status_code", "?")
        body = ""
        try:
            if response is not None:
                body = response.text[:1000]
        except Exception:
            pass
        logger.warning(
            "❌ Erreur création %s (HTTP %s) : %s | colonnes envoyées=%s | réponse Grist=%s",
            type, status, e, sorted(fields.keys()), body,
        )
        return None

### UTILITAIRES

# -- Fonction utilitaire pour retrouver un élément par identifiant dans une liste de dictionnaires

def find_item_by_id(items, item_id, field="id"):
    """
    Retourne le dictionnaire dont le champ 'field' correspond à item_id.
    Si aucun élément ne correspond, retourne None.
    Ajoute des logs détaillés pour le débogage.
    """
    items = _ensure_list(items)
    
    for idx, item in enumerate(items):
        value = item.get(field)
        if str(value) == str(item_id):
            return item

    logger.warning(f"⚠️ Aucun élément trouvé avec {field} = {item_id}")
    return None

###  -- pour parser les timestamps

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


def _find_item(objects, name, type):
    """Trouve un objet par nom et type.

    Selon la source (Grist/iObeya/GitHub), la clé du nom peut être `Nom` ou `name`.
    """
    return next(
        (
            o
            for o in objects
            if (o.get("Nom") == name or o.get("name") == name)
            and o.get("type") == type
        ),
        None,
    )
    
    
from collections import defaultdict

def _compute_max_id_by_type(objects, id_field="id_Num", type_field="type", pi_field="pi_Num", pi_num=None):
    """
    Calcule le max id_Num par type.
    Ignore les valeurs None, vides ou non numériques.
    Retourne un dict: {type: max_id}
    """
    max_by_type = defaultdict(int)

    for obj in objects:
        obj_type = obj.get(type_field)
        raw_id = obj.get(id_field)

        if not obj_type or raw_id is None:
            continue

        # Optional filter by PI number (string/int safe compare)
        if pi_num is not None:
            obj_pi = obj.get(pi_field)
            if obj_pi is None:
                continue
            if str(obj_pi).strip() != str(pi_num).strip():
                continue

        try:
            id_num = int(str(raw_id).strip())
        except (ValueError, TypeError):
            continue

        if id_num > max_by_type[obj_type]:
            max_by_type[obj_type] = id_num

    return dict(max_by_type)


def _compute_global_max_id(objects, id_field="id_Num"):
    """Calcule le max global de `id_field` sur l'ensemble des objets (tous types confondus).

    Ignore les valeurs None, vides ou non numériques.
    Retourne un int (0 si aucun id valide).
    """
    max_id = 0
    for obj in objects:
        raw_id = obj.get(id_field)
        if raw_id is None:
            continue
        try:
            id_num = int(str(raw_id).strip())
        except (ValueError, TypeError):
            continue
        if id_num > max_id:
            max_id = id_num
    return max_id


def _ensure_list(obj):
    """Transforme au mieux un objet en liste."""
    if obj is None:
        return []
    if isinstance(obj, list):
        return obj
    if isinstance(obj, tuple):
        return list(obj)

    # dict qui contient une liste
    if isinstance(obj, dict):
        for k in ("records", "items", "data", "results"):
            v = obj.get(k)
            if isinstance(v, list):
                return v
        return []

    # Flask Response
    get_json = getattr(obj, "get_json", None)
    if callable(get_json):
        try:
            return _ensure_list(get_json(silent=True))
        except Exception:
            return []

    # requests.Response
    json_fn = getattr(obj, "json", None)
    if callable(json_fn):
        try:
            return _ensure_list(json_fn())
        except Exception:
            return []

    return []