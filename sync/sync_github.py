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
                    "id_GitHub": node.get("id"),
                    "Nom_Feature": cleaned_text or "(Sans titre)",
                    **({"Nom_Feature": cleaned_text} if detected_kind == "Features" else {}),
                    **({"Description": body} if detected_kind == "Features" else {}),
                    **({"Description": cleaned_text} if detected_kind == "Issues" else {}),
                    "id_Num": item_number,
                    "pi_num": pi_number,
                    "Etat": state,
                    "Commentaires": url_issue,
                    "timestamp": updated
                })

        print(f"✅ {len(objects)} items récupérés depuis GitHub.")
        return objects

    except requests.RequestException as e:
        print(f"❌ Erreur API GitHub : {e}")
        return []

def github_create_issue(project_id, github_token, feature, assignees=None, labels=None):
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
    repo_full_name = github_get_repo_full_name(project_id, github_token)
    if not repo_full_name:
        print(f"❌ Impossible de déterminer le dépôt GitHub à partir du project_id {project_id} (via get_repo_full_name)")
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


#####
##### Fonctions utilitaires internes
#####


# utilitaire pour récupérer le nom complet du repo à partir du project_id GitHub
def github_get_repo_full_name(project_id, github_token):
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
    


