# Personalizzazione

Tutto è configurazione + prompt in chiaro: nessun codice da toccare per il 90% delle modifiche.

## 1. Modelli e profili
`config/settings.yaml → profiles`. Ogni tier (`main`, `fast`, `reasoning`, `vision`, `embed`) accetta un
tag o `{model, backend}` per mischiare server:

```yaml
profiles:
  mio-pc:
    main: { model: "qwen3-coder:30b", backend: vllm }      # codice su vLLM
    fast: "qwen2.5-coder:1.5b"                              # router/query su Ollama
    reasoning: "qwen3:14b"                                  # thinking solo in deep
    embed: "nomic-embed-text"
    num_ctx: 32768
    native_tools: true
```
Poi `MYDEVAGENT_PROFILE=mio-pc` (o `profile: mio-pc`). Override veloce senza file:
`MYDEVAGENT_MODEL_MAIN=mydevagent-custom mydevagent chat`.

## 2. Modificare un agente
- **Comportamento**: modifica `prompts/agents/NN_nome.md` (inglese = resa migliore dei modelli coder).
- **Budget**: `max_tokens`, `temperature`, `tier` in `config/agents.yaml`.
- **Cosa vede**: `reads` (meno sezioni = più veloce).
- **Quando si attiva**: `keywords` (IT/EN) e `aliases` (`@nome`).
- **Regole globali**: `prompts/system_persona.md` (vale per tutti; tienila corta: è nel prefisso di ogni
  chiamata).

## 2b. Memoria del progetto, comandi personalizzati, permessi
- **`MYDEVAGENT.md`** nella radice: comandi (`- test: pytest -q`), architettura, convenzioni. L'agente lo
  legge a ogni richiesta; `/init` lo genera, `#nota` aggiunge righe. Letti anche `AGENTS.md`, `CLAUDE.md` e
  `~/.mydevagent/MYDEVAGENT.md` (preferenze personali per tutti i progetti).
- **Comandi personalizzati**: `.mydevagent/commands/<nome>.md` → `/nome` (vedi `docs/TUI.md`).
- **Permessi**: `mydevagent --permissions auto-edit`; regole «consenti sempre» in
  `.mydevagent/settings.json`, ad esempio:
  ```json
  { "allow": ["bash:pytest*", "bash:npm test*", "bash:ruff*", "edit:src/*"] }
  ```

## 3. Raggruppamenti (squadre) e modalità
Le modalità sono gruppi di agenti già pronti. Crea le tue combinazioni in `settings.yaml`:

```yaml
modes:
  balanced:
    gate: [reviewer, security]      # ogni task passa anche dalla security
    max_review_rounds: 1
  deep:
    gate: [security, performance, edge_cases, reviewer]
    max_review_rounds: 3
    think: true
    docs: true
```
Squadre "al volo" direttamente nel messaggio: `@be @db @sec crea l'endpoint di pagamento`.

## 4. Sostituire un agente con un altro ruolo
Il sistema richiede **esattamente 15 agenti nel nucleo** (`agents.yaml`) e **20 estesi** per `/ultra-deep`
(`agents_ultra.yaml`, id 16-35), validati all'avvio. Per cambiare un ruolo, ad esempio
trasformare *DevOps* in *Mobile (iOS/Android)*:
1. in `agents.yaml` cambia `key`, `name`, `role`, `goal`, `keywords`, `aliases`, `prompt` dell'agente 8;
2. crea `prompts/agents/08_mobile.md` partendo da un prompt specialist esistente;
3. `stage: specialist` → entra automaticamente nel fan-out parallelo.

Stage disponibili: `research`, `plan`, `specialist` (fan-out), `test`, `gate` (quality gate con VERDICT),
`docs`, `final`. Per più di 15 agenti: `load_registry(settings, strict=False)` nel tuo codice.

## 5. Tool personalizzati
Crea un modulo Python (es. `my_tools/jira.py`) e registralo:

```python
# my_tools/jira.py
import os, httpx
from mydevagent.tools import tool

@tool("jira_issue", "Read a Jira issue (summary, description, status).",
      {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]})
def jira_issue(ctx, key: str) -> str:
    r = httpx.get(f"{os.environ['JIRA_URL']}/rest/api/3/issue/{key}",
                  auth=(os.environ["JIRA_USER"], os.environ["JIRA_TOKEN"]), timeout=10)
    r.raise_for_status()
    f = r.json()["fields"]
    return f"{key}: {f['summary']} [{f['status']['name']}]\n{f.get('description')}"
```

```yaml
# settings.yaml
tools:
  custom: ["my_tools.jira"]
```
```yaml
# agents.yaml → l'agente che deve usarlo
    tools: [rag_search, read_file, jira_issue]
```
I tool nativi vengono chiamati dal modello (function calling) quando il profilo ha `native_tools: true`
(consigliato da 14B in su; i 7B sono meno affidabili nel function calling). Il contesto `ctx` offre
`ctx.settings`, `ctx.workspace`, `ctx.web`, `ctx.sandbox`, `ctx.index`, `ctx.llm`.
I tool restituiscono sempre stringhe; errori ed eccezioni vengono convertiti in `ERROR: …` senza
interrompere il team.

Tool inclusi: `web_search`, `web_fetch`, `read_file`, `list_dir`, `grep`, `write_file` (disattivato di
default), `git_status`, `git_diff`, `git_log`, `git_commit` (disattivato di default), `run_code`, `rag_search`.

## 6. Conoscenza dei tuoi progetti senza training: RAG
```bash
cd ~/code/mio-progetto
mydevagent index            # embeddings con nomic-embed-text (fallback lessicale automatico)
mydevagent chat             # gli agenti ricevono i pezzi di codice rilevanti
```
Rilancia `mydevagent index` dopo grandi modifiche. È il modo più economico ed efficace per far
"conoscere" il tuo codice al modello — prova questo **prima** del fine-tuning.

## 7. Fine-tuning leggero (QLoRA) sul tuo stile
Utile quando vuoi che il modello scriva *come te* (convenzioni, librerie interne, pattern ricorrenti).

```bash
pip install -e ".[finetune]"                                   # GPU NVIDIA (Linux/WSL2) o Colab
python finetune/build_dataset.py ~/code/progetto1 ~/code/progetto2 --extra finetune/my_qa.jsonl
python finetune/train_qlora.py --config finetune/config_qlora.yaml
bash finetune/export_gguf.sh                                    # → ollama model "mydevagent-custom"
MYDEVAGENT_MODEL_MAIN=mydevagent-custom mydevagent chat
```
- Dataset: coppie *prima/dopo* dai tuoi commit (messaggio del commit = istruzione), esempi FIM per
  l'autocomplete e le tue coppie domanda/risposta. File con segreti scartati automaticamente.
- 7B QLoRA: ~10 GB VRAM, 1–3 ore per qualche migliaio di esempi su una RTX 3060/4070.
- Parti con 500–3000 esempi di qualità e 1–2 epoche; valuta sempre su `val.jsonl` e su task reali:
  un fine-tuning cattivo peggiora il ragionamento generale.
- Dettagli in [`finetune/README.md`](../finetune/README.md).

## 8. Lingua
Prompt degli agenti in inglese, risposta nella lingua dell'utente (regola nella persona). Per forzare
l'italiano sempre: aggiungi a `system_persona.md` → `Always reply in Italian.`
