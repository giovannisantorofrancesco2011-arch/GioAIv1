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
  pezzo di testo), `write_file`, `bash`, `run_tests`, `todo_write`, `web_search`,
  `web_fetch` (legge una pagina web: la prima volta per ogni sito chiede il permesso, anche in `plan`),
  `preview` (guarda una pagina del progetto su localhost, vedi «Anteprima dei siti»).
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
| `/add-dir [cartella]` · `/add-dir rimuovi <cartella>` | lavora anche su altre cartelle (es. frontend e backend) |
| `/anteprima [file \| url]` | apre nel browser il sito del progetto, servito su localhost |
| `/impara` · `/impara off` | modalità impara: spiega cosa fa e ti lascia scrivere un pezzo di codice |
| `/new [modello] [nome]` | crea un progetto pronto (sito, gioco, bot-discord, api, python) e ci lavora dentro |
| `/multi` · `/multi stop` | multigiocatore: gli amici sulla tua rete seguono la sessione dal browser e scrivono all'agente |
| `/init` | l'agente analizza il progetto e crea `MYDEVAGENT.md` (comandi, architettura, convenzioni) |
| `/memory [testo]` | mostra la memoria del progetto · aggiunge una nota |
| `/compact` | riassume la conversazione (automatico oltre 10 turni) |
| `/model <nome>` · `/models` | cambia modello per la sessione (`--save` lo ricorda nel `.env`) · modelli installati e in uso |
| `/pull <nome>` | scarica un modello da Ollama con barra di avanzamento |
| `/skill` · `/skill <nome> <richiesta>` | skill disponibili · usa una skill per questa richiesta |
| `/plugin` · `/plugin install <utente/repo>` · `update` · `remove` | plugin nel formato di Claude Code |
| `/hooks` · `/hooks trust` | hook attivi · attiva quelli del progetto |
| `/mcp` · `/mcp reload` · `/mcp trust` | server MCP e il loro stato · riavviali · attiva quelli del progetto |
| `/vio` | saluta (e accarezza) Vio, la mascotte |
| `/agents` | i 35 agenti (nucleo e ultra) |
| `/files` · `/cost` · `/think` | allegati · token e tempo · mostra il ragionamento |
| `/stats` · `/stats 7` · `/stats 30` | statistiche: questa sessione e da sempre (o ultimi giorni), grafico dell'attività, giorni di fila |
| `/index` | indicizza il progetto per la ricerca semantica (di solito lo fa da solo in background) |
| `/doctor` | verifica backend, modelli, rete, sandbox |
| `/update` | aggiorna MyDevAgent (`git pull`, dipendenze se cambiate); all'avvio Vio ti avvisa delle novità |
| `/theme [dark\|light]` | tema dei diff e del codice |
| `/resume` · `/export` · `/clear` · `/exit` | sessioni, export Markdown, nuova conversazione, esci |

## Progetti pronti: `/new`
`/new` elenca i modelli, `/new <modello> [nome]` crea il progetto e da lì in poi lavori dentro di lui:

| Modello | Cosa ottieni |
|---|---|
| `sito` | sito web con HTML, CSS e JavaScript (tema chiaro/scuro), senza installare niente |
| `gioco` | gioco 2D con Pygame: acchiappa le stelle |
| `bot-discord` | bot Discord con `!ciao` e `!dado`; i passaggi per il token sono nel suo `MYDEVAGENT.md` |
| `api` | API con FastAPI e i test (`python -m pytest -q`) |
| `python` | programma Python con i test, per iniziare |

Il progetto nasce nella cartella aperta se è vuota, altrimenti in una sottocartella nuova (mai dentro la
cartella di MyDevAgent: lì va accanto). Ogni modello ha già il suo `MYDEVAGENT.md` con i comandi per
avviarlo e provarlo, un `.gitignore` e `git init`. Poi basta dire cosa vuoi cambiare: «fai il sito sui
miei disegni», «aggiungi i nemici al gioco».

## Più cartelle insieme: `/add-dir`
Quando un progetto sta in più cartelle (il sito in `frontend`, il server in `backend`), apri MyDevAgent in
una e aggiungi le altre, come in Claude Code:

```
/add-dir ../backend          aggiunge una cartella (ricordata per questo progetto)
/add-dir                     mostra le cartelle
/add-dir rimuovi ../backend  la toglie
mydevagent --add-dir ../backend   solo per questa volta
```

