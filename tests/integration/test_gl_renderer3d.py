# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ROADMAP M21: o render 3D na placa de video, sem janela (contexto ModernGL standalone).
Pula se a ModernGL nao estiver instalada ou a maquina nao tiver OpenGL 3.3."""
from __future__ import annotations

import numpy as np
import pytest

from ouroboros.interfaces.renderer3d import COR_AFIM, Estilo3D, Iluminacao3D, Luz3D, translacao_e_giro_y

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


def _quadrado(z: float, lado: float = 2.0):
    """Dois triangulos virados para +z (para a camera), no plano z."""
    a, b, c, d = (-lado, -lado, z), (lado, -lado, z), (lado, lado, z), (-lado, lado, z)
    return np.array([a, b, c, a, c, d], dtype=np.float32)


def _quadro(r, *malhas, estilo=Estilo3D(), luz=Iluminacao3D(ceu=(1, 1, 1), solo=(1, 1, 1))):
    r.definir_estilo(estilo)
    r.definir_iluminacao(luz)
    r.definir_camera((0.0, 0.0, 5.0), (0.0, 0.0, 0.0), 60.0)
    for m, modelo in malhas:
        r.desenhar(m, modelo)
    px = r.ler_pixels()
    r.desenhou = False
    return px


def test_z_buffer_o_mais_perto_ganha_em_qualquer_ordem(r3d):
    vermelho = r3d.criar_malha(_quadrado(1.0), np.full((6, 3), (255, 0, 0)))
    verde = r3d.criar_malha(_quadrado(-1.0), np.full((6, 3), (0, 255, 0)))
    for ordem in ((vermelho, verde), (verde, vermelho)):
        px = _quadro(r3d, *((m, None) for m in ordem))
        assert tuple(px[24, 32]) == (255, 0, 0)


def test_neblina_engole_o_longe_mas_nao_o_que_emite_luz(r3d):
    branco = r3d.criar_malha(_quadrado(0.0), np.full((6, 3), (255, 255, 255)))
    lampada = r3d.criar_malha(_quadrado(0.0), np.full((6, 3), (255, 255, 255)), emissivo=np.ones(6, bool))
    escuro = Estilo3D(fundo=(0, 0, 0), neblina_cor=(0, 0, 0), neblina=(1.0, 3.0))
    assert _quadro(r3d, (branco, None), estilo=escuro)[24, 32].max() < 10
    assert _quadro(r3d, (lampada, None), estilo=escuro)[24, 32].min() > 245


def test_a_lanterna_so_acende_o_que_esta_no_cone(r3d):
    # um chao em grade: a luz e por vertice (Gouraud), um quadrado so com 4 cantos fora do
    # cone ficaria todo escuro -- a mesma limitacao do PS1
    grade = [_quadrado(0.0, 0.25) + (x, y, 0) for x in np.arange(-6, 6, 0.5) for y in np.arange(-6, 6, 0.5)]
    chao = r3d.criar_malha(np.vstack(grade), np.full((6 * len(grade), 3), (200, 200, 200)))
    foco = Luz3D("foco", (0.0, 0.0, 4.0), (3.0, 3.0, 3.0), 20.0, direcao=(0.0, 0.0, -1.0), cone=(0.98, 0.995))
    px = _quadro(r3d, (chao, None), luz=Iluminacao3D(ceu=(0, 0, 0), solo=(0, 0, 0), luzes=(foco,)))
    assert px[24, 32].mean() > 120  # o centro, sob o feixe
    assert px[2, 2].mean() < 10  # o canto, fora do cone


def test_modelo_move_a_malha(r3d):
    m = r3d.criar_malha(_quadrado(0.0, 0.5), np.full((6, 3), (255, 255, 255)))
    centro = _quadro(r3d, (m, None))
    longe = _quadro(r3d, (m, translacao_e_giro_y(3.0, 0.0, 0.0)))
    assert centro[24, 32].min() > 200 and longe[24, 32].max() < 30


def test_estilo_ps1_baixa_resolucao_e_15_bits(r3d):
    m = r3d.criar_malha(_quadrado(0.0), np.array([(255, 0, 0), (0, 255, 0), (0, 0, 255)] * 2, dtype=np.float32))
    ps1 = Estilo3D(resolucao=(32, 24), fundo=(0, 0, 0), tremor=True, modo_cor=COR_AFIM, bits_cor=5, pontilhado=True)
    px = _quadro(r3d, (m, None), estilo=ps1)
    assert px.shape == (24, 32, 3)
    niveis = {round(v / 255 * 31, 3) for v in np.unique(px)}
    assert all(abs(n - round(n)) < 0.07 for n in niveis)  # so os 32 niveis de 5 bits
