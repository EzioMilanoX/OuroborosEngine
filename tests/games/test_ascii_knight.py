# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ASCII Knight (ROADMAP M20/M22): a cena monta, roda quadros nos tres desenhos e nas tres
projecoes, anda, pula, golpeia e passa atras/na frente do pilar (pygame real sob o driver
dummy de tests/conftest.py)."""
from __future__ import annotations

from pathlib import Path

import pygame
import pytest

from games.ascii_knight import arte
from games.ascii_knight.composition import build_game
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.core.projecao import MODOS

_CONFIG = Path(__file__).resolve().parent.parent.parent / "games" / "ascii_knight" / "config.json"


@pytest.fixture
def jogo():
    loop = build_game(EngineConfig.from_json(str(_CONFIG)))
    entrada = loop.input_provider
    segurando, apertou = set(), set()
    entrada.is_action_held = lambda a: a in segurando
    entrada.is_action_pressed = lambda a: a in apertou
    yield loop, loop.current_scene, segurando, apertou
    loop.renderer.shutdown()


def test_roda_nos_tres_desenhos_e_nas_tres_projecoes(jogo):
    loop, cena, _, _ = jogo
    vistos = set()
    for _ in MODOS:
        for _ in range(3):
            for _ in range(3):
                loop.tick_once(1 / 60)
            pixels = pygame.surfarray.array3d(pygame.display.get_surface())[:, :500]
            assert pixels.std() > 8, (cena.proj.modo, cena.modo_render)  # desenhou algo, nao so o fundo
            assert (loop.renderer._filtro_ascii is not None) == (cena.modo_render == "filtro")
            vistos.add((cena.proj.modo, cena.modo_render))
            cena.trocar_render()
        cena.trocar_projecao()
    assert len(vistos) == 9


def test_anda_pula_e_vira_para_o_lado(jogo):
    loop, cena, segurando, apertou = jogo
    k = cena.cavaleiro
    x0 = k.x
    segurando.add("direita")
    for _ in range(20):
        loop.tick_once(1 / 60)
    assert k.x > x0 + 50 and k.olhando == 1 and k.estado == "andando"
    segurando.clear()
    segurando.add("esquerda")
    loop.tick_once(1 / 60)
    assert k.olhando == -1
    segurando.clear()
    apertou.add("pular")
    loop.tick_once(1 / 60)
    apertou.clear()
    for _ in range(10):
        loop.tick_once(1 / 60)
    assert k.z > 20 and cena._sprite_cavaleiro() is arte.PULO
    for _ in range(60):
        loop.tick_once(1 / 60)
    assert k.z == 0.0


def test_o_golpe_acerta_o_inimigo_na_frente(jogo):
    loop, cena, _, apertou = jogo
    k = cena.cavaleiro
    alvo = cena.inimigos[0]
    for e in cena.inimigos[1:]:
        e.vivo, e.t_volta = False, 99.0
    k.x, k.y, k.olhando = 480.0, 330.0, 1
    alvo.x, alvo.y, alvo.z, alvo.hp, alvo.t = 520.0, 330.0, 0.0, 1, 0.0
    apertou.add("atacar")
    loop.tick_once(1 / 60)
    apertou.clear()
    for _ in range(20):
        loop.tick_once(1 / 60)
    assert not alvo.vivo and cena.abates == 1


def test_passa_atras_e_na_frente_do_pilar(jogo):
    loop, cena, _, _ = jogo
    _, px, py, _ = cena.cenario[0]
    k = cena.cavaleiro
    k.x, k.y = px + 5, py - 30  # atras (mais longe da camera)
    ordem = cena.montar_fila().tolist()
    assert ordem.index(200) < ordem.index(0)  # o cavaleiro sai antes: o pilar o cobre
    k.x, k.y = px + 5, py + 30  # na frente
    ordem = cena.montar_fila().tolist()
    assert ordem.index(200) > ordem.index(0)
