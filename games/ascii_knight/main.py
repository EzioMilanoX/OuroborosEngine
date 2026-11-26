# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
ASCII Knight (ROADMAP M20/M22): um cavaleiro em arte ASCII numa arena em visao 3/4, com
pilares, arvores, duas gosmas e um morcego, ordenados pela fila de profundidade da engine.

Rodar a partir da raiz do repositorio:

    python -m games.ascii_knight.main

Controles: setas/WASD andar, espaco atacar, J pular, F troca o desenho (ASCII nativo ->
filtro ASCII sobre o render normal -> render normal), P troca a projecao (3/4 -> isometrica
-> de cima), ESC sai.
"""
from __future__ import annotations

from pathlib import Path

from games.ascii_knight.composition import build_game
from ouroboros.bootstrap.engine_config import EngineConfig

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_game(config)
    try:
        game_loop.run()
    finally:
        game_loop.renderer.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
