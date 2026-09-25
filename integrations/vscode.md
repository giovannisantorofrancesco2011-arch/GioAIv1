# MyDevAgent in VS Code

Tre strade, dalla più completa alla più semplice.

## 1. Continue.dev (consigliata: chat multi-agente + autocomplete + @codebase)
1. Installa l'estensione **Continue** dal Marketplace.
2. Avvia il server: `mydevagent serve` (lascialo aperto in un terminale).
3. Scarica il modello per l'autocomplete: `ollama pull qwen2.5-coder:1.5b-base`.
4. Copia [`continue/config.yaml`](continue/config.yaml) in `~/.continue/config.yaml`
   (Windows: `%USERPROFILE%\.continue\config.yaml`).
5. Apri la sidebar di Continue (`Ctrl/Cmd+L`) → scegli **MyDevAgent (team 15 agenti)**.
   - `Ctrl/Cmd+I` = edit inline (usa *MyDevAgent Fast*).
   - Tab = autocomplete locale.
   - Nel messaggio: `/deep`, `@security`, `@perf`, `@web` per guidare il team.

## 2. GitHub Copilot Chat con modelli locali (BYOK)
Copilot Chat permette di aggiungere modelli locali tramite **Ollama**:
1. `ollama create mydevagent -f modelfiles/Modelfile.gpu8` (lo fa già `scripts/install.sh`).
2. In Copilot Chat: selettore modelli → **Manage Models…** → **Ollama** → seleziona `mydevagent`.

Così usi la persona MyDevAgent a singolo agente (veloce). Per il team completo a 15 agenti usa Continue
(o un provider "OpenAI Compatible" puntato a `http://127.0.0.1:8000/v1`, se la tua versione di VS Code
lo offre in *Manage Models*). Nota: alcune funzioni di Copilot (es. completamenti inline) possono ancora
richiedere un account Copilot.

## 3. Cline / Roo Code (agenti che modificano file ed eseguono comandi)
Provider **OpenAI Compatible** → Base URL `http://127.0.0.1:8000/v1`, API key qualsiasi (o
`MYDEVAGENT_API_KEY`), Model ID `mydevagent-fast` (Cline invia prompt molto lunghi con le sue istruzioni:
la modalità fast evita di moltiplicarli per 15 agenti). In alternativa scegli direttamente il provider
**Ollama** con il modello `mydevagent`.
