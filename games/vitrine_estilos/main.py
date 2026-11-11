# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Vitrine de estilos (ROADMAP fase 8): a mesma cena em ilustracao cel-shading, pixel art,
tinta/sumi-e, flat com luz e low poly 3D, para comparar o que a engine pode mostrar.

Rodar a partir da raiz do repositorio:

    python -m games.vitrine_estilos.main

Controles: 1-5 abre um estilo em tela cheia, G volta para a grade, A/D troca, ESC sai.
"""
from __future__ import annotations

from pathlib import Path

from ouroboros.bootstrap.engine_config import EngineConfig

from games.vitrine_estilos.composition import build_game

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
