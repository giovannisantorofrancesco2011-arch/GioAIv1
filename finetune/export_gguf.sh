#!/usr/bin/env bash
# Esporta il modello fine-tuned in GGUF (se non già fatto) e lo registra in Ollama come "mydevagent-custom".
#   bash finetune/export_gguf.sh [config]
set -euo pipefail
CONFIG="${1:-finetune/config_qlora.yaml}"
read -r GGUF_DIR QUANT NAME OUT < <(python3 - "$CONFIG" <<'PY'
import sys, yaml
c = yaml.safe_load(open(sys.argv[1]))
print(c["export"]["gguf_dir"], c["export"]["quantization"], c["export"]["ollama_name"], c["train"]["output_dir"])
PY
)

if ! ls "$GGUF_DIR"/*.gguf >/dev/null 2>&1; then
  echo "==> merge LoRA + quantizzazione $QUANT con Unsloth"
  python3 - "$OUT/adapter" "$GGUF_DIR" "$QUANT" <<'PY'
import sys
from unsloth import FastLanguageModel
model, tok = FastLanguageModel.from_pretrained(sys.argv[1], load_in_4bit=True)
model.save_pretrained_gguf(sys.argv[2], tok, quantization_method=sys.argv[3])
PY
fi

GGUF="$(ls -S "$GGUF_DIR"/*.gguf | grep -i "$QUANT" | head -1 || ls -S "$GGUF_DIR"/*.gguf | head -1)"
echo "==> GGUF: $GGUF"
SYSTEM="$(sed -n '/^SYSTEM """/,/"""$/p' modelfiles/Modelfile.gpu8)"
cat > "$GGUF_DIR/Modelfile" <<MF
FROM $(realpath "$GGUF")
PARAMETER num_ctx 16384
PARAMETER temperature 0.2
PARAMETER top_p 0.9
$SYSTEM
MF
ollama create "$NAME" -f "$GGUF_DIR/Modelfile"
cat <<MSG
Fatto! Prova:   ollama run $NAME
Per usarlo nel team a 15 agenti:   MYDEVAGENT_MODEL_MAIN=$NAME mydevagent chat
(oppure imposta  main: "$NAME"  nel profilo in config/settings.yaml)
MSG
