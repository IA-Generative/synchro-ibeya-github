#!/usr/bin/env python3
import argparse
import os
import sys
import time
import requests

#python3 delete_issues.py --repo IA-Generative/default_repository --dry-run
#python3 delete_issues.py --repo IA-Generative/default_repository --yes
#export GITHUB_TOKEN="ghp_..."   # token avec droits suffisants sur le repo


REST_API = "https://api.github.com"
GQL_API = "https://api.github.com/graphql"

def gh_headers(token: str):
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

def list_issues(owner: str, repo: str, token: str, state: str = "all", per_page: int = 100):
    """
    Liste les issues (et PRs) via REST.
    On filtrera ensuite pour exclure les PRs.
    """
    url = f"{REST_API}/repos/{owner}/{repo}/issues"
    page = 1
    while True:
        r = requests.get(
            url,
            headers=gh_headers(token),
            params={"state": state, "per_page": per_page, "page": page},
            timeout=30,
        )
        r.raise_for_status()
        items = r.json()
        if not items:
            break
        for it in items:
            yield it
        page += 1

def delete_issue_gql(issue_node_id: str, token: str):
    """
    Supprime une issue via GraphQL deleteIssue.
    """
    query = """
    mutation($issueId: ID!) {
      deleteIssue(input: { issueId: $issueId }) {
        clientMutationId
      }
    }
    """
    payload = {"query": query, "variables": {"issueId": issue_node_id}}
    r = requests.post(GQL_API, headers=gh_headers(token), json=payload, timeout=30)
    r.raise_for_status()
    data = r.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data

def main():
    ap = argparse.ArgumentParser(description="Delete all issues in a GitHub repo (GraphQL deleteIssue).")
    ap.add_argument("--repo", default="IA-Generative/default_repository", help="owner/repo")
    ap.add_argument("--state", default="all", choices=["open", "closed", "all"])
    ap.add_argument("--include-closed", action="store_true", help="Alias: include closed issues too (same as --state all)")
    ap.add_argument("--dry-run", action="store_true", help="Ne supprime rien, affiche seulement ce qui serait supprimé")
    ap.add_argument("--yes", action="store_true", help="Ne demande pas de confirmation interactive")
    ap.add_argument("--sleep", type=float, default=0.2, help="Pause entre suppressions (anti rate-limit)")
    args = ap.parse_args()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("❌ Variable d'environnement GITHUB_TOKEN manquante.", file=sys.stderr)
        sys.exit(2)

    owner, repo = args.repo.split("/", 1)
    state = "all" if args.include_closed else args.state

    # Collecte issues (en excluant les PRs)
    issues = []
    for it in list_issues(owner, repo, token, state=state):
        if "pull_request" in it:
            continue  # exclut PRs
        node_id = it.get("node_id")
        number = it.get("number")
        title = (it.get("title") or "").strip()
        if node_id and number:
            issues.append({"node_id": node_id, "number": number, "title": title})

    if not issues:
        print("✅ Aucune issue à supprimer.")
        return

    print(f"🔎 Repo: {owner}/{repo}")
    print(f"📌 Issues trouvées: {len(issues)} (state={state})")
    for it in issues[:10]:
        print(f" - #{it['number']} {it['title']}")
    if len(issues) > 10:
        print(f" ... +{len(issues) - 10} autres")

    if args.dry_run:
        print("🧪 DRY RUN: aucune suppression effectuée.")
        return

    if not args.yes:
        resp = input(f"\n⚠️ Confirmer la suppression de {len(issues)} issues ? taper 'DELETE' : ")
        if resp.strip() != "DELETE":
            print("❌ Annulé.")
            return

    deleted = 0
    for it in issues:
        try:
            delete_issue_gql(it["node_id"], token)
            deleted += 1
            print(f"🗑️ Deleted #{it['number']} {it['title']}")
        except Exception as e:
            print(f"❌ Failed #{it['number']} : {e}", file=sys.stderr)
        time.sleep(args.sleep)

    print(f"✅ Terminé. Supprimées: {deleted}/{len(issues)}")

if __name__ == "__main__":
    main()