#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )"/.. && pwd )"
cd "$ROOT_DIR"

mkdir -p data

echo "[1/3] Extract from iObeya"
python3 src/extract_iobeya.py --config config.yaml --out data/features_raw.json

echo "[2/3] Map to normalized schema"
python3 src/map_features.py --in data/features_raw.json --out data/features_normalized.json --config config.yaml

echo "[3/3] Load into GitHub Project"
python3 src/load_github.py --in data/features_normalized.json --config config.yaml
