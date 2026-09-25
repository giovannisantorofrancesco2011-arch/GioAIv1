**MyDevAgent Studio** è l'editor di codice con Vio: basato su VSCodium, con MyDevAgent come agente principale.

### Come si installa
1. Scarica **MyDevAgent-Studio-Setup.exe** qui sotto e aprilo.
2. Windows potrebbe dire «Windows ha protetto il PC» (l'installer non è firmato): clicca **Ulteriori informazioni** e poi **Esegui comunque**.
3. Lascia la spunta su «Installa anche Python, Ollama e MyDevAgent se mancano»: si apre una finestra che scarica quello che serve (la prima volta i modelli pesano qualche GB).
4. Apri MyDevAgent Studio, apri la cartella del tuo progetto e parla con Vio nella barra a sinistra.

### Cosa c'è
- Chat con Vio: legge il progetto, modifica i file e lancia i test; tu confermi ogni modifica vedendo il confronto prima/dopo.
- **Ctrl+I** sul codice selezionato (o dove vuoi del codice nuovo): Vio lo scrive come chiedi; **Ctrl+Invio** per tenerlo, **Esc** per annullare.
- **Tab**: suggerimenti di codice mentre scrivi.
- `/stats`, `/undo`, `/diff`, i team di agenti e tutti i comandi di MyDevAgent.
- Tema nero e viola, interfaccia in italiano.

`mydevagent.vsix` è la stessa estensione per chi usa già VS Code o VSCodium.
