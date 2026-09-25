# I 15 agenti di MyDevAgent

Tutti gli agenti condividono **lo stesso modello caricato** (niente 15 modelli in VRAM): cambiano il
prompt di ruolo, le sezioni della blackboard che leggono, i tool, il tier di modello e il budget di token.
Definizioni: [`config/agents.yaml`](../config/agents.yaml) · prompt: [`prompts/agents/`](../prompts/agents) ·
persona comune: [`prompts/system_persona.md`](../prompts/system_persona.md).

## Come collaborano

```
                         ┌──────────── router (euristiche, 0 token) ────────────┐
                         │                                                      │
  FAST  (1 chiamata)     ▼                                                      │
  richiesta ─▶ specialista più adatto + regole del Formatter fuse ─▶ risposta   │
                                                                                │
  BALANCED / DEEP                                                               ▼
  richiesta ─▶ [11 Research]* ─▶ 1 Architect ─▶ specialisti in parallelo (2,3,5,6,7,8)
                                                     │
                                                     ▼
                                   4 Debug & Test (test + self-check in sandbox Docker)
                                                     │
                                                     ▼
                  quality gate in parallelo: 12 Reviewer (+ 9 Security, 10 Performance, 14 Edge Cases in deep)
                                                     │
                     BLOCKER/MAJOR? ── sì (max 1 giro in balanced, 2 in deep) ──▶ di nuovo agli specialisti
                                                     │ no
                                                     ▼
                                     13 Documentation (deep o se richiesto)
                                                     │
                                                     ▼
                                15 Output Formatter (streaming all'utente)

  * Research solo se servono informazioni aggiornate e sei online; offline il team lo sa e lo dichiara.
```

**Blackboard** (`mydevagent/state.py`): gli agenti non si mandano chat a vicenda. Scrivono in sezioni
condivise (`plan`, `artifacts`, `test_report`, `issues`, `research`…) e ognuno riceve **solo** le sezioni
elencate nel suo `reads`. Questo taglia i token del 50–80% rispetto alle chat multi-agente classiche.

**Protocolli di output** (parsati dal codice):
- file: ```` ```python file=app/main.py ```` → raccolti ed eseguibili in sandbox
- self-check: ```` ```python run ```` → eseguito dal Debug agent in Docker senza rete
- quality gate: `VERDICT: APPROVE|REVISE` + `- [BLOCKER|MAJOR|MINOR] area: problema → fix`

## Scheda di ogni agente

| # | Agente | Stage | Tier | Legge | Tool | Output |
|---|---|---|---|---|---|---|
| 1 | **Architetto del Codice** | plan | reasoning | request, history, files, rag, research, image_notes | rag_search, read_file, list_dir, grep | Goal · Assumptions · Design · Files · Assignments · Acceptance criteria · Risks |
| 2 | **Algoritmi & Strutture Dati** | specialist | main | request, history, files, plan, research, issues | run_code | Approach con O(·) e invariante · codice · edge case |
| 3 | **Linguaggi & Framework** | specialist | main | + rag | rag_search, read_file, web_search | Codice idiomatico · comandi di run. Agente di default |
| 4 | **Debugging & Testing** | test | main | + artifacts, test_report, image_notes | run_code, read_file, grep, git_diff, git_log | Root cause · test del framework · 1 self-check `run` |
| 5 | **Frontend** | specialist | main | + rag, image_notes | rag_search, read_file, web_search | Componenti TS accessibili, stati loading/error/empty |
| 6 | **Backend & API** | specialist | main | + rag | rag_search, read_file, web_search | Contratti, validazione, errori, auth, esempio curl |
| 7 | **Database & ORM** | specialist | main | + rag | rag_search, read_file | Modello, schema/migrazioni reversibili, indici, query |
| 8 | **DevOps & CI/CD** | specialist | main | + rag | read_file, web_search | Dockerfile multi-stage, CI con permessi minimi, deploy/rollback |
| 9 | **Security** | gate | reasoning | request, plan, artifacts, research | web_search, grep | VERDICT + issue OWASP/CWE (veto sui BLOCKER) |
| 10 | **Performance** | gate | reasoning | request, plan, artifacts, test_report | run_code | VERDICT + issue con impatto stimato |
| 11 | **Research** | research | main | request, history, research | web_search, web_fetch, rag_search | Findings con fonti numerate `[n]` |
| 12 | **Code Reviewer & Refactor** | gate | reasoning | request, plan, artifacts, test_report, issues | git_diff, read_file | VERDICT + issue su correttezza, coerenza, criteri di accettazione |
| 13 | **Documentation** | docs | main | request, plan, artifacts | read_file | README/sezione, docstring essenziali |
| 14 | **Edge Case & Robustness** | gate | reasoning | request, plan, artifacts, test_report | run_code | VERDICT + input/condizioni che rompono il codice |
| 15 | **Output Formatter** | final | main | request, history, plan, artifacts, test_report, issues, research | — | Summary · Code · Run · Notes (+ esito sandbox reale aggiunto dal sistema) |

