"""
Ponto de entrada do Jogo Musical (vertical slice).

Rodar SEMPRE como modulo, a partir da raiz do repositorio (mesma
convencao do CLI offline `python -m ouroboros.rhythm.offline.cli`) --
NUNCA como script solto (`python games/rhythm_game/main.py`), pois este
modulo usa imports absolutos (`from games.rhythm_game...`) que exigem a
raiz do repo em `sys.path`, o que so acontece automaticamente no modo
`-m`:

    python -m games.rhythm_game.main

Controles: setas para navegar o menu, ENTER para confirmar, A/S/W/D para
as 4 lanes durante uma musica, P para pausar/continuar, ESC volta pro
menu (ou sai do processo, se ja estiver nele).
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from games.rhythm_game.composition import build_menu_game

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_menu_game(config)
    game_loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
