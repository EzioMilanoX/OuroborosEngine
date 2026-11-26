# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao do ASCII Knight: o `GameLoop` padrao da engine com a cena da arena."""
from __future__ import annotations

from games.ascii_knight.cena import AsciiKnightScene
from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop


def build_game(config: EngineConfig, seed: int = 7) -> GameLoop:
    game_loop = CompositionRoot(config).build()
    cena = AsciiKnightScene(game_loop.input_provider, game_loop.renderer, ao_sair=game_loop.stop, seed=seed)
    game_loop.reset_scenes(cena)
    return game_loop
