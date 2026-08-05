"""Public presentation of the current game status."""

from __future__ import annotations

from machiavelli.game.game import Game


class GameStatusReporter:
    """Render game status without placing channel formatting in the domain."""

    @staticmethod
    def generate(game: Game) -> list[str]:
        """Return the current public game status as Discord-ready lines."""
        report = [f"## __**Partida**: {game.name}__"]
        report.append(
            f"**Escenario:** {game.scenario.name if game.scenario else 'Por definir'}."
        )
        report.append(
            f"**Horario de los turnos:** {game.weekly_deadline or 'Por definir'}."
        )

        if game.turn_number == 0:
            report.append("### __**Estado:** Por comenzar.__")
            if game.players:
                players = ", ".join(
                    f"<@{player.discord_id}> ({player.player_id})"
                    for player in game.players
                )
                if game.scenario:
                    report.append(
                        f"**Jugadores {len(game.players)}/"
                        f"{len(game.scenario.powers)}:** {players}"
                    )
                else:
                    report.append(f"**Jugadores {len(game.players)}:** {players}")
            else:
                report.append("**Jugadores:** Ninguno")
        else:
            if game.scenario is None:
                raise ValueError("Una partida iniciada debe tener escenario")
            year = (game.turn_number - 1) // 4 + game.scenario.year
            season = (
                "Primavera (mantenimiento)",
                "Primavera (campaña)",
                "Verano",
                "Otoño",
            )[(game.turn_number - 1) % 4]
            report.append(f"### __**Estado:** {season} de {year}__")
            report.append("**Han enviado sus órdenes:**")
            ordered_players = [player for player in game.players if player.commands]
            if ordered_players:
                report.extend(
                    f"- <@{player.discord_id}> ({player.player_id})"
                    for player in ordered_players
                )
            else:
                report.append("- Nadie :wink:.")

        report.append(f"**Próximo turno:** {game.next_deadline or 'Por definir'}.")
        return report
