"""Vio, la mascotte viola di MyDevAgent: pixel art disegnata con i mezzi blocchi (▀ ▄) del terminale.

Ogni carattere contiene due pixel (sopra e sotto), quindi lo sprite 14×12 occupa 14 colonne e 6 righe.
L'espressione cambia con la modalità (Shift+Tab), mentre lavora, a fine turno e quando la accarezzi (/vio).
"""

from __future__ import annotations

from rich.table import Table
from rich.text import Text

NAME = "Vio"
PURPLE = "#a855f7"
COLORS = {
    "P": PURPLE,  # corpo
    "D": "#6b21a8",  # ombre e zampe
    "L": "#d8b4fe",  # riflesso
    "K": "#1e1033",  # occhi e bocca
    "W": "#ffffff",  # luce negli occhi
    "C": "#f472b6",  # guance
    "Y": "#facc15",  # stelle
    "G": "#67e8f9",  # occhiali
    "R": "#f43f5e",  # cuore / errore
}

# righe 0-3 testa e orecchie, 4-5 occhi (variabili), 6-7 bocca (variabile), 8-11 corpo e zampe
HEAD = [
    ".D..........D.",
    ".DD........DD.",
    ".DPPPPPPPPPPD.",
    "DPLPPPPPPPPPPD",
]
EYES = {
    "open": ["DPPWKPPPPWKPPD", "DPPKKPPPPKKPPD"],
    "happy": ["DPPKKPPPPKKPPD", "DPKPPKPPKPPKPD"],
    "closed": ["DPPPPPPPPPPPPD", "DPKKKPPPPKKKPD"],
    "glasses": ["DGGGGGPPGGGGGD", "DGWKGGGGGWKGGD"],
    "stars": ["DPPYPPPPPPYPPD", "DPYYYPPPPYYYPD"],
    "look": ["DPPPWKPPPPWKPD", "DPPPKKPPPPKKPD"],
    "cross": ["DPKPKPPPPKPKPD", "DPPKPPPPPPKPPD"],
    "hearts": ["DPRPRPPPPRPRPD", "DPPRPPPPPPRPPD"],
}
MOUTHS = {
    "smile": ["DCCPPKPPKPPCCD", "DPPPPPKKPPPPPD"],
    "open": ["DCCPPKKKKPPCCD", "DPPPPPKKPPPPPD"],
    "flat": ["DCCPPPPPPPPCCD", "DPPPPKKKKPPPPD"],
    "sad": ["DCCPPPKKPPPCCD", "DPPPPKPPKPPPPD"],
}
BODY = [
    "DPPPPPPPPPPPPD",
    ".DPPPPPPPPPPD.",
    "..DDDDDDDDDD..",
    "..DD......DD..",
]
# nome → (occhi, bocca)
EXPRESSIONS = {
    "ask": ("open", "smile"),  # curiosa: chiede prima di toccare i file
    "auto-edit": ("happy", "open"),  # entusiasta: modifica da sola
    "plan": ("glasses", "flat"),  # studiosa: legge e pianifica, non tocca nulla
    "auto": ("stars", "open"),  # a razzo: fa tutto da sola
    "chat": ("look", "smile"),  # chiacchiera senza toccare i file
    "fast": ("happy", "open"),  # modalità del team: un solo agente, veloce
    "balanced": ("open", "smile"),
    "deep": ("glasses", "smile"),
    "ultra-deep": ("stars", "open"),
    "auto-team": ("look", "smile"),  # il router sceglie il team
    "think": ("look", "flat"),
    "blink": ("closed", "flat"),
    "done": ("happy", "smile"),
    "error": ("cross", "sad"),
    "love": ("hearts", "smile"),
}
SAYS = {
    "ask": "Ti chiedo conferma prima di ogni modifica.",
    "auto-edit": "Modifico i file da sola, per i comandi ti chiedo.",
    "plan": "Leggo e ti propongo un piano, senza toccare niente.",
    "auto": "Faccio tutto da sola, dentro questa cartella.",
    "chat": "Rispondo e basta: i file li salvi tu con /apply.",
    "fast": "Vado veloce: un solo agente.",
    "balanced": "Team standard: piano, modifiche, test e review.",
    "deep": "Team completo: sicurezza, performance, casi limite.",
    "ultra-deep": "35 agenti al lavoro: ci vorrà un po', ma ne vale la pena!",
    "auto-team": "Scelgo io il team giusto per ogni richiesta.",
    "done": "Fatto!",
    "error": "Qualcosa non va: guarda il messaggio qui sopra.",
    "love": "Grazie! ♥",
}
# faccine di una riga per la barra in basso e per l'indicatore di lavoro
FACES = {
    "ask": "(•ᴗ•)?", "auto-edit": "(^ᴗ^)", "plan": "(⌐■_■)", "auto": "(★ᴗ★)", "chat": "(•ᴗ•)",
    "done": "(^ᴗ^)", "error": "(×_×)", "love": "(♥ᴗ♥)",
}
PATS = ["Grazie! ♥", "Fusa in corso… ♥", "Pronta a programmare! ♥", "Ancora, ancora! ♥"]
THINK_FACES = ["(•_•)", "( •_•)", "(•_• )", "(-_-)", "(•_•)", "(•_•)ゞ"]


def sprite(expression: str = "ask") -> list[str]:
    eyes, mouth = EXPRESSIONS.get(expression, EXPRESSIONS["ask"])
    return HEAD + EYES[eyes] + MOUTHS[mouth] + BODY


def render(expression: str = "ask") -> Text:
    """Lo sprite come Text di rich: ogni carattere unisce due righe di pixel con ▀ / ▄."""
    rows = sprite(expression)
    out = Text()
    for top, bottom in zip(rows[0::2], rows[1::2], strict=True):
        for a, b in zip(top, bottom, strict=True):
            ca, cb = COLORS.get(a), COLORS.get(b)
            if ca and cb:
                out.append("▀", style=f"{ca} on {cb}")
            elif ca:
                out.append("▀", style=ca)
            elif cb:
                out.append("▄", style=cb)
            else:
                out.append(" ")
        out.append("\n")
    out.rstrip()
    return out


def card(expression: str, text: str | None = None, title: str = NAME) -> Table:
    """Vio con il fumetto accanto: usata quando cambi modalità e con /vio."""
    grid = Table.grid(padding=(0, 2))
    grid.add_column(no_wrap=True)
    grid.add_column(vertical="middle")
    bubble = Text()
    bubble.append(f"{title}\n", style=f"bold {PURPLE}")
    bubble.append(Text.from_markup(text if text is not None else SAYS.get(expression, "")))
    grid.add_row(render(expression), bubble)
    return grid


def face(expression: str) -> str:
    return FACES.get(expression, FACES["ask"])


def think_face(elapsed: float) -> str:
    return THINK_FACES[int(elapsed * 2) % len(THINK_FACES)]


if __name__ == "__main__":  # anteprima: python -m mydevagent.tui.mascot
    from rich.console import Console

    console = Console()
    for name in EXPRESSIONS:
        console.print(f"[bold]{name}[/]  {face(name)}")
        console.print(render(name))
