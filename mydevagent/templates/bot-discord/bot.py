"""Bot Discord con due comandi: !ciao e !dado.

Il token del bot va nel file .env (copia .env.example): i passaggi sono in MYDEVAGENT.md.
Avvio: python bot.py  (prima: python -m pip install -r requirements.txt)
"""

import os
import random

import discord
from discord.ext import commands
from dotenv import load_dotenv

load_dotenv()
intents = discord.Intents.default()
intents.message_content = True  # serve per leggere i comandi che iniziano con !
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready() -> None:
    print(f"Collegato come {bot.user}")


@bot.command()
async def ciao(ctx: commands.Context) -> None:
    """Saluta chi scrive il comando."""
    await ctx.send(f"Ciao {ctx.author.display_name}! 👋")


@bot.command()
async def dado(ctx: commands.Context, facce: int = 6) -> None:
    """Tira un dado: !dado oppure !dado 20."""
    await ctx.send(f"🎲 È uscito {random.randint(1, max(2, facce))}")


if __name__ == "__main__":
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        raise SystemExit("Manca DISCORD_TOKEN: copia .env.example in .env e incolla il token del bot")
    bot.run(token)
