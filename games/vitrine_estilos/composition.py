# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Composicao da vitrine: pinta os quadros de cada estilo (`arte.gerar`, ou `biogenia.gerar`
para os tons de Biogenia), salva como PNG num cache em disco (refeito so quando a arte daquele
estilo muda), registra como texturas e mostra com `draw_ui_image` (M18)."""
from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence

import pygame

from games.vitrine_estilos import arte, biogenia
from games.vitrine_estilos.cena import VitrineScene
from ouroboros.bootstrap.composition_root import CompositionRoot
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.bootstrap.game_loop import GameLoop

BASE_ID = 7000
TODOS_OS_ESTILOS = arte.ESTILOS + biogenia.ESTILOS


def versao_da_arte(estilo: str = "") -> str:
    """Muda quando o codigo que pinta aquele estilo muda: o cache em disco so vale para a mesma
    arte (`arte.py` e `tres_d.py` para o espadachim; `biogenia.py`, que usa `arte.py`, para Biogenia)."""
    pasta = Path(arte.__file__).parent
    arquivos = ("biogenia.py", "arte.py", "tres_d.py") if estilo in biogenia.ESTILOS else ("arte.py", "tres_d.py")
    fonte = b"".join((pasta / a).read_bytes() for a in arquivos)
    return hashlib.sha1(fonte + str(arte.QUADROS).encode()).hexdigest()[:16]


def _gerar(estilo: str):
    return biogenia.gerar(estilo) if estilo in biogenia.ESTILOS else arte.gerar(estilo)


def _salvar(imagem: pygame.Surface, caminho: Path) -> None:
    """Salva num arquivo temporario e troca de nome: duas vitrines abertas ao mesmo tempo
    nao quebram uma a outra (se a troca falhar, a outra ja escreveu o mesmo quadro)."""
    tmp = caminho.with_name(f"{caminho.stem}.{os.getpid()}.png")
    pygame.image.save(imagem, str(tmp))
    try:
        os.replace(tmp, caminho)
    except OSError:
        tmp.unlink(missing_ok=True)
        if not caminho.exists():
            raise


def _aviso(renderer, texto: str) -> None:
    """Uma tela simples enquanto pinta (a primeira abertura demora): a janela segue viva."""
    renderer.begin_frame()
    renderer.draw_ui_rect(0, 0, arte.LARGURA, arte.ALTURA, (10, 9, 14, 255))
    renderer.draw_text(arte.LARGURA / 2, arte.ALTURA / 2, texto, 18, (230, 226, 220, 255), anchor="center")
    renderer.draw_text(arte.LARGURA / 2, arte.ALTURA / 2 + 30, "so na primeira vez (ou quando a arte muda)", 13,
                       (150, 146, 140, 255), anchor="center")
    renderer.end_frame()
    pygame.event.pump()


def preparar_texturas(renderer, pasta: Path, estilos: Sequence[str] = TODOS_OS_ESTILOS,
                      ao_pintar: Optional[Callable[[str], None]] = None) -> Dict[str, List[int]]:
    """Registra os quadros de cada estilo no renderer. Pinta e salva em `pasta` so o que
    falta ou mudou (a primeira abertura pinta tudo; as seguintes so carregam os PNGs).
    `ao_pintar(texto)` e chamado antes de pintar cada estilo (a tela de progresso)."""
    pasta.mkdir(parents=True, exist_ok=True)
    texturas: Dict[str, List[int]] = {}
    for i, estilo in enumerate(estilos):
        versao = versao_da_arte(estilo)
        caminhos = [pasta / f"{estilo}_{q}.png" for q in range(arte.QUADROS)]
        marca = pasta / f"versao_{estilo}.txt"  # uma marca por estilo
        valido = marca.exists() and marca.read_text(encoding="utf-8").strip() == versao
        if not (valido and all(c.exists() for c in caminhos)):
            if ao_pintar is not None:
                ao_pintar(f"pintando {i + 1} de {len(estilos)}: {estilo}")
            for caminho, imagem in zip(caminhos, _gerar(estilo)):
                _salvar(imagem, caminho)
            marca.write_text(versao, encoding="utf-8")
        ids = []
        for q, caminho in enumerate(caminhos):
            tid = BASE_ID + i * 100 + q
            renderer.load_texture(tid, str(caminho))
            ids.append(tid)
        texturas[estilo] = ids
    return texturas


def build_game(config: EngineConfig, pasta: Optional[Path] = None, cena: int = 0) -> GameLoop:
    game_loop = CompositionRoot(config).build()
    pasta = pasta or Path(tempfile.gettempdir()) / "ouroboros_vitrine_estilos"
    texturas = preparar_texturas(game_loop.renderer, pasta, ao_pintar=lambda texto: _aviso(game_loop.renderer, texto))
    game_loop.reset_scenes(VitrineScene(game_loop.input_provider, texturas, ao_sair=game_loop.stop, cena=cena))
    return game_loop
