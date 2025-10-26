#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CERTS_DIR="${SCRIPT_DIR}/../certs"
DOMAIN="${1:-localhost}"
MODE="${2:-auto}"

if [ ! -d "$CERTS_DIR" ]; then
  echo "📁 Le répertoire certs n'existe pas, création en cours..."
  mkdir -p "$CERTS_DIR"
fi

echo "🔐 [CERTS] Dossier cible : $CERTS_DIR"
echo "🔧 Domaine : $DOMAIN"
echo "🔧 Mode : $MODE"

# --- Fonction : Vérifie si une commande existe ---
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# --- Option 1 : Développement local avec mkcert ---
generate_local() {
  echo "🧱 Génération locale du certificat avec mkcert..."

  if ! command_exists mkcert; then
    echo "⚠️ mkcert non trouvé. Installation recommandée via Homebrew :"
    echo "   brew install mkcert && brew install nss"
    echo "⏳ Utilisation de OpenSSL en remplacement temporaire..."
    openssl req -x509 -newkey rsa:4096 -nodes       -keyout "$CERTS_DIR/privkey.pem"       -out "$CERTS_DIR/fullchain.pem"       -days 3650       -subj "/CN=$DOMAIN"       -addext "subjectAltName=DNS:$DOMAIN,IP:127.0.0.1"
    return
  fi

  cd "$CERTS_DIR"
  mkcert -install
  mkcert "$DOMAIN" 127.0.0.1 ::1

  mv "$DOMAIN+2.pem" fullchain.pem 2>/dev/null || true
  mv "$DOMAIN+2-key.pem" privkey.pem 2>/dev/null || true
  echo "✅ Certificats générés avec mkcert dans $CERTS_DIR"
}

# --- Option 2 : Production avec Let's Encrypt ---
generate_prod() {
  echo "☁️ Génération du certificat Let's Encrypt pour le domaine $DOMAIN"

  if ! command_exists certbot; then
    echo "⚠️ certbot non trouvé. Installation :"
    echo "   sudo apt install -y certbot || brew install certbot"
    exit 1
  fi

  sudo certbot certonly --standalone -d "$DOMAIN" --agree-tos -n -m admin@"$DOMAIN"

  # Copie dans le dossier certs/
  sudo cp /etc/letsencrypt/live/"$DOMAIN"/fullchain.pem "$CERTS_DIR"/
  sudo cp /etc/letsencrypt/live/"$DOMAIN"/privkey.pem "$CERTS_DIR"/

  echo "✅ Certificats copiés dans $CERTS_DIR"
}

# --- Détection du mode ---
if [[ "$MODE" == "local" ]]; then
  generate_local
elif [[ "$MODE" == "prod" ]]; then
  generate_prod
else
  # Mode auto : macOS => mkcert, Linux => certbot
  if [[ "$OSTYPE" == "darwin"* ]]; then
    generate_local
  else
    generate_prod
  fi
fi

echo "🎉 Terminé !"
ls -lh "$CERTS_DIR"
