# MyDevAgent con Aider, Open WebUI e altri client OpenAI-compatibili

## Aider (pair programming da terminale, modifica i file e fa commit)
```bash
pip install aider-chat
export OPENAI_API_BASE=http://127.0.0.1:8000/v1
export OPENAI_API_KEY=local            # o MYDEVAGENT_API_KEY
aider --model openai/mydevagent-fast   # edit veloci
aider --model openai/mydevagent        # team completo per task complessi
```
Aider chiede al modello di rispondere in formati di edit specifici: il team li rispetta nella modalità
fast (una sola chiamata con le istruzioni di Aider). Se preferisci, usa direttamente Ollama:
`aider --model ollama_chat/mydevagent`.

## Open WebUI (interfaccia web tipo ChatGPT)
Settings → Connections → OpenAI API → URL `http://host.docker.internal:8000/v1`, key `local`.

## Python (SDK OpenAI)
```python
from openai import OpenAI
client = OpenAI(base_url="http://127.0.0.1:8000/v1", api_key="local")
stream = client.chat.completions.create(
    model="mydevagent", stream=True,
    messages=[{"role": "user", "content": "Scrivi un rate limiter token-bucket in Go con test"}],
)
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")
```

## Python (libreria, senza server)
```python
from mydevagent import Orchestrator
print(Orchestrator().ask("/deep API FastAPI per upload file su S3 con validazione e test"))
```
