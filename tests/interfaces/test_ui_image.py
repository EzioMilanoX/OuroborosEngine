# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
draw_ui_image (ROADMAP M18): uma textura carregada desenhada em coordenadas
de tela, com ancora, espelho, alfa e escala. Le pixels da tela real do
backend sob o driver SDL dummy.
"""
import pygame
import pytest

from ouroboros.adapters.pygame_backend.pygame_renderer import PygameRenderer
from ouroboros.interfaces.renderer import IRenderer

FUNDO = (8, 8, 14)


@pytest.fixture
def renderer(tmp_path):
    r = PygameRenderer()
    r.initialize(width=200, height=200, title="test")
    img = pygame.Surface((20, 10), pygame.SRCALPHA)
    img.fill((255, 0, 0, 255))
    img.fill((0, 0, 255, 255), pygame.Rect(10, 0, 10, 10))  # metade direita azul
    caminho = tmp_path / "t.png"
    pygame.image.save(img, str(caminho))
    r.load_texture(7, str(caminho))
    r.begin_frame()
    yield r
    r.shutdown()


def _pixel(x, y):
    return tuple(pygame.display.get_surface().get_at((x, y)))[:3]


def test_ancora_no_meio_da_base(renderer):
    renderer.draw_ui_image(7, 100, 100, anchor=(0.5, 1.0))
    assert _pixel(95, 95) == (255, 0, 0)  # metade esquerda
    assert _pixel(105, 95) == (0, 0, 255)  # metade direita
    assert _pixel(100, 102) == FUNDO  # nada abaixo dos pes


def test_espelho_troca_os_lados(renderer):
    renderer.draw_ui_image(7, 100, 100, anchor=(0.5, 1.0), flip_x=True)
    assert _pixel(95, 95) == (0, 0, 255)
    assert _pixel(105, 95) == (255, 0, 0)


def test_escala_e_alfa(renderer):
    renderer.draw_ui_image(7, 100, 100, scale=2.0)
    assert _pixel(82, 100) == (255, 0, 0)  # 40 de largura: vai de 80 a 120
    renderer.begin_frame()
    renderer.draw_ui_image(7, 100, 100, alpha=128)
    r, g, b = _pixel(95, 100)
    assert 100 < r < 255 and b < 100


def test_textura_desconhecida_nao_desenha(renderer):
    renderer.draw_ui_image(99, 100, 100)
    assert _pixel(100, 100) == FUNDO


def test_default_da_interface_e_no_op():
    class Minimo(IRenderer):
        def initialize(self, w, h, t): ...
        def begin_frame(self): ...
        def draw_batch(self, *a): ...
        def end_frame(self): ...
        def load_texture(self, i, p): ...
        def get_viewport_size(self): return (1, 1)
        def shutdown(self): ...

    Minimo().draw_ui_image(1, 0, 0)


def test_recarregar_o_mesmo_id_mostra_a_imagem_nova(renderer, tmp_path):
    """Uma "foto" nova no mesmo slot: o cache da escala antiga nao pode sobreviver."""
    renderer.draw_ui_image(7, 100, 100, scale=2.0)  # guarda a versao escalada da vermelha/azul
    verde = pygame.Surface((20, 10), pygame.SRCALPHA)
    verde.fill((0, 255, 0, 255))
    caminho = tmp_path / "verde.png"
    pygame.image.save(verde, str(caminho))
    renderer.load_texture(7, str(caminho))
    renderer.begin_frame()
    renderer.draw_ui_image(7, 100, 100, scale=2.0)
    assert _pixel(90, 100) == (0, 255, 0)
