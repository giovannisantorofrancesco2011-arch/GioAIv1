#!/usr/bin/env bash
# MyDevAgent — avvio con un comando (Linux/macOS), senza attivare l'ambiente virtuale.
# Uso, dalla cartella del tuo progetto:   /percorso/di/mydevagent/run.sh   [opzioni di mydevagent]
# Se dice "permission denied":            bash /percorso/di/mydevagent/run.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN="$HERE/.venv/bin/mydevagent"
if [[ ! -x "$BIN" ]]; then
  echo "MyDevAgent non è ancora installato: avvio l'installazione (una volta sola)."
  bash "$HERE/scripts/install.sh"
fi
exec "$BIN" "$@"
