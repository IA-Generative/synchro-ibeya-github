# PSEUDO-CODE: Load normalized features into GitHub Project v2
# Usage: python load_github.py --in data/features_normalized.json --config config.yaml

import argparse, json, time

def graphql(query, variables, token):
    # Pseudo call to https://api.github.com/graphql with Bearer token.
    # Return json response, handle errors/retries.
    return {"data": {}}

def ensure_fields(project_id, token, field_names):
    # Discover field IDs by name and return a dict {name: fieldId}.
    return {name: f"FIELD_ID_{i}" for i, name in enumerate(field_names)}

def upsert_item(project_id, token, item, fields):
    # 1) Lookup id_map for item['id']
    # 2) If not found -> addProjectV2DraftIssue(title, body)
    # 3) Then updateProjectV2ItemFieldValue for each field (state, wsjf, pi, owner, tags, last_sync_at)
    return "GITHUB_ITEM_ID"

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--config", required=True)
    args = p.parse_args()

    cfg = {
        "github": {"project_id": "PROJECT_V2_NODE_ID", "token_env_var": "GITHUB_TOKEN"},
        "mapping": {"fields": {
            "feature_key": "Feature Key", "state": "State", "wsjf": "WSJF",
            "pi": "PI", "owner": "Owner", "tags": "Tags", "last_sync_at": "Last Sync At"
        }}
    }

    token = "<ENV:GITHUB_TOKEN>"
    project_id = cfg["github"]["project_id"]
    field_names = list(cfg["mapping"]["fields"].values())
    field_ids = ensure_fields(project_id, token, field_names)

    data = json.load(open(args.inp, "r", encoding="utf-8"))
    for item in data:
        upsert_item(project_id, token, item, field_ids)
        time.sleep(0.1)  # minimise real-world rate-limits

if __name__ == "__main__":
    main()
