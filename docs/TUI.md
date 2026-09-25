# Interfaccia da terminale (stile Claude Code)

```bash
mydevagent                               # apre l'interfaccia nella cartella del progetto
mydevagent -p gpu16                      # con un altro profilo
mydevagent --continue                    # riprende l'ultima sessione di questa cartella
mydevagent --permissions auto-edit       # modifiche automatiche, comandi con conferma
mydevagent chat --plain                  # vecchia chat semplice (pipe, terminali limitati)
```

```
> aggiungi sub(a, b) in calc.py e un test
⏺ fast · agente · Linguaggi & Framework
⏺ Read(calc.py)
  ⎿  calc.py (2 lines)
⏺ Update(calc.py)
@@ -1,2 +1,5 @@
 def add(a, b):
     return a + b
+
+def sub(a, b):
+    return a - b
Applicare la modifica a calc.py?  1 Sì  2 Sì, e non chiedere più  3 No
  › 1
⏺ Test(python -m pytest -q)
  ⎿  ✓ test passati
Ho aggiunto sub in calc.py e il test test_sub; 2 test passati.
---
📝 File modificati: calc.py, test_calc.py  (/undo per annullare)
✅ Test: passati (python -m pytest -q)

 agente ⏵ ask (shift+tab) · qwen2.5-coder:7b · modo auto · ● online · ~3.2k tok ·  main
```

## Modalità agente (default) e modalità chat
- **agente** (`/agent`): il team lavora **direttamente sui file** della cartella in cui hai aperto
  MyDevAgent, con dei tool: `read_file`, `list_files`, `grep`, `edit_file` (sostituzione esatta di un
  pezzo di testo), `write_file`, `bash`, `run_tests`, `todo_write`, `web_search`.
- **chat** (`/chat`): risponde con il codice senza toccare i file; `/apply` lo salva dopo il diff.

## Permessi (come Claude Code) — `Shift+Tab` per cambiarli
| Modalità | Letture | Modifiche ai file | Comandi |
|---|---|---|---|
| `ask` (default) | ✓ | chiede conferma con il diff | chiede conferma (i comandi di sola lettura no) |
| `auto-edit` | ✓ | automatiche | chiede conferma |
| `plan` | ✓ | ✗ — l'agente propone un piano | solo sola lettura (`ls`, `git status`, …) |
| `auto` | ✓ | automatiche | automatici |

- Alla conferma: **1 Sì** · **2 Sì, e non chiedere più** (salva una regola in `.mydevagent/settings.json`,
  es. `bash:pytest*` o `edit:src/app.py`) · **3 No**, e puoi scrivere cosa fare invece: l'agente lo riceve.
- `rm -rf`, `sudo`, `git push --force`, `git reset --hard`, `curl … | sh` & co. chiedono **sempre**
  conferma, anche in `auto`. `.env` e le chiavi non vengono mai letti né modificati.
- Prima di ogni modifica il file viene salvato in `.mydevagent/checkpoints/` → `/undo` e `/rewind`.
  `.mydevagent/` contiene un proprio `.gitignore`: non finisce nei tuoi commit.

## Input
| Tasto / sintassi | Effetto |
|---|---|
| `Enter` | invia |
| `Alt+Enter` o `Ctrl+J` | nuova riga |
| `Tab` | completa `/comandi`, `@file`, `@agenti` |
| `↑` / `↓` | cronologia (`~/.mydevagent/history`) |
| `Shift+Tab` | cambia modalità dei permessi (ask → auto-edit → plan) |
| `Esc` o `Ctrl+C` | durante il lavoro: interrompe (due volte = forza). Al prompt `Ctrl+C` pulisce, due volte esce |
| `Esc Esc` | al prompt: `/rewind` |
| `Ctrl+D` | esce (la sessione viene salvata) |
| `@percorso/file` | allega il file al messaggio |
| `@security` `@perf` `@web` `@mobile` `@gdpr` … | coinvolge un agente |
| `!comando` | esegue un comando shell (es. `!pytest -q`) e ne allega l'output al messaggio successivo |
| `#testo` | aggiunge una nota a `MYDEVAGENT.md` (memoria del progetto) |

