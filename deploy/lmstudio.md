# Deploy con LM Studio (GUI, Windows/macOS/Linux)

1. Scarica LM Studio da https://lmstudio.ai e cerca **Qwen2.5-Coder-7B-Instruct** (GGUF Q4_K_M; su Mac
   puoi scegliere la versione MLX, più veloce su Apple Silicon). Scarica anche
   **Qwen2.5-Coder-1.5B-Instruct** e **nomic-embed-text-v1.5**.
2. Tab **Developer** → **Start Server** (porta 1234). Nelle impostazioni del modello: Context Length 16384,
   Flash Attention ON, e (se disponibile) *Speculative Decoding* con il modello 1.5B/0.5B come draft.
3. Copia gli **identificatori** dei modelli mostrati da LM Studio (es. `qwen2.5-coder-7b-instruct`).
4. Configura MyDevAgent (`.env`):
   ```bash
   LLM_BASE_URL=http://localhost:1234/v1
   LLM_API_KEY=lm-studio
   MYDEVAGENT_MODEL_MAIN=qwen2.5-coder-7b-instruct
   MYDEVAGENT_MODEL_REASONING=qwen2.5-coder-7b-instruct
   MYDEVAGENT_MODEL_FAST=qwen2.5-coder-1.5b-instruct
   MYDEVAGENT_MODEL_EMBED=text-embedding-nomic-embed-text-v1.5
   ```
   oppure in `settings.yaml`: `default_backend: lmstudio` e i nomi nel profilo.
5. `mydevagent doctor` → verifica che i modelli risultino presenti; poi `mydevagent chat`.

System prompt per l'uso diretto in LM Studio (senza orchestratore): copia il blocco `SYSTEM` di
`modelfiles/Modelfile.gpu8` nel campo *System Prompt*.
