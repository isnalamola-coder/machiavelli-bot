# machiavelli/discord.py
import asyncio
import logging
import os
import sqlite3
import traceback
from contextlib import closing
from datetime import datetime

import discord
from discord import app_commands

from machiavelli.engine import GameEngine
from machiavelli.engine.military import (
    DislodgementResolver,
    DislodgementResolverRequired,
    InvalidMilitaryState,
    MilitaryResolutionError,
    UnresolvedMilitaryConflict,
)
from machiavelli.game import (
    Command,
    DuplicatedGameException,
    Game,
    GameNotFoundException,
    Player,
    TooManyExpenses,
)
from machiavelli.scenario import Scenario
from machiavelli.tables import GameTables

logger = logging.getLogger(__name__)

# Estructura del documento (para orientarme)
# 1. Grupos de comandos
# 2. Inicializa los comandos
# 4. Comandos administrativos
# 5. Comandos de los jugadores


def format_error_with_location(e: Exception) -> str:
    """Extrae tipo, mensaje y localización de una excepción."""
    # Obtenemos la lista de marcos de la pila donde ocurrió la excepción
    tb_list = traceback.extract_tb(e.__traceback__)

    if tb_list:
        # Cogemos el último marco (donde saltó la excepción exactamente)
        last_frame = tb_list[-1]
        filename = os.path.basename(
            last_frame.filename
        )  # Solo el nombre del archivo (ej: discord.py)
        lineno = last_frame.lineno
        func_name = last_frame.name

        return (
            f"`{type(e).__name__}: {e}`\n"
            f"Ubicación: `{filename}:{lineno}` en `{func_name}()`"
        )

    return f"`{type(e).__name__}: {e}`"


# Grupo de comandos
game_group = app_commands.Group(
    name="mach", description="Comandos de las partidas de Machiavelli"
)

# Grupo de administración
admin_group = app_commands.Group(
    name="shar",
    description="Comandos de gestión interna para el Juez/Admin",
    default_permissions=discord.Permissions(administrator=True),
)

# Ruta por defecto
DB_PATH = os.getenv("DATABASE_PATH", "machiavelli.db")

game_group.db_path = DB_PATH
admin_group.db_path = DB_PATH


def init_game_commands(db_path: str) -> tuple[app_commands.Group, app_commands.Group]:
    """Configura la ruta de BBDD de ambos grupos de comandos."""
    game_group.db_path = db_path
    admin_group.db_path = db_path
    return game_group, admin_group


# Comandos administrativos
@admin_group.command(name="create", description="Crea una nueva partida en este canal")
@app_commands.describe(name="Nombre de la partida")
async def create(interaction: discord.Interaction, name: str):
    # Deferimos la respuesta para evitar el timeout de 3 segundos de Discord
    await interaction.response.defer(ephemeral=False)

    try:
        # Accedemos de forma segura a la propiedad del grupo.
        with sqlite3.connect(admin_group.db_path) as conn:
            game = Game.create_game(
                name=name, channel_id=interaction.channel_id, conn=conn
            )

        await interaction.followup.send(
            f"**¡Partida Creada!**\nSe ha creado la partida *'{game.name}'* "
            f"en el canal <#{interaction.channel_id}>.\n"
            f"ID de registro: `{game.database_id}`. ¡Que comience la diplomacia!"
        )

    except DuplicatedGameException as e:
        await interaction.followup.send(f"Error al crear partida: {e}")


