# MyDevAgent

**Assistente di programmazione local-first con 15 agenti specializzati.** Gira tutto sul tuo PC
(GPU 8 GB+ o solo CPU), funziona offline e, quando sei online, fa ricerche web in tempo reale.
Lo usi da terminale, come server compatibile OpenAI (VS Code/Continue, Cursor, Aider, Cline…) o come
modello Ollama "single-agent".

> **Cos'è, in concreto.** Non è un LLM addestrato da zero (servirebbero milioni di euro di GPU).
> È un sistema completo costruito sopra i migliori modelli open-weight per il codice (Qwen2.5-Coder,
> Qwen3-Coder, …): una **persona di sistema**, **15 agenti di ruolo orchestrati con LangGraph**, **tool**
> reali (ricerca web, sandbox Docker, filesystem, git, RAG sulla tua codebase, visione), un **router** che
> tiene veloci le richieste semplici, e un **setup QLoRA** per addestrarlo sui tuoi progetti.
> La qualità dipende dal modello che scegli: un 7B locale non eguaglia i modelli cloud di frontiera,
> ma la pipeline (piano → implementazione → test eseguiti davvero → review) ne alza parecchio l'affidabilità.

```
richiesta ─▶ router ─┬─ fast      specialista giusto (1 chiamata, ~1–3 s) ───────────────────────────▶ risposta
                     └─ balanced/deep  [Research] ▶ Architect ▶ specialisti ∥ ▶ Debug&Test (sandbox)
                                       ▶ quality gate ∥ (Review, Security, Performance, Edge cases)
                                       ▶ revisione se serve ▶ [Docs] ▶ Formatter (streaming) ───────▶ risposta
```

## I 15 agenti

| # | Agente | # | Agente | # | Agente |
|---|---|---|---|---|---|
| 1 | Architetto del Codice | 6 | Backend & API | 11 | Research (web) |
| 2 | Algoritmi & Strutture Dati | 7 | Database & ORM | 12 | Code Reviewer & Refactor |
| 3 | Linguaggi & Framework | 8 | DevOps & CI/CD | 13 | Documentation |
| 4 | Debugging & Testing | 9 | Security | 14 | Edge Case & Robustness |
| 5 | Frontend | 10 | Performance | 15 | Output Formatter |

Ruoli, prompt, tool, flusso e interazioni: **[docs/AGENTS.md](docs/AGENTS.md)**.

---

## Installazione e avvio in 5 minuti

### Automatica
```bash
git clone <questo-repo> mydevagent && cd mydevagent
./scripts/install.sh gpu8          # cpu | gpu8 | gpu16 | gpu24     (Windows: scripts\install.ps1 -HwProfile gpu8)
source .venv/bin/activate
mydevagent
```

### Manuale
```bash
# 1. Ollama  →  https://ollama.com/download
ollama pull qwen2.5-coder:7b && ollama pull qwen2.5-coder:1.5b && ollama pull nomic-embed-text

# 2. MyDevAgent (Python 3.10+)
python3 -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[server,search]"
cp .env.example .env                                      # profilo, chiavi di ricerca (opzionali)

# 3. Verifica e usa
mydevagent doctor
mydevagent
```

### Quale profilo?
| Profilo | Hardware | Modello principale |
|---|---|---|
| `cpu` | solo CPU, 16 GB RAM | qwen2.5-coder:3b |
| `gpu8` | GPU 8 GB (RTX 3060/4060, M1/M2 16 GB) | qwen2.5-coder:7b |
| `gpu16` | GPU 12–16 GB | qwen2.5-coder:14b |
| `gpu24` | GPU 24 GB / Mac 32 GB+ | qwen3-coder:30b (MoE, velocissimo) |

Cambia profilo con `MYDEVAGENT_PROFILE=gpu16` in `.env` o `mydevagent -p gpu16`.

## Uso

```bash
mydevagent                                        # interfaccia interattiva stile Claude Code (vedi docs/TUI.md)
mydevagent --continue                             # riprende l'ultima sessione di questa cartella
mydevagent ask "Scrivi un LRU cache thread-safe in Go con test"
mydevagent ask "Perché crasha?" -f app/main.py -f error.log
mydevagent ask "/deep API FastAPI per upload su S3 con auth JWT, Postgres e Docker"
mydevagent ask "Rifai questa UI in React + Tailwind" -i mockup.png
mydevagent ask "Qual è l'ultima versione di Next.js e cosa cambia? @web"
cat diff.patch | mydevagent ask - -q               # da stdin, solo risposta
mydevagent route "..."                            # mostra modalità e agenti scelti (0 token)
mydevagent agents                                 # tabella dei 15 agenti
mydevagent index                                  # indicizza il progetto corrente per il RAG
mydevagent serve                                  # server OpenAI-compatibile su :8000
ollama run mydevagent                             # modello single-agent (dopo `ollama create`, vedi sotto)
```

Nell'interfaccia: `/` per i comandi, `@file` per allegare, `!comando` per la shell, `/apply` per salvare
i file generati (con diff e conferma), `Ctrl+C` per interrompere. Guida completa: [docs/TUI.md](docs/TUI.md).

Nel messaggio puoi guidare il team: `/fast`, `/balanced`, `/deep`, `@security`, `@perf`, `@web`, `@db`,
`@fe`, `@be`, `@devops`, `@review`, `@docs`…

