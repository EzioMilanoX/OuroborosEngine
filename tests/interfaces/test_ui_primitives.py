# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Primitivas vetoriais de UI e fontes customizadas (ROADMAP M16), contra o
driver SDL dummy forcado em conftest.py. Cada teste le pixels da tela real
do backend: o que importa e o que aparece, nao que a chamada nao explodiu.
"""
import math
import os

import pygame
import pytest

from ouroboros.adapters.pygame_backend.pygame_renderer import PygameRenderer
from ouroboros.interfaces.renderer import IRenderer

FUNDO = (8, 8, 14)  # cor de begin_frame do PygameRenderer
VERMELHO = (255, 0, 0, 255)


@pytest.fixture
def renderer():
    r = PygameRenderer()
    r.initialize(width=200, height=200, title="test")
    r.begin_frame()
    yield r
    r.shutdown()


def _pixel(x, y):
    return tuple(pygame.display.get_surface().get_at((x, y)))[:3]


def _faixa(x0, x1, y):
    """Pixels de uma faixa horizontal: bordas podem cair 1px para dentro ou fora."""
    return [_pixel(x, y) for x in range(x0, x1)]


def test_circulo_preenchido_pinta_o_centro(renderer):
    renderer.draw_ui_circle(100, 100, 30, VERMELHO)
    assert _pixel(100, 100) == (255, 0, 0)
    assert _pixel(100 + 40, 100) == FUNDO


def test_circulo_com_espessura_e_so_contorno(renderer):
    renderer.draw_ui_circle(100, 100, 30, VERMELHO, width=3)
    assert _pixel(100, 100) == FUNDO
    assert (255, 0, 0) in _faixa(126, 132, 100)


def test_circulo_translucido_mistura_com_o_fundo(renderer):
    renderer.draw_ui_circle(100, 100, 30, (255, 0, 0, 128))
    r, g, b = _pixel(100, 100)
    assert 100 < r < 255 and (r, g, b) != FUNDO


def test_linha(renderer):
    renderer.draw_ui_line(20, 50, 180, 50, VERMELHO, width=3)
    assert _pixel(100, 50) == (255, 0, 0)
    assert _pixel(100, 60) == FUNDO


def test_linha_fina_translucida_nao_explode_e_aparece(renderer):
    renderer.draw_ui_line(20, 20, 180, 20, (255, 0, 0, 200))
    assert _pixel(100, 20) != FUNDO


def test_arco_segue_a_convencao_anti_horaria(renderer):
    """0 a pi/2 e o quarto de cima-direita da tela (anti-horario visto na
    tela); o quarto de baixo-direita precisa ficar vazio."""
    renderer.draw_ui_arc(100, 100, 40, 0, math.pi / 2, VERMELHO, width=4)
    d = int(40 * math.cos(math.pi / 4))
    cima_direita = [_pixel(100 + d + o, 100 - d - o) for o in range(-3, 3)]
    baixo_direita = [_pixel(100 + d + o, 100 + d + o) for o in range(-3, 3)]
    assert (255, 0, 0) in cima_direita
    assert (255, 0, 0) not in baixo_direita


def test_poligono_preenchido_e_contorno(renderer):
    triangulo = [(100, 40), (160, 160), (40, 160)]
    renderer.draw_ui_polygon(triangulo, VERMELHO)
    assert _pixel(100, 120) == (255, 0, 0)

    renderer.begin_frame()
    renderer.draw_ui_polygon(triangulo, VERMELHO, width=2)
    assert _pixel(100, 120) == FUNDO
    assert (255, 0, 0) in _faixa(96, 104, 159) + _faixa(96, 104, 160)


def test_formas_degeneradas_sao_ignoradas(renderer):
    renderer.draw_ui_circle(100, 100, 0, VERMELHO)
    renderer.draw_ui_arc(100, 100, -1, 0, 1, VERMELHO)
    renderer.draw_ui_polygon([(0, 0), (10, 10)], VERMELHO)
    assert _pixel(100, 100) == FUNDO


def _fonte_de_teste():
    """A fonte que acompanha o pygame: um TTF real sem depender de asset do repo."""
    return os.path.join(os.path.dirname(pygame.__file__), pygame.font.get_default_font())


def _largura_do_texto(renderer, **kw):
    renderer.begin_frame()
    renderer.draw_text(10, 10, "WWWWWWWW", 24, (255, 255, 255, 255), **kw)
    linha = [_pixel(x, 22) for x in range(0, 200)]
    acesos = [x for x, p in enumerate(linha) if p != FUNDO]
    return max(acesos) - min(acesos)


def test_load_font_muda_a_fonte_usada_pelo_draw_text(renderer):
    padrao = _largura_do_texto(renderer)
    renderer.load_font(3, _fonte_de_teste())
    customizada = _largura_do_texto(renderer, font_id=3)
    assert customizada != padrao


def test_font_id_nunca_carregado_cai_na_fonte_padrao(renderer):
    assert _largura_do_texto(renderer, font_id=99) == _largura_do_texto(renderer)


def test_load_font_com_arquivo_invalido_falha_no_carregamento(renderer, tmp_path):
    ruim = tmp_path / "nao_e_fonte.ttf"
    ruim.write_bytes(b"isto nao e uma fonte")
    with pytest.raises(Exception):
        renderer.load_font(4, str(ruim))


def test_null_renderer_registra_fontes_e_aceita_as_primitivas(null_renderer):
    assert isinstance(null_renderer, IRenderer)
    null_renderer.load_font(5, "kanji.ttf")
    assert null_renderer._loaded_fonts[5] == "kanji.ttf"
    null_renderer.draw_ui_line(0, 0, 1, 1, VERMELHO)
    null_renderer.draw_ui_circle(0, 0, 1, VERMELHO)
    null_renderer.draw_ui_arc(0, 0, 1, 0, 1, VERMELHO)
    null_renderer.draw_ui_polygon([(0, 0), (1, 0), (0, 1)], VERMELHO)
    null_renderer.draw_text(0, 0, "x", 12, VERMELHO, font_id=5)
