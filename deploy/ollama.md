# Deploy con Ollama (consigliato per iniziare)

```bash
# 1. installa: https://ollama.com/download  (Linux: curl -fsSL https://ollama.com/install.sh | sh)
# 2. modelli per il profilo gpu8 (cambia i tag per gli altri profili, vedi config/settings.yaml)
ollama pull qwen2.5-coder:7b
ollama pull qwen2.5-coder:1.5b
ollama pull nomic-embed-text
ollama pull qwen2.5-coder:1.5b-base      # autocomplete per Continue (opzionale)
ollama pull qwen2.5vl:7b                 # screenshot/mockup (opzionale)
# 3. modello "single-agent" con la persona MyDevAgent integrata
ollama create mydevagent -f modelfiles/Modelfile.gpu8
ollama run mydevagent
```

Variabili consigliate (vedi `docs/PERFORMANCE.md`): `OLLAMA_FLASH_ATTENTION=1`,
`OLLAMA_KV_CACHE_TYPE=q8_0`, `OLLAMA_KEEP_ALIVE=30m`, `OLLAMA_NUM_PARALLEL=3`,
`OLLAMA_CONTEXT_LENGTH=16384`.

Il team a 15 agenti usa Ollama tramite l'endpoint OpenAI-compatibile `http://localhost:11434/v1`
(default in `settings.yaml`). Tutto in Docker: `docker compose -f deploy/docker-compose.yml up -d`.
