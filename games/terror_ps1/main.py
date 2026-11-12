# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Demo de terror PS1 em primeira pessoa, na placa de video (ROADMAP M21; blueprint SEN-04).

Uma floresta de 80x80 com sete marcos: ache os 7 amuletos e leve-os ao santuario do torii,
ao norte. O vulto so anda quando nao esta iluminado; as armadilhas de urso nas trilhas
prendem e fazem barulho, e ele ouve.

    pip install moderngl
    python -m games.terror_ps1.main

Mouse olha, WASD anda (Q/E ou setas tambem giram), F ou botao direito liga/apaga a
lanterna, ESPACO (ou botao esquerdo) forca a armadilha, F11 tela cheia, ESC sai.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.resources import ResourceRoot

from games.terror_ps1.composition import build_game

# a raiz do repositorio (onde fica data/); dentro do .exe, a pasta _internal
RECURSOS = ResourceRoot(Path(__file__).resolve().parents[2])


def carregar_config() -> EngineConfig:
    """O config.json com os caminhos de dados absolutos: abre de qualquer pasta."""
    cfg = EngineConfig.from_json(str(RECURSOS("games", "terror_ps1", "config.json")))
    return dataclasses.replace(cfg, difficulty_path=RECURSOS.resolve(cfg.difficulty_path),
                               input_bindings_path=RECURSOS.resolve(cfg.input_bindings_path))


def main() -> int:
    game_loop = build_game(carregar_config())
    try:
        game_loop.run()
    finally:
        game_loop.renderer.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