L'agente vede l'elenco dei file e la memoria (`MYDEVAGENT.md`) di ogni cartella, e le usa con percorsi come
`../backend/app.py`: legge, cerca (`grep` guarda in tutte), modifica con i soliti permessi, e `/undo` annulla
anche lì. Puoi allegare i loro file con `@../backend/app.py`. I comandi partono dalla cartella principale.

## Anteprima dei siti
Quando l'agente cambia una pagina web la guarda da solo, con lo strumento **Anteprima**: la apre su
localhost in un browser senza finestra (Chrome, Edge o Chromium, quello che hai già), fa uno screenshot che
il modello `vision` descrive, e legge gli errori della console, i file mancanti e il testo visibile.
- un file HTML del progetto (`index.html` se non dice altro) viene servito su `127.0.0.1`, senza file
  nascosti (`.git`, `.env`) né chiavi;
- un sito con il suo server (`npm run dev`, `uvicorn`, Flask…) si apre con il suo url: l'agente può
  accenderlo con il suo comando, che chiede il permesso come ogni comando e resta acceso finché MyDevAgent
  è aperto (l'output finisce in `.mydevagent/preview-server.log`).

Lo screenshot resta in `.mydevagent/preview.png`. Senza modello vision l'agente usa solo testo ed errori:
`/pull qwen2.5vl:7b` (o quello del tuo profilo, vedi `/models`). Per vedere il sito tu: `/anteprima` apre
`index.html` nel browser, `/anteprima pagina.html` un'altra pagina, `/anteprima localhost:5173` un server
già acceso. Un browser diverso: `MYDEVAGENT_BROWSER=<percorso>` nel `.env`.

## Modalità impara: `/impara`
Per imparare mentre programmi, come lo stile «Learning» di Claude Code. Con `/impara` l'agente:
- dice in una o due frasi cosa sta per fare e perché;
- scrive quasi tutto, ma ti lascia **un pezzo piccolo** (una condizione, un ciclo, il corpo di una funzione):
  lo trovi nel codice con un commento `TODO(tu):` e un suggerimento, non la soluzione;
- finisce con «💡 Da sapere»: due o tre concetti spiegati in parole semplici.

Quando hai scritto il tuo pezzo diglielo («fatto»): lo legge e ti dice cosa va e cosa sistemare. I test che
provano il tuo pezzo possono fallire finché non lo scrivi, e la review non lo conta come errore. Vio mostra
«impara» sopra l'input; la scelta resta anche ai prossimi avvii, `/impara off` la spegne.

## Multigiocatore: `/multi`
Per programmare insieme a un amico che è sulla tua stessa rete (lo stesso Wi-Fi). `/multi` mostra un link
con un codice, per esempio `http://192.168.1.23:8765/?codice=K7M2QP`: l'amico lo apre nel browser (PC o
telefono, non deve installare niente), scrive il suo nome ed entra.
- vede quello che vedi tu nel terminale: le righe `⏺`/`⎿` dei tool, i diff colorati e le risposte;
- scrive all'agente dalla pagina: il messaggio compare da te come `› Marco: …` e l'agente lo esegue come
  i tuoi (se stavi scrivendo qualcosa resta lì, lo ritrovi dopo);
- le modifiche ai file e i comandi chiesti da un amico li **confermi sempre tu**, anche se sei in modalità
  auto; lui vede «deve confermare…» e poi com'è andata. I comandi `/`, `!` e `#` restano solo tuoi.

