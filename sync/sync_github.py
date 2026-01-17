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
from sync.sync_utils import extract_id_and_clean_for_kind

# --- Activation et configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("sync_github")

# Chargement de la configuration depuis config.yaml ou config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"
with open(config_path, "r") as f:
    config = yaml.safe_load(f)


########### 
###########  Methodes pour gérer les interactions avec Github  ###########
###########

def github_get_organizations(organizations):
    org_list = []
    for org in organizations:
        org_list.append({"id": org, "name": org})
    return org_list

# récupération de la liste des projets GitHub (Projects V2) via GraphQL

def github_get_projects(github_token,org_name): 
    
    if not github_token or not org_name:
        logger.error("❌ Token GitHub manquant ou non défini dans l'environnement")
        return []    
    
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
        "Authorization": f"Bearer {github_token}",
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
            logger.warning(f"⚠️ Aucune organisation trouvée : {org_name}")
            return []

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

        # Tri alpha sur le nom du projet (insensible à la casse)
        project_list_sorted = sorted(
            project_list,
            key=lambda p: ((p.get("name") or "").strip().lower(), (p.get("id") or ""))
        )

        return project_list_sorted

    except requests.RequestException as e:  
        logger.error(f"❌ Erreur API GitHub : {e}")
        return []

###
### Crud des données des projets GitHub Issues via REST API v3
###

def github_get_project_objects(projectId, github_token):
    """
    Version compatible GitHub API v4 (GraphQL) fin 2024 / 2025.
    Récupère correctement les titres et descriptions des items Projects V2.
    Utilise extract_feature_id_and_clean() pour extraire Nom_Feature et id_feature.
    """
    import requests, re

    if not projectId or not github_token:
        logger.warning("⚠️ Paramètres GitHub manquants (projectId ou token).")
        return []
    logger.info(f"🔗 Project ID utilisé pour la requête GraphQL : {projectId}")
    
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
                databaseId
                number
                title
                body
                createdAt
                updatedAt            # last-modified timestamp for the issue
                repository {
                    nameWithOwner
                }
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
                databaseId
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

        nodes = (
            data.get("data", {})
            .get("node", {})
            .get("items", {})
            .get("nodes", [])
        )
        objects = []

        for node in nodes:
            content = node.get("content") or {}
            typename = content.get("__typename", "Unknown")
            title = content.get("title")
            body = content.get("body")
            state = content.get("state", "N/A")
            url_issue = content.get("url", "")
            number = content.get("number", "")
            updated = node.get("updatedAt")

            # Project item metadata
            project_item_id = node.get("id")  # ProjectV2Item.id
            project_item_updated_at = node.get("updatedAt")

            # Content metadata (Issue/PR/DraftIssue)
            id_Github_IssueGQL = content.get("id")  # GraphQL node id of Issue/PR/DraftIssue
            id_Github_Issue = content.get("databaseId")  # GraphQL node id of Issue/PR/DraftIssue

            timestamp_Issue = content.get("updatedAt")
            nameWithOwner = content.get("repository", {}).get("nameWithOwner", "")
            content_type = typename

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
            
            # Extraction de Nom_Feature et id_feature depuis le titre (et si issue idem pour body)      
            cleaned_text, detected_kind, pi_number, item_number = extract_id_and_clean_for_kind(title, kind=None)

            if detected_kind == "Issues" or detected_kind == "Features":
                objects.append({
                    "type": detected_kind,
                    "id_Github": project_item_id,
                    "id_Github_IssueGQL": id_Github_IssueGQL,
                    "timestamp_Issue": timestamp_Issue,
                    "id_Github_Issue": id_Github_Issue,
                    "Nom": cleaned_text or "(Sans Nom)",
                    **({"Description": body} if detected_kind == "Features" else {}),
                    "id_Num": item_number,
                    "pi_Num": pi_number,
                    "number": number,
                    "Etat": state,
                    "nameWithOwner": nameWithOwner,   
                    "Commentaires": url_issue,
                    "timestamp": project_item_updated_at,
                    "timestamp_Issue": timestamp_Issue
                })

        print(f"✅ {len(objects)} items récupérés depuis GitHub.")
        return objects

    except requests.RequestException as e:
        print(f"❌ Erreur API GitHub : {e}")
        return []


