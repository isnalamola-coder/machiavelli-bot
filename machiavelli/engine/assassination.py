# machiavelli/engine/assassination.py


from ..game.game import Game


class AssassinationResolver:
    """Responsable de la gestión de los asesinatos."""

    def __init__(self, game: Game):
        self.game = game

    def run(self) -> None:
        """Ejecuta las órdenes de asesinato."""
        return
