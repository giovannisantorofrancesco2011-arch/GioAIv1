# Velocità ed efficienza dei token

Obiettivo: **1–3 s** per le richieste semplici su 7B/14B in GPU, e pipeline multi-agente che costano il
meno possibile. Ecco cosa fa già MyDevAgent e cosa puoi regolare.

## Cosa è già attivo

| Tecnica | Dove | Effetto |
|---|---|---|
| Router euristico (0 token, <1 ms) | `router.py` | la maggior parte delle domande va in **fast = 1 sola chiamata LLM** |
| Formatter fuso in fast | `graph.py → system_prompt(fused_delivery=True)` | niente seconda chiamata per "riformattare" |
| Blackboard con `reads` per agente | `state.py`, `agents.yaml` | ogni agente riceve solo le sezioni utili (−50/80% token di input) |
| Prefisso stabile (persona → ruolo) | `Team.system_prompt` | la KV/prefix cache del server riusa la persona tra agenti e richieste |
| `max_tokens` per agente | `agents.yaml` | i quality gate rispondono in ~100–300 token |
| Specialisti e gate in parallelo | `Send` di LangGraph | latenza ≈ agente più lento, non la somma |
| `<think>` rimosso dalla blackboard | `reasoning.strip_thinking` | il ragionamento non viene rimandato agli altri agenti |
| Thinking solo in deep e solo per tier `reasoning` | `modes.*.think` | `/no_think` (Qwen3) o `Reasoning: low` (gpt-oss) nelle altre modalità |
| Ricerca in fast senza LLM | `orchestrator.run` | risultati iniettati direttamente nel contesto |
| Codice incollato non gonfia la modalità | `router.prose_length` | un traceback lungo resta in fast |
| Streaming end-to-end | CLI + server SSE | primo token visibile subito |

### Modalità agente
| Tecnica | Effetto |
|---|---|
| **Warmup** all'apertura della UI (richiesta da 1 token in background) | la prima domanda non paga 5–20 s di caricamento del modello |
| System prompt fisso per tutto il turno (persona → ruolo → memoria → repo map → regole → tool) | ogni passo del ciclo riusa la prefix cache del server |
| Output dei tool troncato in mezzo (prime/ultime righe) e `read_file` a finestre | contesto piccolo anche su file e log lunghi |
| Risultati dei tool più vecchi svuotati quando il contesto supera `num_ctx × 3` caratteri | niente overflow di contesto nei task lunghi |
| Prompt di ruolo compatto in modalità agente | meno token e meno confusione per i modelli piccoli |
| Messaggio "tests pass → fermati" dopo test verdi | i modelli piccoli non fanno giri inutili |

## Misurare: `mydevagent bench`
```bash
mydevagent bench                     # primo token e token/s di main e fast, con consiglio sul profilo
mydevagent bench --tiers main,reasoning
```
Esempio misurato nel container di sviluppo (solo CPU, nessuna GPU): `qwen2.5-coder:1.5b` → primo token
0,5 s, ~14 token/s; `qwen2.5-coder:0.5b` → ~29 token/s. Su una GPU da 8 GB un 7B Q4 fa tipicamente
40–80 token/s. Con la sola CPU la modalità agente funziona ma ogni passo richiede decine di secondi:
usa `/fast`, un modello 3B o una GPU.

## Server: le impostazioni che contano di più

### Ollama
```bash
export OLLAMA_FLASH_ATTENTION=1        # meno memoria e più velocità su contesti lunghi
export OLLAMA_KV_CACHE_TYPE=q8_0       # KV cache a 8 bit: metà VRAM, qualità ~identica
export OLLAMA_KEEP_ALIVE=30m           # il modello resta caricato (niente 5–20 s di reload)
export OLLAMA_NUM_PARALLEL=3           # agenti in parallelo sullo stesso modello
export OLLAMA_CONTEXT_LENGTH=16384     # contesto di default per i modelli non creati da Modelfile
export OLLAMA_MAX_LOADED_MODELS=2      # main + fast insieme se la VRAM lo consente
```
(Windows: impostale come variabili d'ambiente utente e riavvia Ollama.)

### llama.cpp (il più efficiente su GPU piccole e Apple Silicon) — [`deploy/llamacpp.sh`](../deploy/llamacpp.sh)
- `--cache-reuse 256` → riuso del prefisso tra richieste
- `-hfd <draft 0.5B>` → **speculative decoding**: 1.5–2.5× sul codice (molto prevedibile)
- `-ctk q8_0 -ctv q8_0`, `--flash-attn on`, `-np 3`

### vLLM (massimo throughput con tanti agenti in parallelo) — [`deploy/vllm.sh`](../deploy/vllm.sh)
- `--enable-prefix-caching`, `--speculative-config` con draft 0.5B, modelli AWQ/FP8

## Scelte di modello

| Hardware | Consiglio | Perché |
|---|---|---|
| CPU / 8 GB RAM | `qwen2.5-coder:3b` (main) | ~10–20 tok/s su CPU moderna |
| GPU 8 GB | `qwen2.5-coder:7b` Q4_K_M | ~40–80 tok/s, entra con 16k di contesto |
| GPU 12–16 GB | `qwen2.5-coder:14b` | salto di qualità netto, ancora veloce |
| GPU 24 GB | `qwen3-coder:30b` (MoE, ~3B attivi) | qualità da 30B a velocità da ~3B |
| Apple Silicon 32 GB+ | `qwen3-coder:30b` con llama.cpp/MLX | la memoria unificata regge il MoE intero |

Regole pratiche:
- **Stesso modello per `main` e `reasoning`** se non ti basta la VRAM per due: gli swap costano secondi.
- Quantizzazione: Q4_K_M è il miglior compromesso; Q5_K_M/Q6_K se hai margine; evita < Q4 per il codice.
- Autocomplete: sempre un modello **base** piccolo (`qwen2.5-coder:1.5b-base`), mai il team.
- I nomi dei modelli evolvono in fretta: quando esce un coder open-weight migliore basta cambiare
  il tag in `config/settings.yaml` (o `MYDEVAGENT_MODEL_MAIN=...`).

## Regolazioni in `config/settings.yaml`

| Voglio… | Modifica |
|---|---|
| più risposte in fast | `router.fast_max_chars: 600` |
| sempre veloce | `router.default_mode: fast` |
| meno giri di revisione | `modes.balanced.max_review_rounds: 0` |
| meno gate in deep | `modes.deep.gate: [security, reviewer]` |
| contesti più corti | `context.max_section_chars: 3000`, `context.history_turns: 2` |
| meno output per agente | abbassa `max_tokens` in `agents.yaml` |
| nessuna lettura di pagine web | `tools.web.fetch_top_n: 0` |

## Misurare
Ogni risposta termina (CLI) con `modalità · N agenti · secondi · ~token`; gli eventi `agent_end`
riportano ms e token per agente. Prova la stessa richiesta con `/fast` e `/deep` per vedere il costo
di ogni fase.
