"""Il tuo programma Python. Avvialo con: python main.py"""


def saluta(nome: str) -> str:
    return f"Ciao, {nome}!"


def main() -> None:
    nome = input("Come ti chiami? ").strip() or "amico"
    print(saluta(nome))


if __name__ == "__main__":
    main()
