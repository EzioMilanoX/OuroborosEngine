# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Modo ASCII no pygame (ROADMAP M22): `draw_ascii` com cache de glifos e o filtro ASCII
(luminancia -> caractere) sobre o quadro renderizado. Pixels lidos da tela real do backend
sob o driver SDL dummy; os defaults da interface continuam no-op.
"""
import json

import pygame
import pytest

from ouroboros.adapters.pygame_backend.pygame_renderer import PygameRenderer
from ouroboros.bootstrap.engine_config import EngineConfig
from ouroboros.core.ascii import FiltroAscii, TelaAscii
from ouroboros.interfaces.null.null_renderer import NullRenderer


@pytest.fixture
def renderer():
    r = PygameRenderer()
    r.initialize(width=320, height=160, title="test")
    r.begin_frame()
    yield r
    r.shutdown()


def _tela():
    return pygame.display.get_surface()


def test_defaults_da_interface_sao_no_op():
    r = NullRenderer()
    r.initialize(10, 10, "t")
    assert r.ascii_cell_size(16) is None
    r.draw_ascii(TelaAscii(2, 2))
    r.set_ascii_filter(FiltroAscii())


def test_draw_ascii_pinta_glifos_e_fundo_por_celula(renderer):
    cw, ch = renderer.ascii_cell_size(16)
    assert cw > 0 and ch > cw  # a celula e mais alta que larga
    t = TelaAscii(6, 2, fundo=(0, 0, 90))
    t.por(1, 0, "@", (255, 0, 0))
    t.por(4, 1, " ", fundo=(0, 120, 0))
    renderer.draw_ascii(t, 10, 20, 16)
    # o fundo de cada celula
    assert tuple(_tela().get_at((10 + 4 * cw + cw // 2, 20 + ch + ch // 2)))[:3] == (0, 120, 0)
    assert tuple(_tela().get_at((10 + 3, 20 + 3)))[:3] == (0, 0, 90)
    assert tuple(_tela().get_at((5, 5)))[:3] == (8, 8, 14)  # fora da grade: intocado
    # o "@" vermelho aparece dentro da celula (1, 0)
    celula = _tela().subsurface((10 + cw, 20, cw, ch))
    assert any(celula.get_at((x, y))[0] > 150 and celula.get_at((x, y))[2] < 120
               for x in range(cw) for y in range(ch))


def test_glifo_e_renderizado_uma_vez_so(renderer, monkeypatch):
    t = TelaAscii(10, 3, fundo=None)
    t.texto(0, 0, "aaaaaaaaaa", (200, 200, 200))
    t.texto(0, 1, "bbbbbbbbbb", (200, 200, 200))
    desenhista = renderer._desenhista_ascii()
    fonte = desenhista.fonte(14)
    chamadas = []
    original = fonte.render

    class Espiao:
        def __getattr__(self, nome):
            return getattr(fonte, nome)

        def render(self, *a, **k):
            chamadas.append(a[0])
            return original(*a, **k)

    monkeypatch.setitem(desenhista._fontes, 14, Espiao())
    for _ in range(5):
        renderer.draw_ascii(t, 0, 0, 14)
    assert sorted(chamadas) == ["a", "b"]  # 2 glifos, 100 celulas desenhadas


def test_filtro_converte_luminancia_em_caractere(renderer):
    renderer.set_ascii_filter(FiltroAscii(tamanho_fonte=12, fundo=0.0, realce=0.0))
    renderer.begin_frame()
    renderer.draw_ui_rect(0, 0, 160, 160, (0, 0, 0, 255))
    renderer.draw_ui_rect(160, 0, 160, 160, (255, 255, 255, 255))
    renderer.end_frame()
    tela = renderer._ascii.ultima_tela_filtro
    cw, ch = renderer.ascii_cell_size(12)
    assert (tela.colunas, tela.linhas) == (320 // cw, 160 // ch)
    meio = tela.linhas // 2
    assert tela.ler(1, meio) == " "  # o preto vira espaco
    assert tela.ler(tela.colunas - 2, meio) == "@"  # o branco, o caractere mais cheio
    # a metade branca virou caracteres: nao e mais branca chapada
    media = pygame.transform.average_color(_tela(), (160, 0, 160, 160))
    assert 30 < media[0] < 230


def test_filtro_respeita_a_area_e_desliga(renderer):
    renderer.set_ascii_filter(FiltroAscii(tamanho_fonte=12, area=(0, 0, 320, 100)))
    renderer.begin_frame()
    renderer.draw_ui_rect(0, 0, 320, 160, (250, 250, 250, 255))
    renderer.end_frame()
    assert tuple(_tela().get_at((50, 150)))[:3] == (250, 250, 250)  # fora da area: o HUD fica
    renderer.set_ascii_filter(None)
    renderer.begin_frame()
    renderer.draw_ui_rect(0, 0, 320, 160, (250, 250, 250, 255))
    renderer.end_frame()
    assert pygame.transform.average_color(_tela())[:3] == (250, 250, 250)


def test_engine_config_liga_o_filtro_pelo_json(tmp_path):
    base = {"window_width": 64, "window_height": 48, "window_title": "t", "entity_capacity": 4,
            "difficulty_path": "x", "input_bindings_path": "y"}
    caminho = tmp_path / "c.json"
    caminho.write_text(json.dumps(base), encoding="utf-8")
    assert EngineConfig.from_json(str(caminho)).ascii_filter is None  # desligado por padrao
    caminho.write_text(json.dumps({**base, "ascii_filter": True}), encoding="utf-8")
    assert EngineConfig.from_json(str(caminho)).ascii_filter == FiltroAscii()
    caminho.write_text(json.dumps({**base, "ascii_filter": {"tamanho_fonte": 10, "area": [0, 0, 64, 40]}}),
                       encoding="utf-8")
    filtro = EngineConfig.from_json(str(caminho)).ascii_filter
    assert filtro.tamanho_fonte == 10 and filtro.area == (0, 0, 64, 40)
