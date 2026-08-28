"""
Ponto de entrada do Jogo Roguelite (vertical slice).

Rodar SEMPRE como modulo, a partir da raiz do repositorio (mesma
convencao do Jogo Musical) -- NUNCA como script solto, pois este modulo
usa imports absolutos (`from games.roguelite...`) que exigem a raiz do
repo em `sys.path`, o que so acontece automaticamente no modo `-m`:

    python -m games.roguelite.main

Controles: WASD para mover, botao esquerdo do mouse para atirar, ESC para sair.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from games.roguelite.composition import build_game

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_game(config)
    game_loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