## Comandi
| Comando | Cosa fa |
|---|---|
| `/help` | comandi e scorciatoie |
| `/fast` `/balanced` `/deep` `/ultra-deep` `/auto` | modalità del team (oppure `/deep <richiesta>` per un solo messaggio) |
| `/plan` | modalità piano (sola lettura) · `/plan <richiesta>` |
| `/permissions [modalità]` | mostra/cambia i permessi e le regole salvate |
| `/undo` · `/rewind` | annulla l'ultimo turno · torna a prima di un turno scelto |
| `/diff` | tutte le modifiche fatte ai file in questa sessione |
| `/agent` · `/chat` | lavora sui file · rispondi soltanto |
| `/apply` | (chat) scrive i file dell'ultima risposta dopo il diff |
| `/init` | l'agente analizza il progetto e crea `MYDEVAGENT.md` (comandi, architettura, convenzioni) |
| `/memory [testo]` | mostra la memoria del progetto · aggiunge una nota |
| `/compact` | riassume la conversazione (automatico oltre 10 turni) |
| `/model <nome>` · `/models` | cambia modello per la sessione (`--save` lo ricorda nel `.env`) · modelli installati e in uso |
| `/pull <nome>` | scarica un modello da Ollama con barra di avanzamento |
| `/skill` · `/skill <nome> <richiesta>` | skill disponibili · usa una skill per questa richiesta |
| `/vio` | saluta (e accarezza) Vio, la mascotte |
| `/agents` | i 35 agenti (nucleo e ultra) |
| `/files` · `/cost` · `/think` | allegati · token e tempo · mostra il ragionamento |
| `/index` | indicizza il progetto per la ricerca semantica (di solito lo fa da solo in background) |
| `/doctor` | verifica backend, modelli, rete, sandbox |
| `/theme [dark\|light]` | tema dei diff e del codice |
| `/resume` · `/export` · `/clear` · `/exit` | sessioni, export Markdown, nuova conversazione, esci |

## Memoria del progetto: `MYDEVAGENT.md`
Un file nella radice del progetto con comandi, architettura e convenzioni: l'agente lo legge a ogni
richiesta (legge anche `AGENTS.md` e `CLAUDE.md` se ci sono, più `~/.mydevagent/MYDEVAGENT.md` per le tue
preferenze globali). Crealo con `/init`, aggiungi note al volo con `#usa sempre pnpm`. Se contiene una
riga `- test: <comando>`, l'agente usa quel comando per i test.

## Comandi personalizzati
Crea `.mydevagent/commands/<nome>.md` (nel progetto) o `~/.mydevagent/commands/<nome>.md` (per tutti i
progetti). `$ARGUMENTS` viene sostituito con il testo dopo il comando; la prima riga `description:` compare
nel completamento.

```markdown
description: scrive i test mancanti per un file
Leggi $ARGUMENTS, individua i casi non coperti e scrivi test con il framework del progetto. Poi eseguili.
```
→ `/testa src/api/users.py`

## Skill
Istruzioni da esperto riutilizzabili, come le skill di Claude Code e di BluAgent. All'agente arriva solo
l'elenco nome + descrizione: il contenuto lo legge (con il tool `skill`, senza chiederti il permesso) solo
quando una richiesta corrisponde, così non riempie il contesto.

Una skill è una cartella con `SKILL.md` e, se servono, file di supporto (modelli, esempi, script) che
l'agente può leggere; oppure un singolo file `<nome>.md`.

```markdown
---
name: changelog
description: Scrive il changelog dal git log. Usala quando chiedo un changelog o le note di rilascio.
---
Leggi `git log` dall'ultimo tag, raggruppa per Aggiunto / Corretto e segui templates/base.md.
```

