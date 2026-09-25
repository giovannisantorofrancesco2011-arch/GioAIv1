# MyDevAgent in Cursor

Cursor invia le richieste dei modelli custom **dai propri server**, non dal tuo PC: per questo non può
raggiungere `localhost`. Serve un URL pubblico temporaneo verso il tuo server locale.

1. Imposta una chiave (obbligatorio se esponi il server!):
   ```bash
   export MYDEVAGENT_API_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
   mydevagent serve
   ```
2. Apri un tunnel HTTPS (uno a scelta):
   ```bash
   cloudflared tunnel --url http://127.0.0.1:8000     # → https://xxxx.trycloudflare.com
   # oppure: ngrok http 8000
   ```
3. Cursor → **Settings → Models**:
   - **OpenAI API Key**: la tua `MYDEVAGENT_API_KEY`
   - **Override OpenAI Base URL**: `https://xxxx.trycloudflare.com/v1`
   - **Add model**: `mydevagent`, `mydevagent-fast`, `mydevagent-deep`
4. Nella chat di Cursor seleziona `mydevagent`.

Limiti: Tab/autocomplete e alcune funzioni agent di Cursor usano solo i modelli di Cursor. Il codice
passa dal tunnel: se vuoi restare 100% offline usa VS Code + Continue.