@admin_group.command(
    name="add_player", description="Añade un jugador a la partida de este canal"
)
@app_commands.describe(
    discord_player="El usuario de Discord que vas a registrar",
    name="El nombre político o ID interno del jugador (ej: 'Francia' o 'Carlos')",
)
async def add_player(
    interaction: discord.Interaction, discord_player: discord.Member, name: str
):
    # Deferimos la respuesta para evitar el timeout de 3 segundos
    await interaction.response.defer(ephemeral=False)

    try:
        with sqlite3.connect(admin_group.db_path) as conn:
            # Carga el objeto Game utilizando el channel_id actual
            game = Game.load_game(conn, channel_id=interaction.channel_id)

            if any(p.discord_id == discord_player.id for p in game.players):
                await interaction.followup.send(
                    f"**Error:** El usuario {discord_player.mention} ya está "
                    "inscrito en esta partida."
                )
                return

            # Crea el Player con el nombre y usuario indicados.
            new_player = Player(
                game=game,
                player_id=name,
                discord_id=discord_player.id,
            )

            # Lo añade a la lista de la partida en memoria
            game.players.append(new_player)

            # Guardamos los datos del jugador
            new_player.save(conn)

        # Confirmación
        report = []
        for p in game.players:
            # Añadimos un fallback por si algún jugador antiguo no tuviera discord_id
            mention = f"<@{p.discord_id}>" if p.discord_id else "Sin usuario"
            report.append(f"- {p.player_id} {mention}")

        # Unimos todas las líneas con saltos de línea
        formatted_output = "\n".join(report)

        await interaction.followup.send(
            f"El jugador **'{name}'** (<@{discord_player.id}>) se ha unido "
            f"con éxito a la partida *'{game.name}'*.\n\n"
            f"Jugadores inscritos hasta ahora:\n{formatted_output}"
        )

    except GameNotFoundException:
        # Si no hay partida en este canal, avisamos limpiamente
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.\n"
            "Crea una primero usando `/sharcashvelli_admin create`."
        )

    except Exception as e:
        await interaction.followup.send(
            f"**Error inesperado:** `{type(e).__name__}: {e}`"
        )


@admin_group.command(
    name="remove_player", description="Elimina a un jugador de la partida de este canal"
)
@app_commands.describe(discord_user="El usuario de Discord que deseas eliminar")
async def remove_player(interaction: discord.Interaction, discord_user: discord.Member):
    await interaction.response.defer(ephemeral=False)

    try:
        with sqlite3.connect(admin_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)

            player = next(
                (p for p in game.players if p.discord_id == discord_user.id), None
            )

            if not player:
                await interaction.followup.send(
                    f"**Error:** El usuario {discord_user.mention} no está "
                    f"inscrito en la partida *'{game.name}'*."
                )
                return

            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM players WHERE game_id = ? AND discord_id = ?",
                (game.database_id, discord_user.id),
            )

            game.players.remove(player)

        if game.players:
            new_list = "\n".join(
                [f"- {p.player_id} (<@{p.discord_id}>)" for p in game.players]
            )
        else:
            new_list = "*No quedan jugadores inscritos en la partida.*"

        await interaction.followup.send(
            f"El jugador **'{player.player_id}'** ({discord_user.mention}) "
            f"ha sido eliminado con éxito de la partida *'{game.name}'*.\n\n"
            f"**Jugadores inscritos ahora:**\n{new_list}"
        )

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal."
        )
    except Exception as e:
        await interaction.followup.send(
            f"**Error inesperado:** `{type(e).__name__}: {e}`"
        )


@admin_group.command(
    name="set_scenario", description="Asigna un escenario a la partida de este canal"
)
@app_commands.describe(
    scenario_id="Elige uno de los escenarios disponibles en la lista"
)
async def set_scenario(interaction: discord.Interaction, scenario_id: str):
    await interaction.response.defer(ephemeral=False)

    try:
        # Cargamos los escenarios para poder sacar el nombre real en la confirmación
        escenarios_disponibles = Scenario.load_scenarios()

        if scenario_id not in escenarios_disponibles:
            await interaction.followup.send(
                "**Error:** El escenario seleccionado no es válido."
            )
            return

        escenario_elegido = escenarios_disponibles[scenario_id]

        with sqlite3.connect(admin_group.db_path) as conn:
            # Cargamos la partida actual por el canal
            game = Game.load_game(conn, channel_id=interaction.channel_id)

            # Le asignamos el ID del escenario elegido
            game.scenario_id = scenario_id

            # Guardamos la partida (como ya tiene ID, ejecutará el UPDATE)
            game.save(conn)

        await interaction.followup.send(
            f"**¡Escenario Configurado!**\nLa partida *'{game.name}'* "
            f"jugará al escenario: **{escenario_elegido.name}**."
        )

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal."
        )
    except Exception as e:
        await interaction.followup.send(
            f"**Error inesperado:** `{type(e).__name__}: {e}`"
        )


