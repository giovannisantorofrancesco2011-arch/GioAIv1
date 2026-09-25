# Bot Discord

Bot in Python con discord.py. I comandi sono funzioni con `@bot.command()` in bot.py.

## Comandi
- installa: `python -m pip install -r requirements.txt`
- avvio: `python bot.py`

## Prima volta
1. Su https://discord.com/developers/applications crea un'applicazione, poi nella scheda Bot premi
   «Reset Token» e copia il token.
2. Sempre nella scheda Bot attiva «Message Content Intent».
3. Copia .env.example in .env e incolla il token dopo `DISCORD_TOKEN=` (il file .env non va mai su GitHub).
4. In OAuth2 → URL Generator scegli `bot` e i permessi «Send Messages», apri il link e invita il bot nel
   tuo server.

## Convenzioni
- un comando nuovo = una funzione async con `@bot.command()` e una docstring
- il token si legge solo da .env, mai scritto nel codice