## Online e offline
- **Offline**: tutto funziona; il Research Agent si disattiva da solo e il team segnala cosa andrebbe
  verificato (versioni, API recenti). Forzalo con `MYDEVAGENT_OFFLINE=1`.
- **Online**: ricerca con catena di fallback **Tavily → Firecrawl → SearXNG → DuckDuckGo**.
  Senza chiavi funziona con DuckDuckGo (`pip install ddgs`, incluso in `[search]`). Per la qualità
  migliore imposta `TAVILY_API_KEY` (piano gratuito) o avvia SearXNG self-hosted
  (`docker compose -f deploy/docker-compose.yml up -d searxng` + `SEARXNG_URL=http://localhost:8080`).
  Le pagine lette passano da un filtro anti-SSRF (niente accesso a localhost/IP privati).

## Tool e sicurezza
| Tool | Note |
|---|---|
| `run_code` | sandbox **Docker**: `--network none`, filesystem read-only, utente nobody, limiti CPU/RAM/PID, timeout. Senza Docker i test vengono saltati (il backend `local` richiede `allow_unsafe_local: true`) |
| `read_file` `list_dir` `grep` | confinati nella workspace, rifiutano `.env`/chiavi, bloccano path traversal e symlink |
| `write_file` `git_commit` | **disattivati** di default (`tools.filesystem.allow_write`, `tools.git.allow_commit`) |
| `git_status` `git_diff` `git_log` | sola lettura |
| `web_search` `web_fetch` | solo online, anti-SSRF |
| `rag_search` | indice locale in `.mydevagent/` (embeddings o fallback lessicale) |
| visione | tier `vision` (qwen2.5vl) per screenshot, mockup, errori in immagine |

Il server rispetta `MYDEVAGENT_API_KEY` (Bearer) — obbligatoria se lo esponi fuori da localhost.

## Deploy
| Backend | Guida |
|---|---|
| Ollama (consigliato) | [deploy/ollama.md](deploy/ollama.md) · modelli single-agent: `ollama create mydevagent -f modelfiles/Modelfile.gpu8` |
| LM Studio | [deploy/lmstudio.md](deploy/lmstudio.md) |
| llama.cpp (+ speculative decoding) | [deploy/llamacpp.sh](deploy/llamacpp.sh) |
| vLLM (+ prefix caching) | [deploy/vllm.sh](deploy/vllm.sh) |
| Docker Compose (Ollama + SearXNG + server) | [deploy/docker-compose.yml](deploy/docker-compose.yml) |
| Hugging Face | i modelli si scaricano da HF con llama.cpp (`-hf`) o vLLM; il fine-tuning parte da HF (Unsloth) |

Qualsiasi server compatibile OpenAI funziona: basta `LLM_BASE_URL` e i nomi dei modelli nel profilo.

## Integrazione negli IDE
- **VS Code + Continue.dev** (chat multi-agente, edit inline, autocomplete, @codebase):
  [integrations/vscode.md](integrations/vscode.md) + [integrations/continue/config.yaml](integrations/continue/config.yaml)
- **GitHub Copilot Chat** con modelli locali (Ollama): [integrations/vscode.md](integrations/vscode.md#2-github-copilot-chat-con-modelli-locali-byok)
- **Cursor**: [integrations/cursor.md](integrations/cursor.md)
- **Aider, Cline, Open WebUI, SDK OpenAI, uso come libreria**: [integrations/aider.md](integrations/aider.md)

## Personalizzazione, velocità, fine-tuning
- [docs/CUSTOMIZATION.md](docs/CUSTOMIZATION.md) — modelli, agenti, squadre, tool custom, RAG, QLoRA
- [docs/PERFORMANCE.md](docs/PERFORMANCE.md) — come renderlo più veloce e più efficiente con i token
- [finetune/README.md](finetune/README.md) — addestramento sui tuoi repository

## Struttura del progetto
```
config/settings.yaml      profili hardware, modalità, tool, server
config/agents.yaml        i 15 agenti (ruolo, tier, budget, sezioni lette, tool, keyword)
prompts/                  persona di sistema + 15 prompt di ruolo
mydevagent/               router · grafo LangGraph · orchestratore · client LLM · tool · CLI · server
mydevagent/tui/           interfaccia da terminale stile Claude Code
modelfiles/               Modelfile Ollama per profilo (persona integrata)
deploy/                   Ollama, LM Studio, llama.cpp, vLLM, Docker Compose, SearXNG
finetune/                 dataset dai tuoi repo, QLoRA con Unsloth, export GGUF → Ollama
integrations/             Continue.dev, VS Code/Copilot, Cursor, Aider/Cline
docs/                     agenti, performance, personalizzazione
tests/                    test con LLM finto (nessun modello richiesto): `pytest`
```

## Sviluppo
```bash
pip install -e ".[dev]"
pytest            # 59 test: registry, router, reasoning, tool/sandbox, pipeline, server
ruff check .
MYDEVAGENT_FAKE_LLM=1 mydevagent                 # prova l'interfaccia senza modello
```

Licenza MIT. I modelli hanno le loro licenze (Qwen: Apache-2.0 per la maggior parte delle taglie —
verifica sempre la model card).