# Precarga de la lista de escenarios
@set_scenario.autocomplete("scenario_id")
async def set_scenario_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Genera sugerencias mientras el usuario escribe."""

    # Cargamos tu diccionario {str: Scenario}
    escenarios_disponibles = Scenario.load_scenarios()

    choices = []
    for s_id, scenario in escenarios_disponibles.items():
        # Filtramos por lo que el usuario esté escribiendo (ignorando mayúsculas)
        # Si no está escribiendo nada (current == ""), mostrará todos
        if current.lower() in scenario.name.lower() or current.lower() in s_id.lower():
            choices.append(
                app_commands.Choice(
                    name=scenario.name,  # Lo que ve el usuario en Discord
                    value=s_id,  # El código de escenario
                )
            )

    # Discord capa el Autocomplete a un máximo de 25 opciones en pantalla
    return choices[:25]


@admin_group.command(
    name="set_deadlines",
    description="Configura el horario semanal y el próximo deadline",
)
@app_commands.describe(
    dia_semanal="El día de la semana en que se procesarán los turnos de forma habitual",
    hora_semanal="La hora del deadline semanal (Formato HH:MM, ej: 22:00)",
    proximo_deadline=(
        "Fecha exacta del siguiente turno "
        "(Formato: DD/MM/AAAA HH:MM, ej: 22/07/2026 22:00)"
    ),
)
# Creamos un desplegable cerrado para los días de la semana
@app_commands.choices(
    dia_semanal=[
        app_commands.Choice(name="Lunes", value="Lunes"),
        app_commands.Choice(name="Martes", value="Martes"),
        app_commands.Choice(name="Miércoles", value="Miércoles"),
        app_commands.Choice(name="Jueves", value="Jueves"),
        app_commands.Choice(name="Viernes", value="Viernes"),
        app_commands.Choice(name="Sábado", value="Sábado"),
        app_commands.Choice(name="Domingo", value="Domingo"),
    ]
)
async def set_deadlines(
    interaction: discord.Interaction,
    dia_semanal: app_commands.Choice[str] = None,
    hora_semanal: str = None,
    proximo_deadline: str = None,
):
    await interaction.response.defer(ephemeral=False)

    try:
        with sqlite3.connect(admin_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)

            cambios = []

            # VALIDACIÓN DEL DEADLINE SEMANAL
            if dia_semanal or hora_semanal:
                # Si me dan el día, exijo la hora, y viceversa
                if not (dia_semanal and hora_semanal):
                    await interaction.followup.send(
                        "**Error:** Para fijar el horario semanal debes indicar "
                        "tanto el día como la hora."
                    )
                    return

                # Validamos que la hora tenga un formato HH:MM correcto
                try:
                    datetime.strptime(hora_semanal, "%H:%M")
                except ValueError:
                    await interaction.followup.send(
                        "**Error:** La hora semanal debe tener el formato "
                        "`HH:MM` (ej: `22:00` o `09:30`)."
                    )
                    return

                game.weekly_deadline = f"{dia_semanal.value} a las {hora_semanal}"
                cambios.append(f"**Horario semanal:** {game.weekly_deadline}")

            # VALIDACIÓN DEL PRÓXIMO DEADLINE ESPECÍFICO
            if proximo_deadline:
                try:
                    # Parseamos el formato natural DD/MM/AAAA HH:MM.
                    fecha_parsed = datetime.strptime(proximo_deadline, "%d/%m/%Y %H:%M")

                    # Lo guardamos en formato ISO (AAAA-MM-DD HH:MM) para la BBDD
                    game.next_deadline = fecha_parsed.strftime("%Y-%m-%d %H:%M")

                    # Para el mensaje usamos un formato legible.
                    fecha_bonita = fecha_parsed.strftime("%A, %d de %B a las %H:%M")
                    cambios.append(f"**Próximo Deadline:** `{fecha_bonita}`")
                except ValueError:
                    await interaction.followup.send(
                        "**Error:** El formato del próximo deadline es incorrecto.\n"
                        "Debe ser estrictamente: `DD/MM/AAAA HH:MM` "
                        "(ej: `22/07/2026 22:00`)."
                    )
                    return

            # GUARDADO (Si se ha configurado algo)
            if not cambios:
                await interaction.followup.send(
                    "No has introducido ningún parámetro para modificar."
                )
                return

            game.save(conn)

        # Generamos una respuesta elegante listando lo que ha cambiado
        resumen = "\n".join(cambios)
        await interaction.followup.send(
            f"**¡Plazos Actualizados!**\nSe han guardado los nuevos plazos "
            f"para la partida *'{game.name}'*:\n{resumen}"
        )

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal."
        )
    except Exception as e:
        await interaction.followup.send(
            f"**Error inesperado:** `{type(e).__name__}: {e}`"
        )


def _execute_game_turn(
    db_path: str,
    channel_id: int,
    *,
    dislodgement_resolver: DislodgementResolver | None = None,
) -> tuple[str, ...]:
    """Ejecuta la transacción síncrona completa dentro del worker."""
    # La conexión y el estado mutable no salen del hilo de trabajo.
    with closing(sqlite3.connect(db_path)) as conn:
        with conn:
            game = Game.load_game(conn, channel_id=channel_id)
            engine = GameEngine(
                game,
                dislodgement_resolver=dislodgement_resolver,
            )
            engine.run()
            report = tuple(game.turn_report())
            game.save(conn)
    return report


def _military_error_message(error: MilitaryResolutionError) -> str:
    """Traduce errores militares a orientación pública sin detalles internos."""
    prefix = "No se pudo resolver la fase militar; no se aplicó ningún cambio."
    if isinstance(error, InvalidMilitaryState):
        guidance = (
            " Revisa que no haya unidades duplicadas ni ocupaciones incompatibles "
            "antes de reintentar."
        )
    elif isinstance(error, UnresolvedMilitaryConflict):
        guidance = (
            " Revisa las órdenes y, si el problema se repite con las mismas entradas, "
            "comunícalo al administrador."
        )
    elif isinstance(error, DislodgementResolverRequired):
        guidance = " Activa la gestión de retiradas antes de reintentar."
    else:
        guidance = " Reintenta el turno y comunica el fallo si persiste."
    return prefix + guidance


@admin_group.command(
    name="run_game", description="Ejecuta y procesa el turno actual de la partida"
)
async def run_game(interaction: discord.Interaction):
    """Ejecuta un turno fuera del event loop y publica solo el resultado seguro."""
    await interaction.response.defer(ephemeral=True)

    try:
        # SQLite, motor y guardado se ejecutan juntos para no bloquear Discord.
        report = await asyncio.to_thread(
            _execute_game_turn,
            admin_group.db_path,
            interaction.channel_id,
        )
    except GameNotFoundException:
        await interaction.edit_original_response(
            content=(
                "**Error:** No hay ninguna partida activa en este canal para poder "
                "ejecutarla."
            )
        )
        return
    except MilitaryResolutionError as error:
        # El diagnóstico completo queda en logs; el usuario recibe orientación segura.
        logger.exception(
            "La fase militar abortó sin commit",
            extra={"cycle_diagnostic": getattr(error, "diagnostic", None)},
        )
        await interaction.edit_original_response(
            content=_military_error_message(error)
        )
        return
    except Exception as error:
        error_detallado = format_error_with_location(error)
        await interaction.edit_original_response(
            content=f"**Error inesperado al ejecutar el turno:** {error_detallado}."
        )
        return

    # Al completar el turno, la respuesta efímera se sustituye por el informe público.
    await interaction.delete_original_response()
    if not report:
        await interaction.followup.send(
            "El turno se ha procesado, pero no se ha generado ninguna "
            "línea de reporte.",
            ephemeral=False,
        )
        return

    current_message = ""
    # Se conserva el orden del informe y se deja margen respecto al límite de Discord.
    for line in report:
        if len(current_message) + len(line) + 1 > 1950:
            await interaction.followup.send(current_message, ephemeral=False)
            current_message = line
        else:
            current_message = (
                f"{current_message}\n{line}" if current_message else line
            )

    if current_message:
        await interaction.followup.send(current_message, ephemeral=False)


# 5. Comandos de los jugadores


@game_group.command(
    name="game_status",
    description="Muestra el estado actual de la partida en este canal",
)
async def game_status(interaction: discord.Interaction):
    # La lectura y preparación del estado puede tardar.
    await interaction.response.defer(ephemeral=False)

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            # Cargamos la partida usando el canal actual
            game = Game.load_game(conn, channel_id=interaction.channel_id)

            # Llamamos a tu función interna que genera las líneas del reporte
            lineas_reporte = game.report_status()

            # Unimos todas las líneas devueltas con saltos de línea
            # Ponemos un fallback por si acaso la lista viniera vacía
            mensaje_status = (
                "\n".join(lineas_reporte)
                if lineas_reporte
                else "No hay datos de estado disponibles."
            )

        # Enviamos el reporte maquetado al canal
        await interaction.followup.send(mensaje_status)

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.\n"
            "Crea una primero usando `/sharcashvelli_admin create`."
        )
    except Exception as e:
        await interaction.followup.send(
            f"**Error inesperado:** `{type(e).__name__}: {e}`"
        )


@game_group.command(
    name="game_report", description="Muestra el informe del último turno jugado"
)
async def game_report(interaction: discord.Interaction):
    # La lectura y preparación del informe puede tardar.
    await interaction.response.defer(ephemeral=True)

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            # Cargamos la partida usando el canal actual
            game = Game.load_game(conn, channel_id=interaction.channel_id)

        report = game.turn_report()

        current_message = ""

        for line in report:
            # Conservamos margen respecto al límite de Discord.
            if len(current_message) + len(line) + 1 > 1950:
                # Enviamos lo acumulado y abrimos un bloque nuevo.
                await interaction.followup.send(current_message, ephemeral=True)
                current_message = line
            else:
                # Si cabe, la acumulamos separada por un salto de línea.
                if current_message:
                    current_message += f"\n{line}"
                else:
                    current_message = line

        # Enviamos el último bloque que haya quedado rezagado en el bucle
        if current_message:
            await interaction.followup.send(current_message, ephemeral=True)

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.",
            ephemeral=True,
        )
    except Exception as e:
        await interaction.followup.send(
            "**Error inesperado al mostrar el informe:** "
            f"`{type(e).__name__}: {e}`.",
            ephemeral=True,
        )


@game_group.command(
    name="cmdlist", description="Muestra la lista de tus órdenes registradas"
)
async def cmdlist(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = next(
                (p for p in game.players if p.discord_id == interaction.user.id),
                None,
            )

            if not player:
                await interaction.followup.send(
                    "**Error:** No estás inscrito en la partida de este canal.",
                    ephemeral=True,
                )
                return

            # Recupera las órdenes
            commands = [str(c) for c in player.commands]

            if not commands:
                await interaction.followup.send(
                    f"**No hay comandos para {player.player_id}:**",
                    ephemeral=True,
                )
                return

            lines = "\n".join([f"**{i + 1}.** `{o}`" for i, o in enumerate(commands)])

            await interaction.followup.send(
                f"**Comandos actuales para {player.player_id}:**\n{lines}",
                ephemeral=True,
            )

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.",
            ephemeral=True,
        )
    except Exception as e:
        errormsg = format_error_with_location(e)
        await interaction.followup.send(
            # f"**Error inesperado:** `{type(e).__name__}: {e}`", ephemeral=True
            f"**Error inesperado:** `{errormsg}`",
            ephemeral=True,
        )


# ==============================================================================
# send commands
# ==============================================================================

# first, autocomplete


def _resolve_player(game: Game, interaction: discord.Interaction) -> Player | None:
    """Resuelve el jugador por potencia administrativa o ID de Discord."""
    selected_power = getattr(interaction.namespace, "power", None)

    # Modo administrador
    if selected_power:
        # Buscamos por el código de la potencia
        return next((p for p in game.players if p.power == selected_power), None)

    # Modo Jugador. Buscamos por la cuenta de Discord
    return next((p for p in game.players if p.discord_id == interaction.user.id), None)


async def cmd_actor_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Actores disponibles para el jugador actual."""
    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = _resolve_player(game, interaction)

            if not player:
                return []

            # Actores disponibles
            actors = player.cmd_available_actors()

            choices = []
            for code, label in actors:
                if current.lower() in label.lower() or current.lower() in code.lower():
                    choices.append(app_commands.Choice(name=label, value=code))

            return choices[:25]
    except Exception:
        return []


