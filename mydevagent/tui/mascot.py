"""Vio, il polpetto viola di MyDevAgent (tanti tentacoli, come i suoi agenti).

Pixel art 14×8 disegnata con i mezzi blocchi (▀ ▄): ogni carattere contiene due pixel, quindi Vio occupa
14 colonne e 4 righe. Sta sopra la barra dove scrivi: cambia espressione con la modalità (Shift+Tab),
muove i tentacoli, sbatte le palpebre, sorride a fine lavoro, fa gli occhi a X sugli errori e i cuori con /vio.
"""

from __future__ import annotations

from rich.text import Text

NAME = "Vio"
PURPLE = "#a855f7"
COLORS = {
    "P": PURPLE,  # corpo
    "D": "#581c87",  # contorno e tentacoli
    "L": "#d8b4fe",  # riflesso
    "K": "#1a0b2e",  # occhi e bocca
    "W": "#ffffff",  # luce negli occhi
    "C": "#f472b6",  # guance e cuori
    "Y": "#facc15",  # occhi a stella
    "B": "#67e8f9",  # occhiali
    "R": "#f43f5e",  # errore
}

HEAD = [".....DDDD.....", "...DDPPPPDD...", "..DPLPPPPPPD.."]
EYES = {
    "open": [".DPPWKPPWKPPD.", ".DPPKKPPKKPPD."],
    "happy": [".DPPKPPPPKPPD.", ".DPKPKPPKPKPD."],
    "closed": [".DPPPPPPPPPPD.", ".DPKKKPPKKKPD."],
    "look": [".DPPPWKPPWKPD.", ".DPPPKKPPKKPD."],
    "glasses": [".DPBBBPPBBBPD.", ".DPBWKBBWKBPD."],
    "stars": [".DPPYWPPYWPPD.", ".DPPYYPPYYPPD."],
    "cross": [".DPRPRPPRPRPD.", ".DPPRPPPPRPPD."],
    "hearts": [".DPCPCPPCPCPD.", ".DPPCPPPPCPPD."],
}
MOUTHS = {
    "smile": ".DPCPPKKPPCPD.",
    "open": ".DPCPKKKKPCPD.",
    "flat": ".DPCPPDDPPCPD.",
}
TENTACLES = [  # due pose: si alternano per farli ondeggiare
    ["DPDPDPPPPDPDPD", "D.P.P.DD.P.P.D"],
    ["DPDPDPPPPDPDPD", ".D.P.PDDP.P.D."],
]
# nome → (occhi, bocca)
EXPRESSIONS = {
    "ask": ("open", "smile"),  # curiosa: chiede prima di toccare i file
    "auto-edit": ("happy", "open"),  # entusiasta: modifica da sola
    "plan": ("glasses", "flat"),  # studiosa: legge e pianifica
    "auto": ("stars", "open"),  # a tutto gas
    "chat": ("look", "smile"),  # chiacchiera
    "fast": ("happy", "smile"),
    "balanced": ("open", "smile"),
    "deep": ("glasses", "smile"),
    "ultra-deep": ("stars", "smile"),
    "auto-team": ("look", "smile"),
    "think": ("look", "flat"),
    "blink": ("closed", "smile"),
    "done": ("happy", "smile"),
    "error": ("cross", "flat"),
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
    "ultra-deep": "35 agenti al lavoro: lento, ma per i lavori importanti.",
    "auto-team": "Scelgo io il team giusto per ogni richiesta.",
}
PATS = ["Grazie! ♥", "Fusa da polpo in corso… ♥", "Otto tentacoli pronti a programmare! ♥", "Ancora, ancora! ♥"]
THINK_FACES = ["(•_•)", "( •_•)", "(•_• )", "(-_-)", "(•_•)", "(•_•)ゞ"]
WIDTH = 14


def sprite(expression: str = "ask", frame: int = 0) -> list[str]:
    eyes, mouth = EXPRESSIONS.get(expression, EXPRESSIONS["ask"])
    return HEAD + EYES[eyes] + [MOUTHS[mouth]] + TENTACLES[frame % len(TENTACLES)]


def cells(expression: str = "ask", frame: int = 0) -> list[list[tuple[str, str | None, str | None]]]:
    """Righe di (carattere, colore primo piano, colore sfondo): due pixel per carattere."""
    rows = sprite(expression, frame)
    out = []
    for top, bottom in zip(rows[0::2], rows[1::2], strict=True):
        line = []
        for a, b in zip(top, bottom, strict=True):
            ca, cb = COLORS.get(a), COLORS.get(b)
            if ca:
                line.append(("▀", ca, cb))
            elif cb:
                line.append(("▄", cb, None))
            else:
                line.append((" ", None, None))
        out.append(line)
    return out


def render(expression: str = "ask", frame: int = 0) -> Text:
    """Per rich (anteprima e test)."""
    out = Text()
    for line in cells(expression, frame):
        for char, fg, bg in line:
            out.append(char, style=f"{fg} on {bg}" if bg else (fg or ""))
        out.append("\n")
    out.rstrip()
    return out


def fragments(expression: str = "ask", frame: int = 0) -> list[list[tuple[str, str]]]:
    """Per prompt_toolkit: una lista di frammenti (stile, testo) per ogni riga."""
    return [[(f"fg:{fg}" + (f" bg:{bg}" if bg else ""), char) if fg else ("", char) for char, fg, bg in line]
            for line in cells(expression, frame)]


def think_face(elapsed: float) -> str:
    return THINK_FACES[int(elapsed * 2) % len(THINK_FACES)]


if __name__ == "__main__":  # anteprima: python -m mydevagent.tui.mascot
    from rich.console import Console

    console = Console()
    for name in EXPRESSIONS:
        console.print(f"[bold]{name}[/]")
        console.print(render(name))
