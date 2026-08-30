"""
Ponto de entrada do Tactics (vertical slice, ROADMAP M13).

Rodar SEMPRE como modulo, a partir da raiz do repositorio (mesma
convencao do Roguelite/Jogo Musical/Platformer) -- NUNCA como script
solto, pois este modulo usa imports absolutos (`from games.tactics...`)
que exigem a raiz do repo em `sys.path`, o que so acontece
automaticamente no modo `-m`:

    python -m games.tactics.main

Controles: WASD move a unidade ativa uma celula por vez (respeitando o
alcance de movimento restante no turno), ESPACO ataca uma unidade
inimiga adjacente (encerra o turno), ENTER encerra o turno sem atacar,
ESC sai.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from games.tactics.composition import build_game

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_game(config)
    game_loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