async def cmd_command_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Sugiere las órdenes válidas según el actor seleccionado previamente."""
    # Leemos el valor que el usuario ha seleccionado/escrito en el campo 'actor'
    actor = getattr(interaction.namespace, "actor", None)

    if not actor:
        return [app_commands.Choice(name="Selecciona primero un actor", value="")]

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = _resolve_player(game, interaction)

            # Comandos disponibles
            commands = player.cmd_available_commands(actor)

            choices = []
            for code, label in commands:
                if current.lower() in label.lower() or current.lower() in code.lower():
                    choices.append(app_commands.Choice(name=label, value=code))

            return choices[:25]
    except Exception:
        return []


async def cmd_target_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Sugiere los objetivos válidos según el actor y el comando seleccionados."""
    actor = getattr(interaction.namespace, "actor", None)
    command = getattr(interaction.namespace, "command", None)

    if not actor or not command:
        return [
            app_commands.Choice(name="Selecciona primero actor y comando", value="")
        ]

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = _resolve_player(game, interaction)

            # Targets disponibles
            targets = player.cmd_available_targets(actor, command)

            choices = []
            for code, label in targets:
                if current.lower() in label.lower() or current.lower() in code.lower():
                    choices.append(app_commands.Choice(name=label, value=code))

            return choices[:25]
    except Exception:
        return []


