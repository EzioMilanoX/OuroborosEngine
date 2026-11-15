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


def _composto(r, estilo):
    """O quadro como sai na tela: o 3D ampliado pelo `compor` (onde moram grao, vinheta e VHS)."""
    tela = r._ctx.simple_framebuffer((64, 48))
    cores = np.array([(255, 40, 40), (40, 255, 40), (40, 40, 255)] * 2, dtype=np.float32)
    m = r.criar_malha(_quadrado(0.0, 1.0), cores)
    _quadro(r, (m, None), estilo=estilo)
    r.desenhar(m)
    r.compor(tela)
    px = np.frombuffer(tela.read(components=3), dtype=np.uint8).reshape(48, 64, 3).astype(int)
    r.remover_malha(m)
    tela.release()
    return px


def test_fita_vhs_so_aparece_quando_pedida(r3d):
    limpo = _composto(r3d, Estilo3D(fundo=(0, 0, 0)))
    assert np.array_equal(limpo, _composto(r3d, Estilo3D(fundo=(0, 0, 0))))  # sem VHS (nem grao): estavel
    fita = _composto(r3d, Estilo3D(fundo=(0, 0, 0), vhs=1.0))
    assert np.abs(fita - limpo).sum() > 0  # com VHS a imagem muda
    cor = lambda px: np.abs(px - px.mean(axis=2, keepdims=True)).mean()  # noqa: E731
    assert cor(fita) < cor(limpo)  # e perde cor


def test_espelhar_inverte_a_imagem_na_horizontal(r3d):
    limpo = _composto(r3d, Estilo3D(fundo=(0, 0, 0)))
    espelho = _composto(r3d, Estilo3D(fundo=(0, 0, 0), espelhar=True))
    assert np.array_equal(espelho, limpo[:, ::-1])


# ------------------------------------------------------------ recortes (billboards)

def _meio_vermelho(espelhado: bool = False) -> np.ndarray:
    """8x16 RGBA: a metade da direita vermelha e opaca, a da esquerda transparente."""
    img = np.zeros((16, 8, 4), dtype=np.uint8)
    img[:, 4:] = (255, 0, 0, 255)
    return img


def _quadro_recorte(r, rid, camera=(0.0, 0.0, 5.0), antes=(), **kw):
    r.definir_estilo(Estilo3D(fundo=(0, 0, 0)))
    r.definir_iluminacao(Iluminacao3D(ceu=(1, 1, 1), solo=(1, 1, 1)))
    r.definir_camera(camera, (0.0, 0.0, 0.0), 60.0)
    for m in antes:
        r.desenhar(m, None)
    r.desenhar_recorte(rid, (0.0, -1.0, 0.0), 2.0, **kw)
    px = r.ler_pixels()
    r.desenhou = False
    return px


def test_recorte_fica_em_pe_e_o_transparente_mostra_o_fundo(r3d):
    rid = r3d.criar_recorte(_meio_vermelho(), (4, 16))  # o pe: embaixo, no meio
    px = _quadro_recorte(r3d, rid)
    assert tuple(px[24, 34]) == (255, 0, 0)  # a metade opaca, a direita do meio
    assert tuple(px[24, 29]) == (0, 0, 0)  # a transparente: o fundo
    assert tuple(px[4, 34]) == (0, 0, 0)  # 2 de altura: nao chega ao topo da tela


def test_recorte_espelhado_vira_na_horizontal(r3d):
    rid = r3d.criar_recorte(_meio_vermelho(), (4, 16))
    px = _quadro_recorte(r3d, rid, espelhar=True)
    assert tuple(px[24, 29]) == (255, 0, 0) and tuple(px[24, 34]) == (0, 0, 0)


def test_recorte_gira_para_encarar_a_camera(r3d):
    rid = r3d.criar_recorte(np.full((16, 8, 4), 255, dtype=np.uint8), (4, 16))
    de_lado = _quadro_recorte(r3d, rid, camera=(5.0, 0.0, 0.0))  # a camera foi para o lado
    assert de_lado[24, 32].min() > 200  # continua de frente (um plano fixo sumiria de perfil)


def test_recorte_respeita_o_z_buffer(r3d):
    rid = r3d.criar_recorte(np.full((16, 8, 4), 255, dtype=np.uint8), (4, 16))
    verde = r3d.criar_malha(_quadrado(1.0), np.full((6, 3), (0, 255, 0)))  # na frente do recorte
    px = _quadro_recorte(r3d, rid, antes=(verde,))
    assert tuple(px[24, 32]) == (0, 255, 0)


def test_sombra_escurece_o_chao_embaixo_do_recorte(r3d):
    vazio = np.zeros((16, 8, 4), dtype=np.uint8)  # um recorte invisivel: so a sombra aparece
    rid = r3d.criar_recorte(vazio, (4, 16))
    lado = 6.0
    a, b, c, d = (-lado, -1.0, lado), (lado, -1.0, lado), (lado, -1.0, -lado), (-lado, -1.0, -lado)
    chao = r3d.criar_malha(np.array([a, b, c, a, c, d], dtype=np.float32), np.full((6, 3), (200, 200, 200)))
    cam = (0.0, 4.0, 4.0)
    sem = _quadro_recorte(r3d, rid, camera=cam, antes=(chao,))
    com = _quadro_recorte(r3d, rid, camera=cam, antes=(chao,), sombra=1.0)
    y, x = np.unravel_index(np.argmax(sem.sum(axis=2) - com.sum(axis=2)), sem.shape[:2])
    assert int(sem[y, x].sum()) - int(com[y, x].sum()) > 100  # escureceu bem
    assert tuple(sem[5, 5]) == tuple(com[5, 5])  # longe dela, nada muda