Cartelle lette (a parità di nome vince la prima): `.mydevagent/skills/` e `.claude/skills/` del progetto,
`~/.mydevagent/skills/`, `~/.claude/skills/` (quindi anche le skill che usi con Claude Code), più quelle
in `MYDEVAGENT_SKILLS_DIRS` nel `.env`, separate da `;` su Windows, per esempio le skill di BluAgent:
`MYDEVAGENT_SKILLS_DIRS=C:\Users\Santoro\BluAgent\skills`.

`/skill` le elenca, `/skill changelog prepara la 1.1` obbliga l'agente a usare quella skill.

## `/ultra-deep`
35 agenti per i lavori importanti: ricerca web se serve, requisiti, piano con avvocato del diavolo,
strategia di test, implementazione, test reali, 10 quality gate e 15 lens review in parallelo,
Integratore capo, fino a 3 giri di correzione, documentazione e release. Le fasi compaiono come
`✻ fase 4/8 · implementazione`. Sono 35–50+ chiamate al modello: con un 7B locale servono diversi minuti.

## Come è fatta (`mydevagent/tui/`)
| File | Ruolo |
|---|---|
| `app.py` | `TuiApp`: input, comandi, permessi, `!shell`, allegati; esegue `AgentRunner` (o `Orchestrator`) in un thread e disegna gli eventi dalla coda; le conferme passano dal thread della UI |
| `render.py` | `TurnRenderer`: righe `⏺`/`⎿`, diff colorati, todo, fasi, spinner, Markdown in streaming |
| `keys.py` | `Esc` durante il lavoro (quando prompt_toolkit non legge la tastiera) |
| `extras.py` | comandi personalizzati, compattazione, notifiche, warmup del modello |
| `completion.py` · `apply.py` · `session.py` | completamento · `/apply` · sessioni e `/resume` |

### Aggiungere un comando
Aggiungi nome e descrizione a `COMMANDS` in `app.py` e gestiscilo in `TuiApp.handle_command`
(oppure, senza codice, crea un comando personalizzato come sopra).

## Controllo all'avvio
Appena si apre, la UI controlla in meno di 2 secondi il server dei modelli e i modelli del profilo. Se è tutto a
posto non mostra niente. Altrimenti:
- **server spento** → spiega come avviarlo (`ollama serve`, l'app Ollama o LM Studio); Invio per riprovare;
- **modelli mancanti** → elenco con dimensione indicativa e tre scelte: **1** scaricarli ora (barra di
  avanzamento), **2** usare i modelli già installati più adatti (con l'opzione di ricordare la scelta nel `.env`),
  **3** continuare;
- **profilo non adatto all'hardware** → un consiglio, mostrato una volta sola (es. «Hai una GPU da 12 GB: ti
  consiglio gpu16»).

Anche gli errori durante l'uso sono spiegati in italiano con il rimedio (modello non installato, server non
raggiungibile, modello troppo lento, memoria insufficiente), nella UI, in `mydevagent ask` e nel server.

## Vio, la mascotte
Vio è il polpetto viola di MyDevAgent (tanti tentacoli, come i suoi agenti), disegnato in pixel art direttamente
nel terminale: 14 colonne per 4 righe, sopra la barra dove scrivi, con accanto una frase.

- Cambia espressione con la modalità: curiosa in `ask`, entusiasta in `auto-edit`, con gli occhiali in `plan`,
  con gli occhi a stella in `auto`, e ne ha una per la chat e per ogni team (`/fast`, `/balanced`, `/deep`,
  `/ultra-deep`). Con `Shift+Tab` cambia subito, insieme alla frase che spiega cosa farà.
- Muove i tentacoli e ogni tanto sbatte le palpebre.
- Mentre il team lavora resta sotto al lavoro in corso e si guarda intorno; a fine lavoro sorride e ti dice quanto
  ci ha messo, se qualcosa va storto fa gli occhi a X.
- `/vio` la saluta (e la accarezza).

Anteprima di tutte le espressioni: `python -m mydevagent.tui.mascot`.
