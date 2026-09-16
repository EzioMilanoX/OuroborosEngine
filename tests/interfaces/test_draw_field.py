# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
`draw_field`: cor interpolada, forma nao -- e por que sao duas coisas.

Um campo e uma grade pequena de valores esticada sobre um retangulo:
iluminacao, nevoa de guerra, mapa de calor. Desenhar isso como um quad por
celula em `draw_batch` cobra por entidade (medido: ~2,8 us cada) e ainda por
cima mostra degraus do tamanho da celula -- o produto paga caro pra receber
ladrilho no lugar de gradiente.

A parte que estes testes guardam nao e "existe um campo", e sim a **divisao
entre os dois argumentos**, que e o contrato inteiro:

- `rgb` e quanto a celula VALE. Entre duas celulas, a media.
- `alpha` e o que a celula E. Entre duas celulas, nada -- rocha e rocha ate a
  aresta, e uma parede meio existente nao e uma parede.

Interpolar a forma junto com a cor e exatamente o erro que este contrato
impede. Uma silhueta borrada no tamanho de uma celula deixa de dizer onde a
parede termina, e num jogo em que a parede decide o caminho isso e pior do que
nao suavizar nada.
"""
import numpy as np
import pygame
import pytest

from ouroboros.adapters.pygame_backend.pygame_renderer import PygameRenderer
from ouroboros.interfaces.null.null_renderer import NullRenderer
from ouroboros.interfaces.renderer import IRenderer

_BACKDROP = (0, 128, 0)
"""Um verde que nenhum campo destes testes desenha -- entao ver verde e ver
BURACO, e nao "uma cor parecida"."""


@pytest.fixture
def renderer():
    renderer = PygameRenderer()
    renderer.initialize(width=200, height=120, title="draw_field")
    renderer.begin_frame()
    yield renderer
    renderer.shutdown()


def _pixels(renderer):
    return pygame.surfarray.array3d(renderer._surface)


def _split_field():
    """2 x 2: coluna 0 preta, coluna 1 branca."""
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[1, :, :] = 255
    return rgb


class TestTheColourIsInterpolated:
    def test_duas_celulas_viram_um_gradiente_e_nao_dois_blocos(self, renderer):
        """O motivo de a primitiva existir. Como dois quads, o meio da tela
        seria preto de um lado e branco do outro, com a emenda visivel."""
        renderer._surface.fill(_BACKDROP)
        renderer.draw_field(_split_field(), 0, 0, 200, 120)

        pixels = _pixels(renderer)
        esquerda = int(pixels[10, 60][0])
        meio = int(pixels[100, 60][0])
        direita = int(pixels[190, 60][0])
        assert esquerda < meio < direita, "o campo tem de variar entre as celulas"
        assert 100 < meio < 155, f"o meio devia ser meio-tom, e e {meio}"

    def test_um_campo_chapado_sai_chapado(self, renderer):
        rgb = np.full((4, 3, 3), 90, dtype=np.uint8)
        renderer._surface.fill(_BACKDROP)
        renderer.draw_field(rgb, 0, 0, 200, 120)

        pixels = _pixels(renderer)
        assert {int(v) for v in pixels[:, 60, 0]} == {90}


class TestTheShapeIsNot:
    def test_a_mascara_corta_seco(self, renderer):
        """A metade do contrato que separa isto de um blit escalado qualquer.

        Coluna 0 opaca, coluna 1 vazia: na fronteira tem de haver pixel
        desenhado ao lado de pixel de fundo, sem nenhum meio-termo. Se o alpha
        interpolasse, a parede teria uma borda de meia celula em que ela
        existe pela metade."""
        alpha = np.zeros((2, 2), dtype=np.uint8)
        alpha[0, :] = 255
        renderer._surface.fill(_BACKDROP)
        renderer.draw_field(_split_field(), 0, 0, 200, 120, alpha=alpha)

        pixels = _pixels(renderer)
        assert tuple(pixels[99, 60]) != _BACKDROP, "dentro da celula opaca"
        assert tuple(pixels[101, 60]) == _BACKDROP, "fora dela, o fundo intacto"

    def test_a_cor_continua_lisa_por_baixo_da_mascara(self, renderer):
        """As duas metades do contrato valem AO MESMO TEMPO: recortar seco nao
        pode custar a suavidade de dentro do recorte."""
        rgb = np.zeros((4, 2, 3), dtype=np.uint8)
        for i in range(4):
            rgb[i, :, :] = i * 80
        alpha = np.full((4, 2), 255, dtype=np.uint8)
        alpha[3, :] = 0                              # so a ultima coluna vazia

        renderer._surface.fill(_BACKDROP)
        renderer.draw_field(rgb, 0, 0, 200, 120, alpha=alpha)

        pixels = _pixels(renderer)
        amostras = [int(pixels[x, 60][0]) for x in (10, 60, 110)]
        assert amostras[0] < amostras[1] < amostras[2], "a cor tem de subir"
        assert tuple(pixels[190, 60]) == _BACKDROP, "a coluna vazia continua vazia"

    def test_sem_mascara_o_campo_e_opaco(self, renderer):
        renderer._surface.fill(_BACKDROP)
        renderer.draw_field(np.zeros((2, 2, 3), dtype=np.uint8), 0, 0, 200, 120)
        assert tuple(_pixels(renderer)[100, 60]) == (0, 0, 0)


class TestItBehavesLikeTheRestOfTheRenderer:
    def test_respeita_o_offset_de_camera(self, renderer):
        """`draw_batch` e `draw_effects` somam a camera; um campo que nao
        somasse ficaria parado enquanto o mundo anda."""
        rgb = np.full((2, 2, 3), 200, dtype=np.uint8)
        renderer._surface.fill(_BACKDROP)
        renderer.set_camera_offset(60.0, 0.0)
        renderer.draw_field(rgb, 0, 0, 100, 120)

        pixels = _pixels(renderer)
        assert tuple(pixels[10, 60]) == _BACKDROP, "antes do offset, nada"
        assert tuple(pixels[100, 60]) != _BACKDROP, "depois dele, o campo"

    def test_desenhar_o_mesmo_campo_nao_aloca_superficie_nova(self, renderer):
        """O campo e redesenhado TODO frame. Alocar duas superficies por
        chamada trocaria o laco de `draw_batch` por pressao de GC, que e a
        troca que a primitiva existe pra evitar."""
        rgb = np.full((2, 2, 3), 10, dtype=np.uint8)
        alpha = np.full((2, 2), 255, dtype=np.uint8)
        renderer.draw_field(rgb, 0, 0, 200, 120, alpha=alpha)
        # Identidade, e nao o tamanho do dicionario: um cache que cria uma
        # superficie nova e a guarda no MESMO lugar deixa o dicionario do
        # mesmo tamanho e aloca a cada frame do mesmo jeito.
        mask = renderer._field_masks[(2, 2)]
        field = renderer._field_surfaces[(200, 120)]
        for _ in range(20):
            renderer.draw_field(rgb, 0, 0, 200, 120, alpha=alpha)
        assert renderer._field_masks[(2, 2)] is mask
        assert renderer._field_surfaces[(200, 120)] is field

    def test_o_default_do_contrato_e_no_op(self):
        """Todo backend que nao souber desenhar campo continua valido -- mesmo
        criterio de `draw_particles`/`draw_effects`."""
        assert not getattr(IRenderer.draw_field, "__isabstractmethod__", False)
        NullRenderer().draw_field(np.zeros((2, 2, 3), dtype=np.uint8), 0, 0, 10, 10)
