# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ROADMAP M21 passo 1: as malhas dos construtores no render de verdade (ModernGL sem janela).
A luz e pela normal: com a luz vindo da camera, a face virada para ela acende -- se o
construtor tivesse virado o triangulo para dentro, ela sairia escura. Pula sem OpenGL."""
from __future__ import annotations

import pytest

from ouroboros.core.colisao3d import Relevo
from ouroboros.interfaces import malhas3d as m
from ouroboros.interfaces.renderer3d import Estilo3D, Iluminacao3D, Luz3D

moderngl = pytest.importorskip("moderngl")


@pytest.fixture(scope="module")
def r3d():
    try:
        ctx = moderngl.create_standalone_context()
    except Exception as erro:  # sem driver OpenGL (ex.: CI sem GPU)
        pytest.skip(f"sem OpenGL: {erro}")
    from ouroboros.adapters.gl_backend.gl_renderer3d import ModernGLRenderer3D

    r = ModernGLRenderer3D(ctx, 64, 48)
    yield r
    r.liberar()
    ctx.release()


def _centro_aceso(r, malha: m.Malha, camera, alvo) -> int:
    mid = malha.criar_em(r)
    try:
        r.definir_estilo(Estilo3D(fundo=(0, 0, 0)))
        luz = Luz3D("dir", tuple(c - a for c, a in zip(camera, alvo)), (1.0, 1.0, 1.0))
        r.definir_iluminacao(Iluminacao3D(ceu=(0, 0, 0), solo=(0, 0, 0), luzes=(luz,)))
        r.definir_camera(camera, alvo, 60.0)
        r.desenhar(mid)
        px = r.ler_pixels()
        r.desenhou = False
        return int(px[24, 32].max())
    finally:
        r.remover_malha(mid)


@pytest.mark.parametrize("malha", [
    m.caixa((-1, -1, -1), (1, 1, 1), (255, 255, 255)),
    m.esfera((0, 0, 0), 1.0, (255, 255, 255), subdivisoes=2),
    m.cilindro((0, -1, 0), 1.0, 2.0, (255, 255, 255), lados=12),
    m.extrusao([(-1, -1), (1, -1), (1, 1), (-1, 1)], -1, 1, (255, 255, 255)),
])
def test_solido_acende_do_lado_da_luz(r3d, malha):
    assert _centro_aceso(r3d, malha, (0.0, 0.3, 5.0), (0.0, 0.0, 0.0)) > 150


def test_terreno_acende_visto_de_cima(r3d):
    chao = m.terreno(Relevo.de_funcao(lambda x, z: 0.0, -3, 3, -3, 3, 1.0), (255, 255, 255))
    assert _centro_aceso(r3d, chao, (0.0, 5.0, 0.01), (0.0, 0.0, 0.0)) > 150
