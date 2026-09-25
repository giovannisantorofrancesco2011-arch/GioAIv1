# Fine-tuning QLoRA di MyDevAgent sui tuoi progetti

| File | Cosa fa |
|---|---|
| `build_dataset.py` | dai tuoi repo git → `data/train.jsonl`, `data/val.jsonl`, `data/fim.jsonl` |
| `config_qlora.yaml` | modello base, LoRA (r=16), iperparametri, export |
| `train_qlora.py` | training QLoRA 4-bit con Unsloth + TRL |
| `export_gguf.sh` | merge + quantizzazione GGUF + `ollama create mydevagent-custom` |

## Requisiti
- GPU NVIDIA con 8 GB+ (1.5B/3B), ~10 GB (7B), ~16 GB (14B). Linux o WSL2.
- Senza GPU: carica la cartella su Google Colab/Kaggle (T4 16 GB gratuita) ed esegui gli stessi comandi.
- `pip install -e ".[finetune]"` (installa unsloth, trl, datasets, peft, transformers).

## Passi
```bash
# 1. Dataset (commit piccoli e ben descritti funzionano meglio)
python finetune/build_dataset.py ~/code/app ~/code/lib --max-commits 3000 --fim-per-repo 300

# (opzionale) tue coppie domanda/risposta, una per riga:
#   {"prompt": "Come gestiamo gli errori nei servizi?", "response": "Usiamo Result<T, AppError> ..."}
python finetune/build_dataset.py ~/code/app --extra finetune/my_qa.jsonl

# 2. Training
python finetune/train_qlora.py --config finetune/config_qlora.yaml

# 3. Export in Ollama
bash finetune/export_gguf.sh

# 4. Uso nel team a 15 agenti
MYDEVAGENT_MODEL_MAIN=mydevagent-custom mydevagent chat
```

## Consigli
- **Qualità > quantità**: elimina commit rumorosi (format, bump, merge). Il builder filtra già quelli
  ovvi e i file generati.
- **Epoche**: 1–2. Più epoche = overfitting sul tuo codice e perdita di capacità generali.
- **Valuta** confrontando `mydevagent-custom` e il modello base sugli stessi 10–20 task reali.
- **FIM**: gli esempi fill-in-the-middle migliorano l'autocomplete; se addestri solo per la chat
  imposta `fim_ratio: 0`. Per un autocomplete personalizzato addestra un modello *base*
  (`unsloth/Qwen2.5-Coder-1.5B`) solo sul file FIM e usalo in Continue come modello `autocomplete`.
- **Privacy**: tutto resta sul tuo PC. Controlla comunque `data/*.jsonl` prima di usare Colab.
