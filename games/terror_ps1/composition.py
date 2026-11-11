# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao da demo: o CompositionRoot monta o renderer "gl" (config.json) e a cena usa
o `renderer_3d()` dele."""
from __future__ import annotations

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop

from games.terror_ps1.cena import TerrorScene


def build_game(config: EngineConfig) -> GameLoop:
    game_loop = CompositionRoot(config).build()
    game_loop.reset_scenes(TerrorScene(game_loop.input_provider, game_loop.renderer, game_loop.audio_engine,
                                       ao_sair=game_loop.stop))
    return game_loop
