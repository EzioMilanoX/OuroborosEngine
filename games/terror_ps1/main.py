# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Demo de terror PS1 em primeira pessoa, na placa de video (ROADMAP M21; blueprint SEN-04).

    pip install moderngl
    python -m games.terror_ps1.main

Mouse olha, WASD anda (Q/E ou setas tambem giram), F ou botao direito liga/apaga a
lanterna, F11 tela cheia, ESC sai.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from games.terror_ps1.composition import build_game

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    game_loop = build_game(EngineConfig.from_json(str(_CONFIG_PATH)))
    try:
        game_loop.run()
    finally:
        game_loop.renderer.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
