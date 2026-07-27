import os
import io
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import database
import random

load_dotenv()

from machiavelli.database import upgrade
from machiavelli.discord import init_game_commands

# Cargar variables de entorno
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

# La base de datos
DB_PATH = os.getenv("DATABASE_PATH", "machiavelli.db")

# Ejecutamos las migraciones
upgrade(DB_PATH)

# Configurar intents
intents = discord.Intents.default()
intents.message_content = True

# Inicializar bot
bot = commands.Bot(command_prefix='!', intents=intents)

# --- COMANDO DE SINCRONIZACIÓN MANUAL ---
@bot.command(name='sync')
@commands.is_owner()
async def sync_commands(ctx, modo: str | None = None):
    """Sincroniza los slash commands bajo demanda (Solo Dueño del Bot)
    
    Uso:
        !sync        -> Sincroniza en ESTE servidor (Instantáneo)
        !sync global -> Sincroniza en TODO Discord (Tarda unos minutos/hora)"""
    if modo == "global":
        await ctx.send("🌍 Sincronizando comandos GLOBALMENTE (puede tardar en aparecer)...")
        try:
            synced = await bot.tree.sync()
            await ctx.send(f"✅ Éxito: Sincronizados {len(synced)} comandos globalmente.")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")
    else:
        await ctx.send("🏠 Sincronizando comandos en este servidor específico...")
        try:
            # Clona los comandos que tenemos en memoria dentro de este servidor concreto
            bot.tree.copy_global_to(guild=ctx.guild)
            # Sincroniza solo este servidor
            synced = await bot.tree.sync(guild=ctx.guild)
            await ctx.send(f"✅ Éxito: Sincronizados {len(synced)} comandos en este servidor al instante.")
        except Exception as e:
            await ctx.send(f"❌ Error local: {e}")

@bot.event
async def on_ready():
    print(f'Bot conectado como {bot.user}')
    
    # La base de datos antigua, por si todavía me hace falta
    database.init_db()

    # Los nuevos comandos
    mach_group, shar_group = init_game_commands(DB_PATH)
    if not bot.tree.get_command("mach"):
        bot.tree.add_command(mach_group)
        print("Grupo 'mach' registrado en memoria local.")
        
    if not bot.tree.get_command("shar"):
        bot.tree.add_command(shar_group)
        print("Grupo 'shar' registrado en memoria local.")

@bot.event
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        await interaction.response.send_message("⛔ Canal o permisos no autorizados.", ephemeral=True)
    else:
        print(f"Error: {error}")
        await interaction.response.send_message("❌ Error interno.", ephemeral=True)

if __name__ == '__main__':
    if not TOKEN or TOKEN == "tu_token_aqui":
        print("⚠️ ADVERTENCIA: Por favor, configura tu DISCORD_TOKEN en el archivo .env antes de iniciar el bot.")
    else:
        bot.run(TOKEN)
