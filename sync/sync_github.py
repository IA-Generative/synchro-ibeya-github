import json
import os, sys
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import yaml

from sync.sync_utils import extract_feature_id_and_clean

# --- Activation et configuration des logs ---
import logging

# --- Configuration des logs ---
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
app = logging.getLogger("sync_github")
app.setLevel(logging.DEBUG)



# Load configuration from config.yaml or config.example.yaml
config_path = "config.yaml" if os.path.exists("config.yaml") else "config.example.yaml"

with open(config_path, "r") as f:
    config = yaml.safe_load(f)

def github_list_organizations():
    github_conf = config.get("github", {})
    organizations = github_conf.get("organizations", [])
    org_list = []
    for org in organizations:
        org_list.append({"id": org, "name": org})
    return org_list

def github_list_projects(): return ["GitHub Project X", "GitHub Project Y"]

def github_get_data(projectId, github_token):
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
        print(json.dumps(data, indent=2)[:1000])  # print the first 1000 chars to avoid overload

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

            cleaned_name, pi_number, item_id = extract_feature_id_and_clean(title or "")
            id_feature = item_id

            features.append({
                "id_GitHub": node.get("id"),
                "Nom_Feature": cleaned_name or "(Sans titre)",
                "id_feature": id_feature,
                "pi_num": pi_number,
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
    
    
