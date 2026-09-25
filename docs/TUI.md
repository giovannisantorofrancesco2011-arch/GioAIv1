# Interfaccia da terminale (stile Claude Code)

```bash
mydevagent                 # apre l'interfaccia nella cartella corrente
mydevagent -p gpu16        # con un altro profilo
mydevagent --continue      # riprende l'ultima sessione di questa cartella
mydevagent chat --plain    # vecchia chat semplice (pipe, terminali limitati)
```

```
╭──────────────────────────────────────────────────────────────╮
│  ✻ Benvenuto in MyDevAgent  15 agenti · local-first          │
│  cwd:     ~/code/mio-progetto                                │
│  profilo: gpu8 · modello: qwen2.5-coder:7b                   │
╰──────────────────────────────────────────────────────────────╯
> /balanced migliora @src/calc.py con type hints
  ⎿  allegato src/calc.py
⏺ Team balanced · 5 agenti
  ⎿  Architetto del Codice → Linguaggi & Framework → Debugging & Testing → Code Reviewer & Refactor → Formatter
⏺ Architetto del Codice
  ⎿  4.1s · 946 tok
⏺ Linguaggi & Framework
  ⎿  6.3s · 870 tok
⠋ ✻ Debugging & Testing sta lavorando… (Ctrl+C per interrompere · 12s · 2.1k tok)

 gpu8  qwen2.5-coder:7b · modo auto · ● online · ~4.831 tok ·  main
```

## Input
| Tasto / sintassi | Effetto |
|---|---|
| `Enter` | invia |
| `Alt+Enter` o `Ctrl+J` | nuova riga (messaggi multi-riga, codice incollato) |
| `Tab` | completa `/comandi`, `@file`, `@agenti` |
| `↑` / `↓` | cronologia (salvata in `~/.mydevagent/history`) |
| `Ctrl+C` | durante una risposta: interrompe (2 volte = forza). Al prompt: pulisce (2 volte = esce) |
| `Ctrl+D` | esce (la sessione viene salvata) |
| `@percorso/file` | allega il file al messaggio |
| `@security` `@perf` `@web` `@db` … | coinvolge un agente (vedi `docs/AGENTS.md`) |
| `!comando` | esegue un comando shell nella cartella (es. `!pytest -q`) e allega l'output al messaggio successivo |

## Comandi
| Comando | Cosa fa |
|---|---|
| `/help` | comandi e scorciatoie |
| `/fast` `/balanced` `/deep` `/auto` | cambia modalità (oppure `/deep <richiesta>` per un solo messaggio) |
| `/apply` | scrive su disco i file dell'ultima risposta: diff per ogni file, poi **1 Sì · 2 Sì a tutti · 3 No**. Solo dentro la cartella del progetto, mai file sensibili (`.env`, chiavi) |
| `/agents` | i 15 agenti con i loro alias |
| `/files` | file allegati all'ultimo messaggio |
| `/cost` | turni, token, tempo |
| `/think` | mostra/nasconde i blocchi di ragionamento del modello |
| `/index` | indicizza il progetto per il RAG |
| `/resume` | riprende una sessione precedente di questa cartella |
| `/export` | salva la conversazione in `mydevagent-<id>.md` |
| `/clear` | nuova conversazione |
| `/exit` | esci |

## Come è fatta (`mydevagent/tui/`)
| File | Ruolo |
|---|---|
| `app.py` | `TuiApp`: loop di input, comandi, `!shell`, allegati; esegue `Orchestrator.run` in un thread e disegna gli eventi dalla coda |
| `render.py` | `TurnRenderer`: righe `⏺`/`⎿` per agenti e tool, spinner, Markdown in streaming (i blocchi completi vanno nello scrollback, solo la coda resta animata) |
| `completion.py` | completamento di `/comandi`, `@agenti`, `@file` |
| `apply.py` | `/apply`: diff + conferma + scrittura confinata nella workspace |
| `session.py` | sessioni in `~/.mydevagent/sessions/` (`MYDEVAGENT_STATE_DIR` per cambiarla) |

L'interruzione usa `Orchestrator.run(cancel=threading.Event())`: il team si ferma prima dell'agente
successivo e lo streaming si chiude al chunk successivo.

### Aggiungere un comando
1. aggiungi nome e descrizione a `COMMANDS` in `app.py` (compare subito in `/help` e nel completamento);
2. gestiscilo in `TuiApp.handle_command` con un nuovo `elif cmd == "/nome":`.

### Cambiare i colori
`ACCENT` in `render.py` (colore principale) e `_style()` in `app.py` (prompt, toolbar, menu).
