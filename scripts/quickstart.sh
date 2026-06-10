#!/usr/bin/env bash
# Distill quickstart — one command to a running agent on this machine.
#
#   ./scripts/quickstart.sh
#
# Generates strong secrets, ensures an env file exists, and brings the stack
# up with Docker Compose. Re-running is safe: existing secrets are preserved.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required but was not found. Install Docker, then re-run." >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose v2 is required (try: docker compose version)." >&2
  exit 1
fi

gen_secret() { openssl rand -hex "${1:-24}" 2>/dev/null || head -c "${1:-24}" /dev/urandom | od -An -tx1 | tr -d ' \n'; }

# Compose reads interpolation variables (NEO4J_PASSWORD) from .env; the agent
# reads its config from an-api.env. Keep both, generate secrets once.
ENV_FILE="an-api.env"
if [[ ! -f "$ENV_FILE" ]]; then
  cp an-api.env.example "$ENV_FILE"
  echo "Created $ENV_FILE from the template — add your LLM API key there."
fi

add_secret() {  # add_secret VAR FILE [length]
  local var="$1" file="$2" len="${3:-24}"
  touch "$file"
  if ! grep -q "^${var}=" "$file"; then
    printf '%s=%s\n' "$var" "$(gen_secret "$len")" >> "$file"
    chmod 600 "$file" 2>/dev/null || true
    echo "Generated $var in $file"
  fi
}

add_secret NEO4J_PASSWORD .env 24
add_secret AGENT_API_TOKEN "$ENV_FILE" 32

echo "Building and starting the stack…"
docker compose up -d --build

TOKEN="$(grep '^AGENT_API_TOKEN=' "$ENV_FILE" | head -1 | cut -d= -f2-)"
cat <<EOF

Distill is starting up.

  Control Panel : http://localhost:5173
  API / Docs    : http://localhost:8000/docs
  API token     : ${TOKEN}

Next: put your LLM API key in ${ENV_FILE} (e.g. OPENAI_API_KEY or MOONSHOT_API_KEY),
then re-run this script. To text your agent, add TELEGRAM_BOT_TOKEN too.
EOF