Vio ti dice quando qualcuno si collega, e `/multi` mostra di nuovo link e chi è entrato. `/multi stop` (o
l'uscita da MyDevAgent) chiude la sessione. Dai il codice solo a chi ti fidi: tramite l'agente può leggere
i file del progetto (non `.env` e le chiavi). La prima volta Windows può chiedere il permesso per Python nel
firewall: consentilo sulle reti private.

## Statistiche: `/stats`
Due colonne, **questa sessione** e **da sempre** (`/stats 7` o `/stats 30`: solo gli ultimi giorni):
richieste, token, tempo di lavoro dell'agente, strumenti usati, file modificati, righe aggiunte e tolte,
test passati e falliti. Sotto c'è il grafico dell'attività come su GitHub (una colonna per settimana,
più è viola acceso più richieste hai fatto quel giorno), la serie di giorni di fila 🔥 con il tuo record,
il giorno record, l'ora preferita, il modello e il team che usi di più e i progetti su cui lavori.
Ogni richiesta aggiunge una riga a `~/.mydevagent/stats.jsonl` (anche quelle fatte da MyDevAgent Studio):
resta sul tuo PC, e per ricominciare da zero basta cancellare quel file.

## Memoria del progetto: `MYDEVAGENT.md`
Un file nella radice del progetto con comandi, architettura e convenzioni: l'agente lo legge a ogni
richiesta (legge anche `AGENTS.md` e `CLAUDE.md` se ci sono, più `~/.mydevagent/MYDEVAGENT.md` per le tue
preferenze globali). Crealo con `/init`, aggiungi note al volo con `#usa sempre pnpm`. Se contiene una
riga `- test: <comando>`, l'agente usa quel comando per i test.

## Comandi personalizzati
Crea `.mydevagent/commands/<nome>.md` (nel progetto) o `~/.mydevagent/commands/<nome>.md` (per tutti i
progetti); valgono anche quelli di Claude Code in `.claude/commands/` e `~/.claude/commands/`.
`$ARGUMENTS` viene sostituito con il testo dopo il comando, `$1`, `$2`… con le singole parole; la
`description:` (nel frontmatter o sulla prima riga) compare nel completamento.

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

## Plugin (compatibili con Claude Code)
Un plugin è una cartella con `.claude-plugin/plugin.json` e dentro `commands/` (comandi `/nome`), `skills/`
(skill) e `agents/` (sotto-agenti, vedi sotto).
È lo stesso formato di Claude Code, quindi funzionano i plugin già pronti:

```
/plugin install anthropics/claude-code     # il marketplace ufficiale: 13 plugin
/plugin install utente/repo                # qualsiasi repository GitHub (o un URL git, o una cartella)
/plugin                                    # elenco con comandi, skill e agenti di ognuno
/plugin update claude-code                 # git pull
/plugin remove claude-code                 # toglie la cartella scaricata (e i plugin che contiene)
```

Poi i comandi compaiono con `/` (anche come `/plugin:comando`), le skill con `/skill` e i sotto-agenti con
`/agents`. Vengono caricati:
i plugin in `.mydevagent/plugins/` del progetto, quelli installati con `/plugin install`
(`~/.mydevagent/plugins/`), **quelli che hai già installato in Claude Code** e le cartelle in
`MYDEVAGENT_PLUGINS_DIRS`.

Funzionano anche gli hook e i server MCP dei plugin (vedi sotto). Differenza da Claude Code: `!`comando``
nei comandi non viene eseguito prima dell'invio: lo esegue l'agente con i suoi tool, chiedendo il permesso
come sempre.

## Hook (comandi automatici)
Comandi che partono da soli in certi momenti, scritti come in Claude Code. Esempio: formattare ogni file
che l'agente modifica e vietargli `git push`. In `.mydevagent/settings.json` (o `.claude/settings.json`):

```json
{"hooks": {
  "PostToolUse": [{"matcher": "Edit|Write",
                   "hooks": [{"type": "command", "command": "ruff format ."}]}],
  "PreToolUse":  [{"matcher": "Bash",
                   "hooks": [{"type": "command", "command": "python .mydevagent/no_push.py"}]}]
}}
```

| Evento | Quando | Cosa può fare |
|---|---|---|
| `PreToolUse` | prima di un tool | bloccarlo (exit code 2: il testo su stderr arriva all'agente) |
| `PostToolUse` | dopo un tool | dare un messaggio all'agente (exit 2 o `{"decision": "block", "reason": …}`) |
| `UserPromptSubmit` | quando invii una richiesta | bloccarla, o aggiungere contesto (quello che stampa) |
| `Stop` · `SubagentStop` | quando l'agente (o un sotto-agente) vuole finire | chiedergli di continuare (exit 2 con il motivo) |
| `SessionStart` | all'avvio (in background) | aggiungere contesto per tutta la sessione |

Il comando riceve su stdin il JSON dell'evento (`tool_name`, `tool_input` con `file_path`, `prompt`…), con i
nomi dei tool di Claude Code (`Bash`, `Edit`, `Write`, `Read`…); nel matcher vanno bene anche i nomi di
MyDevAgent (`bash`, `edit_file`…). Valgono `$CLAUDE_PROJECT_DIR` e `${CLAUDE_PLUGIN_ROOT}`; su Windows gli
hook partono con il bash di Git, se è installato, come in Claude Code.

Da dove: `~/.claude/settings.json` (gli hook che usi già con Claude Code), `~/.mydevagent/settings.json`, i
plugin, e quelli del progetto. **Quelli del progetto partono solo dopo il tuo sì**, che MyDevAgent chiede
all'avvio (e di nuovo se cambiano): un repository scaricato non deve eseguire comandi da solo sul tuo PC.
`/hooks` li elenca, `/hooks trust` attiva quelli del progetto, `"disableAllHooks": true` li spegne tutti.
Gli hook `prompt`, `async`/`asyncRewake` e con `if` non sono ancora eseguiti (in `/hooks` sono in grigio).

## Server MCP (strumenti esterni)
Con MCP l'agente usa strumenti di altri programmi: GitHub, database, browser, file system, documentazione…
Si configurano come in Claude Code, in `.mcp.json` nel progetto o in `~/.mydevagent/mcp.json` per tutti i
progetti:

```json
{"mcpServers": {
  "github": {"command": "npx", "args": ["-y", "@modelcontextprotocol/server-github"],
             "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"}},
  "docs":   {"type": "http", "url": "https://esempio.com/mcp",
             "headers": {"Authorization": "Bearer ${DOCS_TOKEN}"}}
}}
```

Vengono letti anche i server che usi già con Claude Code (`~/.claude.json`, anche quelli del singolo
progetto) e quelli dei plugin. `${VAR}` e `${VAR:-predefinito}` prendono i valori dalle variabili
d'ambiente (o dal `.env`), così i token non finiscono nel file. Come per gli hook, i server scritti nel
progetto partono solo dopo il tuo sì.

All'avvio MyDevAgent li collega in background. All'agente arriva l'elenco dei server con i nomi degli
strumenti e un solo tool, `mcp`: prima chiede gli argomenti di un server, poi usa lo strumento. Così anche
un server con 50 strumenti non riempie il contesto di un modello locale. Ogni uso chiede conferma come un
comando (con «Sì, e non chiedere più» per quello strumento); in modalità plan sono permessi solo gli
strumenti che il server dichiara di sola lettura. Negli hook lo strumento si chiama `mcp__server__nome`,
come in Claude Code.

`/mcp` mostra i server e il loro stato, `/mcp reload` li riavvia, `/mcp trust` attiva quelli del progetto.
Trasporti: `stdio` (un comando) e `http`. Il vecchio `sse` e il login OAuth non ci sono ancora: per i server
remoti metti il token negli `headers`.

## Sotto-agenti
Agenti specializzati che l'agente principale chiama da solo, come in Claude Code: ognuno lavora in un
contesto tutto suo (non vede la conversazione), con i suoi tool, e restituisce solo il resoconto finale.
Così la ricerca nel codice o una review non riempiono il contesto dell'agente principale, che con i modelli
locali è piccolo. Un file Markdown in `.mydevagent/agents/` o `.claude/agents/` (progetto),
`~/.mydevagent/agents/` o `~/.claude/agents/` (tutti i progetti), oppure negli `agents/` dei plugin:

```markdown
---
name: code-reviewer
description: Rivede il codice appena modificato. Usalo dopo ogni modifica importante.
tools: Read, Grep, Glob
model: haiku
---
Sei un revisore severo: cerca bug, casi limite e nomi poco chiari. Non modificare i file.
```

`tools` è facoltativo (senza, ha tutti i tool) e accetta i nomi di Claude Code (`Read`, `Grep`, `Glob`,
`Bash`, `Edit`, `Write`…) o quelli di MyDevAgent; `model: haiku` usa il modello veloce. Le modifiche di un
sotto-agente passano dai soliti permessi e finiscono nel riepilogo, nella review e in `/undo`. Un
sotto-agente non può chiamarne altri. Quando finisce partono gli hook `SubagentStop`. `/agents` li elenca
sotto gli agenti del team.

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
| `multi.py` · `multi.html` | `/multi`: la stanza (server HTTP con il feed in Server-Sent Events) e la pagina per gli amici |
| `statsview.py` | `/stats`: tabella, grafico dell'attività e serie di giorni (i dati li raccoglie `mydevagent/stats.py`) |

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
