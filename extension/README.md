# MyDevAgent per VS Code

**Vio**, l'agente di programmazione di [MyDevAgent](https://github.com/giovannisantorofrancesco2011-arch/MyDevAgent),
dentro l'editor. Tutto gira sul tuo computer con Ollama: niente cloud, niente abbonamenti.

- **Chat** nella barra laterale (Ctrl+L): Vio legge il progetto, modifica i file, lancia i test. Vede il file aperto
  e il codice selezionato; con `@` citi altri file, con `/` usi i comandi (`/stats`, `/undo`, `/diff`, `/init`…).
- **Modifiche da confermare**: prima di toccare un file Vio apre il confronto prima/dopo; applichi con ✓ o rifiuti con ✗
  (anche dalla chat), e con `/undo` torni indietro.
- **Ctrl+I** sul codice selezionato (o dove vuoi aggiungerne): descrivi la modifica e Vio la scrive nel file.
  Ctrl+Invio per tenerla, Esc per annullarla.
- **Tab**: suggerimenti di codice mentre scrivi (meglio con il modello `qwen2.5-coder:1.5b-base`).
- **Tema MyDevAgent Dark**: nero con sfumature di viola.

Serve MyDevAgent installato (con la sua cartella `.venv`): l'estensione lo cerca da sola, oppure imposta
`mydevagent.percorso`. Su Windows, se manca, Vio può installarlo con un clic (Python, Ollama, modelli compresi).

Fa parte di **MyDevAgent Studio**, l'editor basato su VSCodium con tutto già pronto.
