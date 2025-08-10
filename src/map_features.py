# PSEUDO-CODE: Map raw iObeya features -> normalized schema
# Usage: python map_features.py --in data/features_raw.json --out data/features_normalized.json --config config.yaml

import argparse, json

def load_mapping(cfg):
    return cfg.get("mapping", {})

def normalize(feature, mapping):
    state_map = mapping.get("states", {})
    return {
        "source": "iobeya",
        "id": feature["id"],
        "title": feature.get("title", ""),
        "body": feature.get("description", ""),
        "state": state_map.get(feature.get("state"), feature.get("state")),
        "wsjf": feature.get("wsjf"),
        "pi": feature.get("pi"),
        "owner": feature.get("owner"),
        "tags": feature.get("tags", []),
        "updatedAt": feature.get("updatedAt")
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--in", dest="inp", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--config", required=True)
    args = p.parse_args()

    # TODO: cfg = yaml.safe_load(open(args.config))
    cfg = {"mapping": {"states": {"Analyzing": "In Review"}}}
    mapping = load_mapping(cfg)

    data = json.load(open(args.inp, "r", encoding="utf-8"))
    normalized = [normalize(feat, mapping) for feat in data]

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(normalized, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
