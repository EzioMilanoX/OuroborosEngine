# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Vitrine de estilos (ROADMAP fase 8): cada estilo gera todos os quadros no tamanho da tela,
os estilos saem diferentes entre si, e a composicao monta e desenha de verdade (pygame
real sob o driver dummy de tests/conftest.py).
"""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from ouroboros.bootstrap.engine_config import EngineConfig

from games.vitrine_estilos import arte
from games.vitrine_estilos.composition import build_game

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_PATH = _REPO_ROOT / "games" / "vitrine_estilos" / "config.json"


@pytest.fixture(scope="module")
def quadros():
    pygame.init()
    pygame.display.set_mode((1, 1))
    return {e: arte.gerar(e) for e in arte.ESTILOS}


def test_cada_estilo_gera_todos_os_quadros_no_tamanho_da_tela(quadros):
    for estilo, qs in quadros.items():
        assert len(qs) == arte.QUADROS, estilo
        assert all(q.get_size() == (arte.LARGURA, arte.ALTURA) for q in qs), estilo


def test_os_estilos_sao_diferentes_entre_si(quadros):
    medias = {e: pygame.transform.average_color(qs[0])[:3] for e, qs in quadros.items()}
    assert len(set(medias.values())) == len(arte.ESTILOS)
    assert medias["sumie"][0] > 180  # o papel claro
    assert medias["neon"][0] < 60  # o escuro do neon


def test_pixel_art_sai_em_blocos_nitidos(quadros):
    q = quadros["pixel"][0]
    for x in range(0, 60, 6):  # dentro de um bloco de 6x6 a cor nao muda
        assert q.get_at((x, 30)) == q.get_at((x + 5, 30))


def test_o_corte_aparece_so_nos_quadros_de_ataque():
    assert arte.pose(0)["corte"] is None and arte.pose(9)["corte"] is not None


def test_a_vitrine_monta_troca_de_estilo_e_desenha(tmp_path):
    loop = build_game(EngineConfig.from_json(str(_CONFIG_PATH)), pasta=tmp_path)
    cena = loop.current_scene
    loop.tick_once(1 / 60)
    assert len(list(tmp_path.glob("*.png"))) == arte.QUADROS * len(arte.ESTILOS)
    assert cena.foco is None  # comeca na grade
    cena.foco = 2
    loop.tick_once(1 / 60)
    tela = pygame.display.get_surface()
    assert pygame.transform.average_color(tela)[0] > 180  # o papel do sumi-e na tela toda
    loop.renderer.shutdown()
