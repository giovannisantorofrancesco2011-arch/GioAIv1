# MyCode

MyCode è Qwen2.5-Coder 7B addestrato per comportarsi come i migliori assistenti di programmazione: risponde
dritto al punto, è onesto su cosa ha verificato, legge il codice prima di cambiarlo, fa modifiche piccole e
chiede conferma prima di fare danni. Funziona da solo in Ollama (`ollama run mycode`) e come cervello di
MyDevAgent (`mydevagent -p mycode`).

Una cosa da sapere subito: l'addestramento insegna a MyCode lo **stile** e il **metodo** di quei file, e un po'
delle loro conoscenze. Non gli dà l'intelligenza di un modello enorme: resta un modello da 7 miliardi di
parametri che gira sul tuo PC, quindi su problemi difficili sbaglierà più spesso di un modello in cloud.

## Cosa c'è in questa cartella

| File | A cosa serve |
|---|---|
| `MANUALE.md` | le regole di MyCode (comportamento e conoscenze), ricavate dai tuoi 14 file |
| `SYSTEM.txt`, `AGENT_SYSTEM.txt` | i prompt di sistema usati negli esempi (chat e modalità agente) |
| `data/train.jsonl`, `data/val.jsonl` | le conversazioni d'esempio per l'addestramento e per la verifica |
| `config.yaml` | le impostazioni dell'addestramento, già pronte per la RTX 4060 (8 GB) |
| `crea_mycode.py`, `crea_mycode.bat` | creano il modello `mycode` in Ollama |
| `MyCode_Colab.ipynb` | lo stesso addestramento su Google Colab, gratis, se sul PC non va |
| `check_data.py` | controlla che gli esempi siano scritti bene |

## 1. Provalo subito, senza addestramento

Serve solo Ollama con `qwen2.5-coder:7b` (`ollama pull qwen2.5-coder:7b`). Dalla cartella del progetto:

```bat
.venv\Scripts\python.exe finetune\mycode\crea_mycode.py --subito
ollama run mycode
```

Questa versione è il modello normale con il manuale come prompt di sistema. Si comporta già meglio, ma solo in
`ollama run`: MyDevAgent manda il suo prompt di sistema e il manuale sparisce. Per avere il comportamento
dentro il modello serve l'addestramento qui sotto.

## 2. Addestralo sul tuo PC (Windows + WSL2)

Gli strumenti di addestramento (Unsloth) funzionano su Linux, quindi su Windows si usa WSL2, cioè Ubuntu
dentro Windows. Basta farlo una volta.

**Installa WSL2.** Apri PowerShell come amministratore, scrivi il comando e riavvia il PC:

```powershell
wsl --install -d Ubuntu-24.04
```

Al primo avvio di "Ubuntu" dal menu Start ti chiede un nome utente e una password (quella di Linux, puoi
sceglierla tu). Il driver NVIDIA va aggiornato **su Windows** (GeForce Experience o nvidia.com): dentro Ubuntu
non si installa nessun driver. Controlla che la scheda si veda:

```bash
nvidia-smi
```

Deve comparire la RTX 4060. Se dice "command not found", aggiorna il driver su Windows e riavvia.

**Prepara Ubuntu** (nella finestra di Ubuntu):

```bash
sudo apt update
sudo apt install -y python3-venv python3-dev build-essential cmake curl git libcurl4-openssl-dev
python3 -m venv ~/mycode-venv
source ~/mycode-venv/bin/activate
pip install --upgrade pip
pip install unsloth pyyaml
```

L'installazione scarica qualche GB (PyTorch con CUDA). `cmake` e `libcurl` servono alla fine, per creare il
file `.gguf`.

