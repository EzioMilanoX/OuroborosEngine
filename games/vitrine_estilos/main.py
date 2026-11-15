# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Vitrine de estilos (ROADMAP fase 8): a mesma cena em ilustracao cel-shading, pixel art,
tinta/sumi-e, flat com luz e low poly 3D, para comparar o que a engine pode mostrar; e uma
segunda cena, Biogenia (o fim do Cretaceo), em seis tons possiveis para o jogo.

Rodar a partir da raiz do repositorio:

    python -m games.vitrine_estilos.main            # comeca no espadachim
    python -m games.vitrine_estilos.main biogenia   # comeca em Biogenia

Controles: 1-6 abre um estilo em tela cheia, G volta para a grade, A/D troca, C troca de
cena, ESC sai.
"""
from __future__ import annotations

import sys
from pathlib import Path

from games.vitrine_estilos.composition import build_game
from ouroboros.bootstrap.engine_config import EngineConfig

_CONFIG_PATH = Path(__file__).resolve().parent / "config.json"


def main() -> int:
    config = EngineConfig.from_json(str(_CONFIG_PATH))
    game_loop = build_game(config, cena=1 if "biogenia" in sys.argv[1:] else 0)
    try:
        game_loop.run()
    finally:
        game_loop.renderer.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
