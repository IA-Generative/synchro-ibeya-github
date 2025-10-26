# Synchro iObeya ↔ GitHub — Packaging (Docker Compose + Helm)

This package contains ready-to-use artifacts to run the app with **Docker Compose** or **Kubernetes (Helm chart)**.

## Repository assumptions
- Your repo contains the Flask app at `webapp/app.py` exposing `app` (i.e. `webapp.app:app`).
- A `config.yaml` is available at repo root (or `config.example.yaml`).

---

## 1) Docker Compose

### Build & run
```bash
# (optional) export env vars for secrets
export ACCESS_KEY="your_access_key_here"
export GITHUB_TOKEN="ghp_..."
export IOBEYA_TOKEN="..."

# ensure you have a config.yaml next to docker-compose.yml
docker compose up --build -d
# then open http://localhost:28080/?key=<ACCESS_KEY>
```

### Files
- `Dockerfile` – production-ready image with Gunicorn
- `.dockerignore` – excludes dev files
- `requirements.txt` – Python deps
- `docker-compose.yml` – one-service stack

---

## 2) Kubernetes (Helm)

The chart will deploy:
- A `Deployment` with a container running the Flask app via Gunicorn
- A `Service` (ClusterIP)
- An optional `Ingress`
- A `ConfigMap` for `config.yaml`
- A `Secret` for tokens/keys

### Quickstart
```bash
# Package image & push to your registry first
docker build -t REGISTRY/PROJECT/synchro-iobeya-github:1.0.0 .
docker push REGISTRY/PROJECT/synchro-iobeya-github:1.0.0

# Install / upgrade the Helm release
helm upgrade --install synchro-iobeya-github ./helm/synchro-iobeya-github \
  --namespace synchro --create-namespace \
  --set image.repository=REGISTRY/PROJECT/synchro-iobeya-github \
  --set image.tag=1.0.0 \
  --set secret.env.ACCESS_KEY="replace_me" \
  --set secret.env.GITHUB_TOKEN="ghp_..." \
  --set secret.env.IOBEYA_TOKEN="..." \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=your.host.name \
  --set ingress.hosts[0].paths[0].path=/ \
  --set ingress.hosts[0].paths[0].pathType=Prefix
```

### Supplying config.yaml
- By default, the chart creates a `ConfigMap` from `.Values.config` and mounts it to `/app/config.yaml`.
- You can either **inline your config** in `values.yaml` (`config:` block) or use `--set-file config=./config.yaml` to inject an existing file.

### IMPORTANT — First access
- Browse the app with `?key=<ACCESS_KEY>` once (e.g. `https://host/?key=replace_me`).
- The app stores the key as an HTTP-only cookie for subsequent requests.

---

## 3) Values you likely want to change
- `image.repository` & `image.tag`
- `ingress.hosts`
- `secret.env.ACCESS_KEY`, `secret.env.GITHUB_TOKEN`, `secret.env.IOBEYA_TOKEN`
- `config` (inline your config.yaml content)

---

## 4) Uninstall
```bash
helm uninstall synchro-iobeya-github -n synchro
```
