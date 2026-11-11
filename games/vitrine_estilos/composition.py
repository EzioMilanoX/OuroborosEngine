# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao da vitrine: pinta os quadros de cada estilo (`arte.gerar`), salva como PNG
num cache, registra como texturas e mostra com `draw_ui_image` (M18)."""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pygame

from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop

from games.vitrine_estilos import arte
from games.vitrine_estilos.cena import VitrineScene

BASE_ID = 7000


def preparar_texturas(renderer, pasta: Path, estilos: Sequence[str] = arte.ESTILOS) -> Dict[str, List[int]]:
    """Gera os quadros de cada estilo, salva em `pasta` e registra no renderer."""
    pasta.mkdir(parents=True, exist_ok=True)
    texturas: Dict[str, List[int]] = {}
    for i, estilo in enumerate(estilos):
        ids = []
        for q, imagem in enumerate(arte.gerar(estilo)):
            caminho = pasta / f"{estilo}_{q}.png"
            pygame.image.save(imagem, str(caminho))
            tid = BASE_ID + i * 100 + q
            renderer.load_texture(tid, str(caminho))
            ids.append(tid)
        texturas[estilo] = ids
    return texturas


def build_game(config: EngineConfig, pasta: Optional[Path] = None) -> GameLoop:
    game_loop = CompositionRoot(config).build()
    pasta = pasta or Path(tempfile.gettempdir()) / "ouroboros_vitrine_estilos"
    texturas = preparar_texturas(game_loop.renderer, pasta)
    game_loop.reset_scenes(VitrineScene(game_loop.input_provider, texturas, ao_sair=game_loop.stop))
    return game_loop