### Dettagli e interazioni

1. **Architetto** — primo agente in balanced/deep. Decide *cosa* fare e *chi* lo fa (sezione
   Assignments), fissa i criteri di accettazione che Reviewer e Debug useranno. Non scrive implementazioni.
2. **Algoritmi** — attivato da parole come *complessità, grafo, DP, ordinamento*. Deve dichiarare O(·)
   e un invariante: il Performance gate lo verifica.
3. **Linguaggi & Framework** — lo specialista "jolly": se nessun dominio è riconosciuto lavora lui.
   Rileva lo stack dai file allegati/RAG e scrive codice idiomatico.
4. **Debug & Test** — in fast risponde direttamente ai bug (traceback incollati). Nel team scrive i test e
   **un self-check eseguito davvero** in Docker (`--network none`, fs read-only, utente nobody, limiti
   CPU/RAM). Un self-check fallito diventa un BLOCKER automatico → revisione.
5. **Frontend** — riceve le `image_notes` dal modello vision se alleghi uno screenshot/mockup.
6. **Backend & API** / 7. **Database** / 8. **DevOps** — lavorano **in parallelo** sullo stesso piano;
   la coerenza tra i loro file è verificata dal Reviewer.
9. **Security** / 10. **Performance** / 14. **Edge Cases** / 12. **Reviewer** — i quality gate girano in
   parallelo. In balanced solo il Reviewer (+ quelli richiamati da parole chiave, es. "sicuro" → Security).
   Le issue BLOCKER/MAJOR rimandano il lavoro agli specialisti con la loro versione precedente.
11. **Research** — genera 1–2 query con il modello `fast`, cerca (Tavily → Firecrawl → SearXNG →
    DuckDuckGo), legge la pagina migliore, sintetizza con fonti. In fast mode i risultati di ricerca
    vengono iniettati direttamente nel contesto (nessuna chiamata LLM extra).
13. **Documentation** — solo in deep o se chiedi documentazione.
15. **Formatter** — unisce tutto, applica le fix rimaste, produce la risposta in streaming. In fast le sue
    regole di output sono fuse nel prompt dello specialista (risparmio di una chiamata intera).

## Guidare il team dal messaggio

| Scrivi | Effetto |
|---|---|
| `/fast` `/balanced` `/deep` | forza la modalità |
| `@sec` `@security` | aggiunge Security al quality gate (o lo rende primario in fast) |
| `@perf` `@edge` `@review` | idem per Performance, Edge Cases, Reviewer |
| `@web` `@research` | forza la ricerca web |
| `@db` `@be` `@fe` `@devops` `@algo` `@lang` | forza lo specialista |
| `@docs` | aggiunge la documentazione |

`mydevagent route "la tua richiesta"` mostra la decisione del router senza chiamare il modello.
