
# Nouvelle fonction utilitaire pour récupérer le nom complet du repo à partir du project_id GitHub
def get_repo_full_name_from_project_id(project_id, github_token):
    """
    Récupère le nom complet du dépôt (organisation/repo) associé à un project_id GitHub (ProjectV2).
    Retourne le nom complet du dépôt (str) ou None si non trouvé/erreur.
    """
    import requests
    graphql_url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }
    query = """
    query($projectId: ID!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          repository {
            nameWithOwner
          }
          owner {
            ... on Organization {
              login
            }
            ... on User {
              login
            }
          }
          repositories(first: 1) {
            nodes {
              nameWithOwner
            }
          }
        }
      }
    }
    """
    variables = {"projectId": project_id}
    try:
        resp = requests.post(graphql_url, headers=headers, json={"query": query, "variables": variables}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        node = data.get("data", {}).get("node", {})
        repo_full_name = None
        if node.get("repository") and node["repository"].get("nameWithOwner"):
            repo_full_name = node["repository"]["nameWithOwner"]
        elif node.get("repositories", {}).get("nodes"):
            repos = node["repositories"]["nodes"]
            if repos and repos[0].get("nameWithOwner"):
                repo_full_name = repos[0]["nameWithOwner"]
        elif node.get("owner", {}).get("login") and node.get("title"):
            repo_full_name = f"{node['owner']['login']}/{node['title']}"
        if not repo_full_name:
            print(f"❌ Impossible de déterminer le dépôt GitHub à partir du project_id {project_id}")
            return None
        return repo_full_name
    except requests.RequestException as e:
        print(f"❌ Erreur lors de la récupération du dépôt GitHub pour le project_id {project_id} : {e}")
        return None
import requests
from datetime import datetime
import pandas as pd
import uuid
import random
import json

def synchronize_all(grist_conf, iobeya_conf, github_conf, context):
    """
    Effectue la synchronisation complète entre Grist, iObeya et GitHub.

    Args:
        grist_conf (dict): paramètres Grist, ex:
            {
                "api_url": "...",
                "doc_id": "...",
                "api_token": "...",
                "feature_table_name": "Features"
            }
        iobeya_conf (dict): paramètres iObeya, ex:
            {
                "api_url": "...",
                "board_id": "...",
                "api_token": "..."
            }
        github_conf (dict): paramètres GitHub, ex:
            {
                "project_id": "...",
                "token_env_var": "..."
            }
        context (dict): informations de synchronisation, ex:
            {
                "github_diff": [...],
                "iobeya_diff": [...],
                "epics_list": [...],
                "epic_id": "...",
                "rename_deleted": True/False,
                "force_overwrite": True/False,
                "pi": "PI-04"
            }

    Returns:
        dict: résultat de la synchronisation (succès, erreurs, statistiques, etc.)
    """

    print("🚀 Démarrage de synchronize_all()")
    print(f"PI : {context.get('pi')} | Force overwrite : {context.get('force_overwrite')}")

    result = {
        "status": "started",
        "grist_synced": False,
        "iobeya_synced": False,
        "github_synced": False,
        "details": {}
    }

    try:
        # Étape 0 — Si force_overwrite est false on commence par créer les features manquantes dans grist
        if not context.get("force_overwrite", False):
            print("🔁 Création des features manquantes dans Grist...")
            create_missing_features_in_grist(grist_conf, context)
            
        # Étape 1 — Synchronisation Grist → iObeya
        print("🔁 Synchronisation Grist → iObeya en cours...")
        # TODO: appel logique d’import / export ici
        result["iobeya_synced"] = True

        # Étape 2 — Synchronisation Grist → GitHub
        print("🔁 Synchronisation Grist → GitHub en cours...")
        # TODO: appel logique d’import / export ici
        result["github_synced"] = True

        result["status"] = "success"
        print("✅ Synchronisation terminée avec succès.")

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        print(f"❌ Erreur dans synchronize_all : {e}")

    return result


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


def create_github_issue_from_feature(project_id, github_token, feature, assignees=None, labels=None):
    """
    Crée une issue GitHub à partir d'une donnée 'feature' standardisée.

    Args:
        project_id (str): identifiant du projet GitHub (GraphQL node ID du ProjectV2)
        github_token (str): jeton d'accès personnel GitHub (scope 'repo')
        feature (dict): dictionnaire de feature contenant :
            {
                "id_GitHub",
                "Nom_Feature",
                "id_feature",
                "Description",
                "Etat",
                "extra",
                "number"
            }
        assignees (list, optional): liste de logins GitHub à assigner
        labels (list, optional): liste de labels à ajouter
    Returns:
        dict | None: Dictionnaire contenant la réponse GitHub si succès, sinon None
    """
    import requests

    if not feature or "Nom_Feature" not in feature:
        print("⚠️ Donnée feature invalide ou incomplète.")
        return None

    # Etape 1 : Récupérer le nom complet du dépôt (organisation/repo) à partir de project_id via la fonction utilitaire
    repo_full_name = get_repo_full_name_from_project_id(project_id, github_token)
    if not repo_full_name:
        print(f"❌ Impossible de déterminer le dépôt GitHub à partir du project_id {project_id} (via get_repo_full_name_from_project_id)")
        return None
    
    title = feature.get("Nom_Feature", "Nouvelle feature")
    # Ajout automatique de l’identifiant dans le titre pour traçabilité
    if feature.get("id_feature"):
        title = f"[{feature['id_feature']}]: {title}"
        body = feature.get("Description", "")
        etat = feature.get("Etat")
        extra = feature.get("extra")

    # Ajout d’un bloc d’infos formaté dans la description
    body += "\n\n---\n🧩 **Méta-informations**\n"
    body += f"- État : {etat or 'N/A'}\n"
    if extra:
        body += f"- Source : {extra}\n"

    url = f"https://api.github.com/repos/{repo_full_name}/issues"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }

    payload = {
        "title": title,
        "body": body.strip(),
    }
    if assignees:
        payload["assignees"] = assignees
    if labels:
        payload["labels"] = labels

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Issue créée : #{data.get('number')} {data.get('title')}")
        print(f"🔗 URL : {data.get('html_url')}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"❌ Erreur lors de la création de l'issue GitHub : {e}")
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
    print(f"🔗 Project ID utilisé pour la requête GraphQL : {projectId}")
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
        items(first: 50) {
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
                ... on DraftIssue {
                title
                body
                createdAt
                updatedAt            # last-modified timestamp for the issue
                }
                ... on Issue {
                id
                number
                title
                body
                createdAt
                updatedAt            # last-modified timestamp for the issue
                comments(first: 20) {
                    totalCount
                    pageInfo { hasNextPage endCursor }
                    nodes {
                        body
                        bodyText     # rendered to plain text
                        author { login }
                        createdAt
                        updatedAt            # last-modified timestamp for the issue
                    }
                }
                assignees(first: 10) { nodes { login } }
                }
                ... on PullRequest {
                id
                number
                title
                body
                createdAt
                updatedAt            # last-modified timestamp for the issue
                comments(first: 20) {
                    totalCount
                    pageInfo { hasNextPage endCursor }
                    nodes {
                        body
                        bodyText     # rendered to plain text
                        author { login }
                        createdAt
                        updatedAt            # last-modified timestamp for the issue
                    }
                }
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

        print("🧩 GraphQL raw response keys:", list(data.keys()))
        project_node = data.get("data", {}).get("node", {})
        print("📦 Project node keys:", list(project_node.keys()))
        print("📄 Sample raw JSON (truncated):")
        print(json.dumps(data, indent=2)[:2000])  # print the first 2000 chars to avoid overload


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

            # Ajout récupération et concaténation des commentaires dans body
            comments_data = content.get("comments", {}).get("nodes", [])
            if comments_data:
                comments_text = "\n".join(
                    f"[{c.get('author', {}).get('login', 'inconnu')}] {c.get('body', '').strip()}"
                    for c in comments_data if c.get("body")
                )
                if comments_text:
                    body = (body or "") + "\n\n---\n💬 Commentaires GitHub :\n" + comments_text

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
        
def get_grist_features(base_url, doc_id, api_key, table_name="Features", filter_epic_id=None , pi=0):
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
            #vérifie le PI si demandé
            try:
                pi_val = int(pi)
            except (ValueError, TypeError):
                pi_val = 0

            # Arrêt anticipé si l'id_Epic correspond à 17
            if str(fields.get("id_Epic", "")) == "17":
                print(f"⏹️ Arrêt : feature liée à l'id_Epic=17 détectée -> {fields.get('Nom_Feature')}")
                
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
                        "id_feature": if_feature
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

def compute_diff(grist_features, dest_features, rename_deleted=False, epic=None):
    """
    Compare les features de Grist et d'iObeya pour déterminer les actions à effectuer.
    - Si la feature existe dans les deux, compare le titre et la description.
    - Si différence, détermine la source en fonction du timestamp le plus récent.
    - Si rename_deleted=True, remplace la suppression par un renommage en 'del_...'.
    - Si une feature existe uniquement dans dest_features, action = "not_present" (pour réimporter dans Grist (bi-directionnel ou synchroniser forcer qui entraîne un effacement)).
    Retourne une liste de différences :
    [{"id": id_feature, "action": "create"|"update_grist"|"update_iobeya"|"not_present"|"delete"|"none"|"manual_check", "feature": {...}}]
    """
    diff_list = []
    grist_dict = {str(f.get("id_feature")): f for f in grist_features if f.get("id_feature")}
    dest_dict = {str(f.get("id_feature")): f for f in dest_features if f.get("id_feature")}

    all_ids = set(grist_dict.keys()) | set(dest_dict.keys())

    for fid in all_ids:
        g_feat = grist_dict.get(fid)
        i_feat = dest_dict.get(fid)

        # Cas 1 : création — présent dans Grist uniquement
        if g_feat and not i_feat:
            diff_list.append({"id": fid, "action": "create", "feature": g_feat})

        # Cas 2 : suppression — présent dans dest uniquement (mais si on souhaite rapatrier, alors "not_present")
        elif not g_feat and i_feat:
            if epic:
                # Réimport d'une nouvelle feature depuis dest vers Grist
                new_feat = dict(i_feat)
                new_feat["id_Epic"] = epic
                diff_list.append({"id": fid, "action": "not_present", "feature": new_feat})
            elif rename_deleted:
                updated = dict(i_feat)
                updated["Nom_Feature"] = f"del_{i_feat.get('Nom_Feature', '')}"
                diff_list.append({"id": fid, "action": "update", "feature": updated})
            else:
                diff_list.append({"id": fid, "action": "delete", "feature": i_feat})

        # Cas 3 : présent dans les deux
        elif g_feat and i_feat:
            g_name = (g_feat.get("Nom_Feature") or "").strip()
            i_name = (i_feat.get("Nom_Feature") or "").strip()
            g_desc = (g_feat.get("Description") or "").strip()
            i_desc = (i_feat.get("Description") or "").strip()

            if g_name != i_name or g_desc != i_desc:
                try:
                    g_time = datetime.fromisoformat(str(g_feat.get("timestamp")))
                    i_time = datetime.fromisoformat(str(i_feat.get("timestamp")))
                except Exception:
                    g_time = i_time = None

                if g_time and i_time:
                    if g_time > i_time:
                        diff_list.append({"id": fid, "action": "update_iobeya", "feature": g_feat})
                    elif i_time > g_time:
                        diff_list.append({"id": fid, "action": "update_grist", "feature": i_feat})
                    else:
                        diff_list.append({"id": fid, "action": "none", "feature": g_feat})
                else:
                    # Si timestamp absent ou invalide
                    diff_list.append({"id": fid, "action": "manual_check", "feature": g_feat})
            else:
                diff_list.append({"id": fid, "action": "none", "feature": g_feat})

    # Résumé des actions
    stats = {a: sum(1 for d in diff_list if d["action"] == a)
             for a in ["create", "update_iobeya", "update_grist", "not_present", "delete", "manual_check", "none"]}

    print(f"📊 Différences calculées : {len(diff_list)} au total")
    for k, v in stats.items():
        print(f"  • {k} : {v}")

    return diff_list


# Nouvelle fonction pour créer dans Grist les features absentes (action = 'not_present') à partir des diffs iObeya et GitHub
def create_missing_features_in_grist(grist_conf, context):
    """
    Crée dans Grist les features présentes dans iObeya ou GitHub
    mais absentes de Grist (action = 'not_present').
    """
    created = []
    api_url = grist_conf.get("api_url")
    doc_id = grist_conf.get("doc_id")
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