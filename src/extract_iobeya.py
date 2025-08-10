# PSEUDO-CODE: Extract iObeya Features
# Usage: python extract_iobeya.py --config config.yaml --out data/features_raw.json

import argparse, json

def read_config(path):
    # TODO: read YAML from path
    return {"iobeya": {}, "run": {"output_dir": "data"}}

def iobeya_login(base_url, username=None, password=None, token=None):
    # Pseudo flow:
    # 1) GET {base}/json/config
    # 2) POST {base}/auth/login {user, pass} -> token (or use token directly)
    # 3) Return session headers
    return {"Authorization": "Bearer <TOKEN>"}

def fetch_board_elements(base_url, board_id, headers):
    # Pseudo request:
    # GET {base}/json/boards/{board_id}/elements
    # Return list of elements
    return [
        {
            "id": "FEAT-001",
            "type": "Feature",
            "title": "Améliorer la recherche",
            "description": "En tant que ... je souhaite ... afin de ...",
            "state": "Analyzing",
            "wsjf": 21,
            "pi": "PI-2025-03",
            "owner": "john.doe@example.com",
            "tags": ["search", "ux"],
            "updatedAt": "2025-08-01T10:11:12Z"
        }
    ]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()

    cfg = read_config(args.config)
    base = cfg["iobeya"].get("base_url")
    board_id = cfg["iobeya"].get("board_id")

    headers = iobeya_login(base, cfg["iobeya"].get("username"), cfg["iobeya"].get("password"), cfg["iobeya"].get("token"))
    items = fetch_board_elements(base, board_id, headers)

    features = [x for x in items if x.get("type") == "Feature"]
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(features, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