def github_project_board_create_objects(github_conf, context):
    """
    Crée dans iObeya les cards marquées 'create' dans iobeya_diff.
    """
    project_id = github_conf.get("project_id")
    api_key = github_conf.get("api_token")
    default_repo_full_name=github_conf.get("default_repo_full_name")

    try:
        created = []
        zorder = 100  # ordre d'empilement initial
        for item in context.get("github_diff", []):
            if item.get("action") == "create":
                feature_name = item.get("Nom")
                # recupère l'objet feature complet depuis le grist_objects
                feature = next((f for f in context.get("grist_objects", []) if f.get("Nom") == feature_name and f.get("type") == "Features"), None)
                
                if feature:
                    result = github_create_projet_Items(project_id, api_key, feature, labels="feature", repo_full_name=default_repo_full_name)
                    if result:
                        created.append(result)
                        zorder -= 1

        print(f"🟦 {len(created)} cards créées dans iObeya.")
        return created
    except Exception as e:
        logger.error(f"❌ Erreur lors de la création des cards iObeya : {e}", exc_info=True)
        return None


def github_create_projet_Items(project_id, github_token, feature, assignees=None, labels=None, repo_full_name=None):
    """
    Crée une issue GitHub à partir d'une donnée 'feature' standardisée.

    Args:
        project_id (str): identifiant du projet GitHub (GraphQL node ID du ProjectV2)
        github_token (str): jeton d'accès personnel GitHub (scope 'repo')
        feature (dict): dictionnaire contenant les données de la feature
        repo_full_name (str, optional): nom complet du dépôt GitHub (format "owner/repo") où créer l'issue.
    Kwargs:
        assignees (list, optional): liste de logins GitHub à assigner
        labels (list, optional): liste de labels à ajouter
    Returns:
        dict | None: Dictionnaire contenant la réponse GitHub si succès, sinon None
    """
    import requests

    # Extraction des champs
    title = feature.get("Nom", "Sans titre")
    body = "Description: " + feature.get("Description", "")
    body += "\n\n----\n"
    id_feature = feature.get("id_Num")
    pi_number = feature.get("pi_Num", "")

    # Calcul des méta-infos ( TODO : mettre le calcul de l'id_feature dans une fonction utilitaire partagée )
    Issue_title = f"[FP{pi_number}-{id_feature}] : {title}" if id_feature else f"[Feat]: {title}"
    hypothesis = feature.get("Hypotheses_de_gain", "")
    criterias = feature.get("Criteres_d_acceptation", "") 

    if not feature or "Nom" not in feature:
        print("⚠️ Donnée feature invalide ou incomplète.")
        return None
       
    # Déterminer le repo cible. ( priorité au repo du projet si vide on prend celui par défaut , sinon le premier repo repo_full_name.
    repos_url, owner, name, inferred_repo_full_name = _github_get_repo(project_id, github_token)
    effective_repo_full_name = ( inferred_repo_full_name or repo_full_name ).strip()
    
    if not effective_repo_full_name:
        logger.error(
            "❌ Impossible d'inférer le repository associé au ProjectV2 (project_id=%s). "
            "Veuillez specifier default_repo_full_name dans la configuration ou ajouter au moins une Issue/PR dans le projet.",
            project_id,
        )
        return None
    
   # Construire le corps de l'issue avec checklist et méta-infos    
    
    index = 0
    
    for line in hypothesis.splitlines():
        if line.strip():
            body += "\nHypothèse #"+ str(index) + " : " + line.strip()
            index += 1
    
    index = 0     
            
    for line in criterias.splitlines():
        if line.strip():
            body += "\nCritère #"+ str(index) + " : " + line.strip()

            index += 1
   
    # Ajoute un horodatage (date + heure) du moment de création côté synchro
    now_str = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    body += f"\n\n----\nCréé depuis Grist (synchro: {now_str})"
    
    # Label attendu (case-insensitive). GitHub conserve la casse d'origine,
    # mais l'API labels est insensible à la casse pour la recherche.
    label_name = "feature"

    payload = {
        "title": Issue_title,
        "body": body.strip(),
        "labels": [label_name]
    }

    # labels additionnels passés en param (en plus de "feature")

    # push des données vers GitHub via REST API v3
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json"
    }


    # Endpoints REST
    api_url_repo = f"https://api.github.com/repos/{effective_repo_full_name}"
    api_url_issues = f"{api_url_repo}/issues"

    # S'assurer que le label existe avant création d'issue
    try:
        _github_ensure_label_exists(
            api_url_repo=api_url_repo,
            headers=headers,
            label_name=label_name,
            color="5319e7",  # violet
            description="Label for features created via Grist sync",
        )
    except requests.exceptions.RequestException as e:
        logger.error(
            "❌ Impossible de vérifier/créer le label '%s' sur %s : %s",
            label_name,
            effective_repo_full_name,
            e,
            exc_info=True,
        )
        return None

    try:
        # 1) Création de l'Issue dans le repository cible
        response = requests.post(api_url_issues, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        issue_data = response.json()

        issue_number = issue_data.get("number")
        issue_title = issue_data.get("title")
        issue_node_id = issue_data.get("node_id")  # GraphQL contentId

        logger.info("✅ Issue créée dans %s : #%s %s", effective_repo_full_name, issue_number, issue_title)

        if not issue_node_id:
            logger.error(
                "❌ L'Issue créée ne contient pas de node_id (contentId) — impossible de l'ajouter au ProjectV2."
            )
            return issue_data

        # 2) Ajout de l'Issue au ProjectV2 (item)
        repos_url= repos_url.replace("projects", "projectsV2")
        repos_url= repos_url.replace("https://github.com/", "https://api.github.com/")
        #        projectsV2
        
        project_item_id = _github_add_issue_to_project(github_token, project_id=project_id, issue_id=issue_node_id)
        if project_item_id:
            logger.info("✅ Issue ajoutée au ProjectV2 (%s) : projectItemId=%s", project_id, issue_node_id)
            issue_data["project_item_id"] = project_item_id
        else:
            logger.warning("⚠️ Issue créée mais non ajoutée au ProjectV2 (project_id=%s)", project_id)

        return issue_data

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ Erreur lors de la création de l'issue GitHub : {e}", exc_info=True)
        return None


def _github_add_issue_to_project(github_token: str, project_id: str, issue_id: str) -> str:
    """Add an Issue (contentId / node_id) to a ProjectV2 and return the created project item id.

    Notes:
      - For Projects V2, adding content MUST be done via GraphQL mutation `addProjectV2ItemById`.
      - `project_id` is the GraphQL node ID of the ProjectV2.
      - `issue_id` is the GraphQL node ID of the Issue (contentId).

    Returns:
      - projectItemId (str) on success
      - "" (empty string) on failure
    """

    url = "https://api.github.com/graphql"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    query = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(
        input: {
          projectId: $projectId
          contentId: $contentId
        }
      ) {
        item {
          id
        }
      }
    }
    """

    variables = {
        "projectId": project_id,
        "contentId": issue_id,
    }

    try:
        r = requests.post(url, headers=headers, json={"query": query, "variables": variables}, timeout=15)
        r.raise_for_status()
        data = r.json()

        if "errors" in data:
            logger.error("⚠️ Erreurs GraphQL addProjectV2ItemById: %s", data.get("errors"))
            return ""

        item_id = (
            data.get("data", {})
            .get("addProjectV2ItemById", {})
            .get("item", {})
            .get("id")
        )

        if not item_id:
            logger.error("❌ addProjectV2ItemById: item.id manquant dans la réponse: %s", data)
            return ""

        return item_id

    except requests.exceptions.RequestException as e:
        logger.error("❌ Erreur API GitHub (addProjectV2ItemById): %s", e, exc_info=True)
        return ""
    
    
def github_update_issue_title_gql_label(
    github_token: str,
    nameWithOwner: str,
    id_Github_IssueGQL: str,
    issue_number: int ,
    new_title: str,
    add_feature_label: bool = True,
) -> bool:
    """
    Met à jour le titre d'une issue GitHub via son identifiant GraphQL (node_id),
    et optionnellement ajoute le label "feature" (via REST API v3).

    Args:
        github_token (str): Personal Access Token GitHub
        id_Github_IssueGQL (str): ID GraphQL de l'issue (ex: I_kwDO...)
        new_title (str): Nouveau titre
        repo_full_name (str, optional): "owner/repo" (requis pour ajouter un label via REST)
        issue_number (int, optional): numéro de l'issue (requis pour ajouter un label via REST)
        add_feature_label (bool): si True, tente d'ajouter le label "feature"

    Returns:
        bool: True si succès (titre + label si demandé), False sinon
    """

    if not github_token or not id_Github_IssueGQL or not new_title:
        logger.error("❌ Paramètres invalides pour updateIssue (GraphQL).")
        return False

    gql_url = "https://api.github.com/graphql"
    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    query = """
    mutation($issueId: ID!, $title: String!) {
      updateIssue(
        input: {
          id: $issueId
          title: $title
        }
      ) {
        issue {
          id
          number
          title
          updatedAt
        }
      }
    }
    """

    variables = {
        "issueId": id_Github_IssueGQL,
        "title": new_title,
    }

    try:
        # --- 1) Update title via GraphQL
        r = requests.post(
            gql_url,
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=10
        )
        r.raise_for_status()
        data = r.json()

        if "errors" in data:
            logger.error("❌ Erreurs GraphQL updateIssue: %s", data["errors"])
            return False

        issue = data["data"]["updateIssue"]["issue"]
        logger.info(
            "✏️ Titre mis à jour via GraphQL : #%s → %s",
            issue.get("number"),
            issue.get("title"),
        )

        # --- 2) Add "feature" label via REST (optional)
        
         # If issue_number is provided, we can infer repo_full_name from it
        
        if nameWithOwner and issue_number and add_feature_label :

            if not nameWithOwner or not issue_number:
                logger.warning(
                    "⚠️ Label 'feature' non ajouté : nameWithOwner/issue_number manquants "
                    "(nameWithOwner=%s, issue_number=%s).",
                    nameWithOwner,
                    issue_number,
                )
                return True  # titre OK, label ignoré faute d'infos

            labels_url = f"https://api.github.com/repos/{nameWithOwner}/issues/{issue_number}/labels"
            payload = {"labels": ["feature"]}

            r2 = requests.post(labels_url, headers=headers, json=payload, timeout=10)
            r2.raise_for_status()

            logger.info("🏷️ Label 'feature' ajouté (ou déjà présent) sur %s #%s", nameWithOwner, issue_number)

        return r2.json() is True

    except requests.exceptions.RequestException as e:
        logger.error(
            "❌ Erreur lors de la mise à jour du titre/label de l'issue : %s",
            e,
            exc_info=True,
        )
        return False
    
        
def github_update_issue_title_gql(
    github_token: str,
    issue_node_id: str,
    new_title: str
) -> bool:
    """
    Met à jour le titre d'une issue GitHub via son identifiant GraphQL (node_id).

    Args:
        github_token (str): Personal Access Token GitHub
        issue_node_id (str): ID GraphQL de l'issue (ex: I_kwDO...)
        new_title (str): Nouveau titre

    Returns:
        bool: True si succès, False sinon
    """
    import requests

    if not github_token or not issue_node_id or not new_title:
        logger.error("❌ Paramètres invalides pour updateIssue (GraphQL).")
        return False

    url = "https://api.github.com/graphql"

    headers = {
        "Authorization": f"Bearer {github_token}",
        "Accept": "application/vnd.github+json",
    }

    query = """
    mutation($issueId: ID!, $title: String!) {
      updateIssue(
        input: {
          id: $issueId
          title: $title
        }
      ) {
        issue {
          id
          number
          title
          updatedAt
        }
      }
    }
    """

    variables = {
        "issueId": issue_node_id,
        "title": new_title.strip()
    }

    try:
        r = requests.post(
            url,
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=10
        )
        r.raise_for_status()
        data = r.json()

        if "errors" in data:
            logger.error("❌ Erreurs GraphQL updateIssue: %s", data["errors"])
            return False

        issue = data["data"]["updateIssue"]["issue"]
        logger.info(
            "✏️ Issue mise à jour via GraphQL : #%s → %s",
            issue.get("number"),
            issue.get("title"),
        )
        return True

    except requests.exceptions.RequestException as e:
        logger.error(
            "❌ Erreur GraphQL lors de la mise à jour du titre de l'issue : %s",
            e,
            exc_info=True,
        )
        return False
    
    
def _github_ensure_label_exists(api_url_repo: str, headers: dict, label_name: str, color: str = "5319e7", description: str = ""):
    """Ensure a label exists on the repository.

    Uses REST API v3:
      - GET  /repos/{owner}/{repo}/labels/{name}
      - POST /repos/{owner}/{repo}/labels

    If the label is missing (404), it is created.
    """
    import requests

    # GitHub label endpoint is case-insensitive but returns stored casing.
    label_endpoint = f"{api_url_repo}/labels/{label_name}"
    r = requests.get(label_endpoint, headers=headers, timeout=10)
    if r.status_code == 200:
        return r.json()
    if r.status_code != 404:
        r.raise_for_status()

    payload = {
        "name": label_name,
        "color": str(color).lstrip("#"),
        "description": description or "",
    }
    r2 = requests.post(f"{api_url_repo}/labels", headers=headers, json=payload, timeout=10)
    r2.raise_for_status()
    logger.info("🏷️ Label '%s' créé sur %s", label_name, api_url_repo)
    return r2.json()


#####
##### Fonctions utilitaires internes
#####

def _github_get_repo(project_id, github_token):
    """
    Récupère le nom complet du dépôt (organisation/repo) associé à un project_id GitHub (ProjectV2).
    Retourne (url, owner, name, repo_full_name) où repo_full_name est inféré si possible à partir des items du projet.
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
          title
          owner {
            ... on Organization { login }
            ... on User { login }
          }
          url
          items(first: 50) {
            nodes {
              content {
                __typename
                ... on Issue {
                  repository { nameWithOwner }
                }
                ... on PullRequest {
                  repository { nameWithOwner }
                }
              }
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
        node = data.get("data", {}).get("node", {}) or {}
        owner = (node.get("owner") or {}).get("login")
        name = node.get("title")
        url = node.get("url")

        # Parse out repository names from items
        from collections import Counter

        repo_counts = Counter()
        items = node.get("items", {}).get("nodes", []) if node.get("items") else []
        for item in items:
            content = item.get("content") or {}
            typename = content.get("__typename")
            if typename in ("Issue", "PullRequest"):
                repo_obj = content.get("repository") or {}
                repo_name = repo_obj.get("nameWithOwner")
                if repo_name:
                    repo_counts[repo_name] += 1

        if repo_counts:
            # Mono-repo en pratique : on choisit le repo majoritaire ; tie-break stable (ordre alpha)
            repo_full_name = sorted(repo_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            if len(repo_counts) > 1:
                logger.warning(
                    "⚠️ Plusieurs repositories détectés dans les items du ProjectV2 : %s. "
                    "Repo choisi par majorité (mono-repo en pratique) : %s",
                    dict(repo_counts),
                    repo_full_name,
                )
        else:
            repo_full_name = None

        if not url:
            logger.error(
                "❌ Impossible de récupérer l'URL du ProjectV2 depuis GitHub. "
                "Project ID=%s.", project_id
            )
            return None
        if repo_full_name:
            logger.info(f"✅ Récupéré URL du ProjectV2 : {url} — repo inféré : {repo_full_name}")
        else:
            logger.info(f"✅ Récupéré URL du ProjectV2 : {url} — aucun repository inféré à partir des items.")
        return url, owner, name, repo_full_name
    
    except requests.RequestException as e:
        print(f"❌ Erreur lors de la récupération du dépôt GitHub pour le project_id {project_id} : {e}")
        return None    
    