async def exp_expense_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Gastos disponibles para el jugador actual."""
    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = _resolve_player(game, interaction)

            if not player:
                return []

            # Actores disponibles
            expenses = player.exp_available_expenses()

            choices = []
            for code, label in expenses:
                if current.lower() in label.lower() or current.lower() in code.lower():
                    choices.append(app_commands.Choice(name=label, value=code))

            return choices[:25]
    except Exception:
        return []


async def exp_target_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Sugiere los objetivos disponibles para el gasto seleccionado previamente."""
    # Leemos el valor que el usuario ha seleccionado/escrito en el campo 'expense'
    expense = getattr(interaction.namespace, "expense", None)

    if not expense:
        return [app_commands.Choice(name="Selecciona primero un gasto", value="")]

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = _resolve_player(game, interaction)

            # Comandos disponibles
            targets = player.exp_available_targets(expense)

            choices = []
            for code, label in targets:
                if current.lower() in label.lower() or current.lower() in code.lower():
                    choices.append(app_commands.Choice(name=label, value=code))

            choices.sort(key=lambda choice: choice.name)
            return choices[:25]
    except Exception:
        return []


async def exp_amount_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Sugiere los objetivos válidos según el gasto y objetivo seleccionados."""
    expense = getattr(interaction.namespace, "expense", None)
    target = getattr(interaction.namespace, "target", None)

    if not expense or not target:
        return [
            app_commands.Choice(name="Selecciona primero gasto y objetivo", value="")
        ]

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = _resolve_player(game, interaction)

            # Targets disponibles
            amounts = player.exp_available_amounts(expense, target)

            choices = []
            for code, label in amounts:
                if current.lower() in label.lower() or current.lower() in code.lower():
                    choices.append(app_commands.Choice(name=label, value=code))

            return choices[:25]
    except Exception:
        return []


# ==============================================================================
# COMANDO /mach cmd
# ==============================================================================


@game_group.command(
    name="cmd", description="Registra una nueva orden para tus unidades"
)
@app_commands.describe(
    actor="Unidad o recurso que ejecutará la acción",
    command="Acción u orden a realizar",
    target="Objetivo de la orden (Provincia, ciudad, unidad, facción, etc)",
)
@app_commands.autocomplete(
    actor=cmd_actor_autocomplete,
    command=cmd_command_autocomplete,
    target=cmd_target_autocomplete,
)
async def cmd(
    interaction: discord.Interaction, actor: str, command: str, target: str = None
):
    await interaction.response.defer(ephemeral=True)

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = next(
                (p for p in game.players if p.discord_id == interaction.user.id), None
            )

            if not player:
                await interaction.followup.send(
                    "**Error:** No se identificó al jugador.", ephemeral=True
                )
                return

            valid_actor = [code for code, _ in player.cmd_available_actors()]
            if actor not in valid_actor:
                await interaction.followup.send(
                    f"**Error:** `{actor}` no es un actor válido.",
                    ephemeral=True,
                )
                return

            valid_command = [code for code, _ in player.cmd_available_commands(actor)]
            if command not in valid_command:
                await interaction.followup.send(
                    f"**Error:** `{command}` no es una orden válida.",
                    ephemeral=True,
                )
                return

            valid_target = [
                code for code, _ in player.cmd_available_targets(actor, command)
            ]
            if valid_target and valid_target[0] != "" and target not in valid_target:
                await interaction.followup.send(
                    f"**Error:** `{target}` no es un objetivo válido.",
                    ephemeral=True,
                )
                return

            cmd = Command(game, player, actor, command, target)
            lines = player.cmd_add_command(cmd)

            player.save(conn)

        report = "\n".join(lines)

        await interaction.followup.send(report, ephemeral=True)

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.", ephemeral=True
        )
    except Exception as e:
        error_detallado = format_error_with_location(e)
        await interaction.followup.send(
            f"**Error inesperado:** {error_detallado}", ephemeral=True
        )


# ==============================================================================
# COMANDO /shar cmd_user
# ==============================================================================
async def cmd_power_autocomplete(
    interaction: discord.Interaction, current: str
) -> list[app_commands.Choice[str]]:
    """Sugiere las potencias/jugadores presentes en la partida actual."""
    try:
        with sqlite3.connect(admin_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)

            # Obtenemos los códigos de las potencias en juego
            active_powers = {p.power for p in game.players}

            choices = []
            for code, name in GameTables.powers.items():
                if code in active_powers:
                    label = f"{name}"
                    choices.append(app_commands.Choice(name=label, value=code))

            return choices[:25]
    except Exception:
        return []


@admin_group.command(
    name="cmd_user", description="Registra una orden en nombre de un jugador"
)
@app_commands.describe(
    power="Código de la potencia/jugador a quien pertenece la orden",
    actor="Unidad o recurso que ejecutará la acción",
    command="Acción u orden a realizar",
    target="Objetivo de la orden (Provincia, ciudad, unidad, facción, etc)",
)
@app_commands.autocomplete(
    power=cmd_power_autocomplete,
    actor=cmd_actor_autocomplete,
    command=cmd_command_autocomplete,
    target=cmd_target_autocomplete,
)
async def cmd_user(
    interaction: discord.Interaction,
    power: str,
    actor: str,
    command: str,
    target: str = None,
):
    await interaction.response.defer(ephemeral=True)

    try:
        with sqlite3.connect(admin_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            # Buscamos al jugador por su código de potencia.
            player = next((p for p in game.players if p.power == power), None)

            if not player:
                await interaction.followup.send(
                    f"**Error:** No se encontró la potencia `{power}` en la partida.",
                    ephemeral=True,
                )
                return

            valid_actor = [code for code, _ in player.cmd_available_actors()]
            if actor not in valid_actor:
                await interaction.followup.send(
                    f"**Error:** `{actor}` no es un actor válido.",
                    ephemeral=True,
                )
                return

            valid_command = [code for code, _ in player.cmd_available_commands(actor)]
            if command not in valid_command:
                await interaction.followup.send(
                    f"**Error:** `{command}` no es una orden válida.",
                    ephemeral=True,
                )
                return

            valid_target = [
                code for code, _ in player.cmd_available_targets(actor, command)
            ]
            if valid_target and valid_target[0] != "" and target not in valid_target:
                await interaction.followup.send(
                    f"**Error:** `{target}` no es un objetivo válido.",
                    ephemeral=True,
                )
                return

            cmd_obj = Command(game, player, actor, command, target)
            lines = player.cmd_add_command(cmd_obj)

            player.save(conn)

        report = "\n".join(lines)

        await interaction.followup.send(f"{report}", ephemeral=True)

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.", ephemeral=True
        )
    except Exception as e:
        error_detallado = format_error_with_location(e)
        await interaction.followup.send(
            f"**Error inesperado:** {error_detallado}", ephemeral=True
        )


# ==============================================================================
# COMANDO /mach expense
# ==============================================================================


@game_group.command(name="expense", description="Registra un nuevo gasto")
@app_commands.describe(
    expense="Tipo de gasto a realizar",
    target="Objetivo del gasto (Provincia, ciudad, unidad, facción, etc)",
    amount="Cantidad destinada al gasto",
)
@app_commands.autocomplete(
    expense=exp_expense_autocomplete,
    target=exp_target_autocomplete,
    amount=exp_amount_autocomplete,
)
async def expense(
    interaction: discord.Interaction, expense: str, target: str, amount: str
):
    await interaction.response.defer(ephemeral=True)

    try:
        with sqlite3.connect(game_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            player = next(
                (p for p in game.players if p.discord_id == interaction.user.id), None
            )

            if not player:
                await interaction.followup.send(
                    "**Error:** No se identificó al jugador.", ephemeral=True
                )
                return

            valid_expense = [code for code, _ in player.exp_available_expenses()]
            if expense not in valid_expense:
                await interaction.followup.send(
                    f"**Error:** `{expense}` no es un gasto válido.",
                    ephemeral=True,
                )
                return

            valid_target = [code for code, _ in player.exp_available_targets(expense)]
            if target not in valid_target:
                await interaction.followup.send(
                    f"**Error:** `{target}` no es un objetivo válido.",
                    ephemeral=True,
                )
                return

            valid_amount = [
                code for code, _ in player.exp_available_amounts(expense, target)
            ]
            if amount not in valid_amount:
                await interaction.followup.send(
                    f"**Error:** `{amount}` no es una cantidad válida.",
                    ephemeral=True,
                )
                return

            cmd = Command(game, player, actor=expense, target=target, command=amount)
            lines = player.cmd_add_command(cmd)

            player.save(conn)

        report = "\n".join(lines)

        await interaction.followup.send(report, ephemeral=True)

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.", ephemeral=True
        )
    except TooManyExpenses:
        report = [f"Orden `{cmd}` enviada."]
        report.append("**Error:** Superado el límite de gastos.")
        report.append("**Órdenes recibidas hasta ahora:**")
        for c in player.commands:
            report.append(f"`{c}`")
        await interaction.followup.send("\n".join(report), ephemeral=True)
    except Exception as e:
        error_detallado = format_error_with_location(e)
        await interaction.followup.send(
            f"**Error inesperado:** {error_detallado}", ephemeral=True
        )


@admin_group.command(
    name="expense_user", description="Registra un gasto en nombre de un jugador"
)
@app_commands.describe(
    power="Código de la potencia/jugador a quien pertenece el gasto",
    expense="Tipo de gasto a realizar",
    target="Objetivo del gasto (Provincia, ciudad, unidad, facción, etc)",
    amount="Cantidad destinada al gasto",
)
@app_commands.autocomplete(
    power=cmd_power_autocomplete,
    expense=exp_expense_autocomplete,
    target=exp_target_autocomplete,
    amount=exp_amount_autocomplete,
)
async def expense_user(
    interaction: discord.Interaction, power: str, expense: str, target: str, amount: str
):
    await interaction.response.defer(ephemeral=True)

    try:
        with sqlite3.connect(admin_group.db_path) as conn:
            game = Game.load_game(conn, channel_id=interaction.channel_id)
            # Buscamos al jugador por su código de potencia.
            player = next((p for p in game.players if p.power == power), None)

            if not player:
                await interaction.followup.send(
                    f"**Error:** No se encontró la potencia `{power}` en la partida.",
                    ephemeral=True,
                )
                return

            valid_expense = [code for code, _ in player.exp_available_expenses()]
            if expense not in valid_expense:
                await interaction.followup.send(
                    f"**Error:** `{expense}` no es un gasto válido.",
                    ephemeral=True,
                )
                return

            valid_target = [code for code, _ in player.exp_available_targets(expense)]
            if target not in valid_target:
                await interaction.followup.send(
                    f"**Error:** `{target}` no es un objetivo válido.",
                    ephemeral=True,
                )
                return

            valid_amount = [
                code for code, _ in player.exp_available_amounts(expense, target)
            ]
            if amount not in valid_amount:
                await interaction.followup.send(
                    f"**Error:** `{amount}` no es una cantidad válida.",
                    ephemeral=True,
                )
                return

            cmd = Command(game, player, actor=expense, target=target, command=amount)
            lines = player.cmd_add_command(cmd)

            player.save(conn)

        report = "\n".join(lines)

        await interaction.followup.send(report, ephemeral=True)

    except GameNotFoundException:
        await interaction.followup.send(
            "**Error:** No hay ninguna partida activa en este canal.", ephemeral=True
        )
    except TooManyExpenses:
        report = [f"Orden `{cmd}` enviada."]
        report.append("**Error:** Superado el límite de gastos.")
        report.append("**Órdenes recibidas hasta ahora:**")
        for c in player.commands:
            report.append(f"`{c}`")
        await interaction.followup.send("\n".join(report), ephemeral=True)
    except Exception as e:
        error_detallado = format_error_with_location(e)
        await interaction.followup.send(
            f"**Error inesperado:** {error_detallado}", ephemeral=True
        )
