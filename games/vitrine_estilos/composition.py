# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao da vitrine: pinta os quadros de cada estilo (`arte.gerar`), salva como PNG
num cache em disco (refeito so quando `arte.py` muda), registra como texturas e mostra com
`draw_ui_image` (M18)."""
from __future__ import annotations

import hashlib
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


def versao_da_arte() -> str:
    """Muda quando `arte.py` ou `tres_d.py` muda: o cache em disco so vale para a mesma arte."""
    pasta = Path(arte.__file__).parent
    fonte = (pasta / "arte.py").read_bytes() + (pasta / "tres_d.py").read_bytes()
    return hashlib.sha1(fonte + str(arte.QUADROS).encode()).hexdigest()[:16]


def preparar_texturas(renderer, pasta: Path, estilos: Sequence[str] = arte.ESTILOS) -> Dict[str, List[int]]:
    """Registra os quadros de cada estilo no renderer. Pinta e salva em `pasta` so o que
    falta ou mudou (a primeira abertura pinta tudo; as seguintes so carregam os PNGs)."""
    pasta.mkdir(parents=True, exist_ok=True)
    versao = versao_da_arte()
    texturas: Dict[str, List[int]] = {}
    for i, estilo in enumerate(estilos):
        caminhos = [pasta / f"{estilo}_{q}.png" for q in range(arte.QUADROS)]
        marca = pasta / f"versao_{estilo}.txt"  # uma marca por estilo
        valido = marca.exists() and marca.read_text(encoding="utf-8").strip() == versao
        if not (valido and all(c.exists() for c in caminhos)):
            for caminho, imagem in zip(caminhos, arte.gerar(estilo)):
                pygame.image.save(imagem, str(caminho))
            marca.write_text(versao, encoding="utf-8")
        ids = []
        for q, caminho in enumerate(caminhos):
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