**Addestra.** Prima chiudi Ollama (icona vicino all'orologio, "Quit Ollama") e i giochi o programmi che usano
la scheda video, così tutti gli 8 GB restano liberi. I dischi di Windows in Ubuntu si trovano sotto `/mnt/c`:

```bash
source ~/mycode-venv/bin/activate
cd /mnt/c/Users/Santoro/Desktop/GioAIv1-claude-gracious-mayer-mt8l9b   # la cartella del progetto
python finetune/mycode/check_data.py
python finetune/train_qlora.py --config finetune/mycode/config.yaml --export-gguf
```

La prima volta scarica il modello base (circa 5,5 GB). L'addestramento dura di solito da una a qualche ora; ogni
tanto stampa la `loss`, che deve scendere. Alla fine crea il file `.gguf` in `finetune/mycode/outputs/`. Ti
servono circa 30 GB liberi sul disco.

Se va in errore:

- "CUDA out of memory": controlla che Ollama sia chiuso. Se non basta, in `config.yaml` metti
  `max_seq_length: 1536`, oppure usa Colab (punto 3).
- Il PC si blocca o il processo viene "Killed" alla fine, durante il salvataggio: WSL ha poca RAM. Crea il file
  `C:\Users\Santoro\.wslconfig` con queste righe, poi in PowerShell `wsl --shutdown` e riprova:

  ```ini
  [wsl2]
  memory=12GB
  swap=16GB
  ```

**Crea MyCode in Ollama.** Riapri Ollama, poi in Windows fai doppio clic su `finetune\mycode\crea_mycode.bat`
(oppure `.venv\Scripts\python.exe finetune\mycode\crea_mycode.py`). Trova da solo il `.gguf` e crea `mycode`,
sostituendo la versione `--subito` se c'era.

```bat
ollama run mycode
```

## 3. In alternativa: Google Colab

Se sul PC non va, apri `MyCode_Colab.ipynb` su [colab.research.google.com](https://colab.research.google.com)
(File, Carica blocco note), scegli Runtime, Cambia tipo di runtime, **GPU T4**, ed esegui le celle in ordine.
Alla fine il file `mycode-q4_k_m.gguf` finisce nel tuo Google Drive, nella cartella `MyCode`. Scaricalo, mettilo
in `finetune\mycode\` e fai doppio clic su `crea_mycode.bat`. Colab gratis ha limiti di tempo: se si
disconnette, riesegui le celle.

## 4. Usalo in MyDevAgent

```bat
mydevagent -p mycode
```

Oppure scrivi `MYDEVAGENT_PROFILE=mycode` nel file `.env` per usarlo sempre. Dentro MyDevAgent puoi anche
passare a MyCode con `/model mycode`. Se `mycode` non esiste ancora, MyDevAgent te lo dice e ti ricorda il
comando per crearlo: non prova a scaricarlo da internet, perché un modello con quel nome su ollama.com sarebbe di
qualcun altro.

## 5. Insegnargli nuovi file Markdown

Quando hai altri file `.md` da cui vuoi che impari, usa `md_to_model.py`. Il lavoro lo fa il modello che hai
in Ollama: legge i file a pezzi, aggiorna `MANUALE.md` (prima salva una copia `.bak.md`) e scrive nuove
conversazioni d'esempio in `data/generated.jsonl`.

```bat
.venv\Scripts\python.exe finetune\md_to_model.py C:\percorso\dei\nuovi\file
```

Puoi dargli file singoli o cartelle intere. Con un modello da 7B ci mette un po' e può essere lento su file
molto lunghi. Se lo interrompi con Ctrl+C, rilanciando lo stesso comando riprende da dove era arrivato, e i
file già studiati non li rifà. Poi rifai l'addestramento (punto 2): `generated.jsonl` viene usato insieme agli
esempi già presenti.

Gli esempi scritti da un modello piccolo sono meno precisi di quelli in `train.jsonl`: dai un'occhiata a
`data/generated.jsonl` e cancella le righe sbagliate prima di addestrare. `check_data.py` controlla il formato,
non se le risposte sono giuste.

Opzioni utili: `--model` per usare un altro modello di Ollama come insegnante (più grande è, meglio scrive),
`--esempi 12` per più conversazioni per pezzo, `--italiano 80` per più esempi in italiano, `--nuovo` per
riscrivere il manuale da zero invece di aggiornarlo.
