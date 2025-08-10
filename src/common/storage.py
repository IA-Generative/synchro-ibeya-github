# PSEUDO key-value idempotent storage (JSON file)

import json, os

class IdStore:
    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._data = {}
        if os.path.exists(path):
            try:
                self._data = json.load(open(path, "r", encoding="utf-8"))
            except Exception:
                self._data = {}

    def get(self, key):
        return self._data.get(key)

    def set(self, key, value):
        self._data[key] = value
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
