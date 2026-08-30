"""
Ponto de entrada do Platformer (vertical slice, ROADMAP M12).

Rodar SEMPRE como modulo, a partir da raiz do repositorio (mesma
convencao do Roguelite/Jogo Musical) -- NUNCA como script solto, pois
este modulo usa imports absolutos (`from games.platformer...`) que
exigem a raiz do repo em `sys.path`, o que so acontece automaticamente
no modo `-m`:

    python -m games.platformer.main

Controles: A/D para correr, ESPACO para pular (so funciona no chao), ESC para sair.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from games.platformer.composition import build_game

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_game(config)
    game_loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
