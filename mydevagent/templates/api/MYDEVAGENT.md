# La mia API

API web in Python con FastAPI. I dati sono in memoria (si azzerano al riavvio).

## Comandi
- installa: `python -m pip install -r requirements.txt`
- avvio: `python -m uvicorn main:app --reload` (documentazione interattiva su http://127.0.0.1:8000/docs)
- test: `python -m pytest -q`

## Convenzioni
- ogni endpoint è una funzione con `@app.get` / `@app.post` e i tipi dei dati sono classi Pydantic
- per ogni endpoint nuovo aggiungi un test in test_main.py
