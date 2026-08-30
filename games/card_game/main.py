# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Ponto de entrada do Card Game (vertical slice, ROADMAP M14).

Rodar SEMPRE como modulo, a partir da raiz do repositorio (mesma
convencao do Roguelite/Jogo Musical/Platformer/Tactics) -- NUNCA como
script solto, pois este modulo usa imports absolutos (`from
games.card_game...`) que exigem a raiz do repo em `sys.path`, o que so
acontece automaticamente no modo `-m`:

    python -m games.card_game.main

Controles: A/D navega a mao, ESPACO joga a carta sob o cursor (se a mana
permitir), ENTER avanca da fase principal pra combate, ESC sai.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from games.card_game.composition import build_game

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_game(config)
    game_loop.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
