# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Projecao e FilaProfundidade (ROADMAP M20): ida e volta tela<->mundo nos tres modos, o 3/4
igual ao do Ryoiki, lote = escalar, a ordem da fila e Zero-GC no caminho quente."""
from __future__ import annotations

import gc
import math

import numpy as np
import pytest

from ouroboros.core.projecao import (
    DE_CIMA, ISOMETRICA, MODOS, TRES_QUARTOS, FilaProfundidade, Projecao,
)


def _proj(modo):
    return Projecao(modo, centro=(120.0, -40.0), tela=(800, 600), zoom=1.7)


@pytest.mark.parametrize("modo", MODOS)
def test_ida_e_volta_tela_mundo(modo):
    p = _proj(modo)
    rng = np.random.default_rng(3)
    for x, y, z in rng.uniform(-500, 500, (50, 3)):
        sx, sy = p.tela_de(x, y, z)
        mx, my = p.mundo_de(sx, sy, z)  # a inversa no plano da altura z
        assert mx == pytest.approx(x, abs=1e-9) and my == pytest.approx(y, abs=1e-9)
        if modo != DE_CIMA:
            mx0, my0 = p.mundo_de(sx, sy)  # no chao cai em outro ponto: a altura sobe na tela
            assert z < 1e-6 or (mx0, my0) != pytest.approx((x, y))


def test_centro_cai_no_meio_da_tela():
    for modo in MODOS:
        p = _proj(modo)
        assert p.tela_de(120.0, -40.0) == pytest.approx((400.0, 300.0))


def test_tres_quartos_e_o_do_ryoiki():
    """Mesmas contas de Ryoiki/ryoiki/movimento.py (ESCALA_Y = 0.62, zoom 1)."""
    p = Projecao(TRES_QUARTOS, centro=(500.0, 300.0), tela=(960, 540))
    x, y, z = 640.0, 410.0, 26.0
    esperado = (x - 500.0 + 480.0, (y - 300.0) * 0.62 - z + 270.0)
    assert p.tela_de(x, y, z) == pytest.approx(esperado)
    sx, sy = 700.0, 100.0
    assert p.mundo_de(sx, sy) == pytest.approx((sx + 500.0 - 480.0, (sy - 270.0) / 0.62 + 300.0))


def test_de_cima_ignora_a_altura_e_isometrica_gira():
    cima = Projecao(DE_CIMA, tela=(100, 100))
    assert cima.tela_de(10, 20, 0) == cima.tela_de(10, 20, 999)
    iso = Projecao(ISOMETRICA, tela=(0, 0))
    # andar em +x desce para a direita, em +y desce para a esquerda (o losango 2:1)
    ax, ay = iso.tela_de(10, 0)
    bx, by = iso.tela_de(0, 10)
    assert ax > 0 and bx < 0 and ay == pytest.approx(by) and ay == pytest.approx(ax * 0.5)
    assert iso.tela_de(0, 0, 10)[1] == pytest.approx(-10.0)  # a altura sobe


def test_profundidade_ordena_por_quem_esta_mais_perto():
    p = Projecao(TRES_QUARTOS)
    assert p.profundidade(0, 10) > p.profundidade(999, 5)  # no 3/4 so o y importa
    iso = Projecao(ISOMETRICA)
    assert iso.profundidade(10, 10) > iso.profundidade(15, 0)  # na iso, x + y
    p.cx, p.zoom = 500.0, 3.0
    assert p.profundidade(0, 10) == Projecao(TRES_QUARTOS).profundidade(0, 10)  # nao depende da camera


def test_elipse_e_sombra_no_chao():
    p = Projecao(TRES_QUARTOS, zoom=2.0)
    assert p.eixos_elipse_chao(10) == pytest.approx((20.0, 20.0 * 0.62))
    out = np.zeros((16, 2))
    pts = p.pontos_elipse_chao(30, 40, 10, out=out)
    assert pts is out
    cx, cy = p.tela_de(30, 40)
    rx, ry = p.eixos_elipse_chao(10)
    assert np.allclose(((out[:, 0] - cx) / rx) ** 2 + ((out[:, 1] - cy) / ry) ** 2, 1.0)
    sx, sy, rx0, ry0, f0 = p.sombra(30, 40, 0.0, 10)
    _, sy2, rx2, _, f2 = p.sombra(30, 40, 80.0, 10)
    assert (sx, sy) == pytest.approx((cx, cy)) and sy2 == pytest.approx(sy)  # fica no chao
    assert f0 == pytest.approx(1.0) and f2 < f0 and rx2 < rx0  # no alto encolhe e clareia
    iso = Projecao(ISOMETRICA)
    assert iso.eixos_elipse_chao(10) == pytest.approx((10.0, 5.0))


@pytest.mark.parametrize("modo", MODOS)
def test_lote_igual_ao_escalar(modo):
    p = _proj(modo)
    rng = np.random.default_rng(7)
    n = 40
    x, y, z = rng.uniform(-300, 300, n), rng.uniform(-300, 300, n), rng.uniform(0, 90, n)
    sx, sy = np.zeros(n + 5), np.zeros(n + 5)  # capacidade maior que n
    p.tela_de_lote(x, y, z, sx, sy, n)
    for i in range(n):
        assert (sx[i], sy[i]) == pytest.approx(p.tela_de(x[i], y[i], z[i]))
    p.tela_de_lote(x, y, 12.0, sx, sy)  # z numero
    assert (sx[3], sy[3]) == pytest.approx(p.tela_de(x[3], y[3], 12.0))
    p.tela_de_lote(x, y, None, sx, sy)  # z None = chao
    assert (sx[3], sy[3]) == pytest.approx(p.tela_de(x[3], y[3]))
    wx, wy = np.zeros(n), np.zeros(n)
    p.mundo_de_lote(sx, sy, wx, wy, n)
    assert np.allclose(wx, x) and np.allclose(wy, y)
    prof = np.zeros(n)
    p.profundidade_lote(x, y, prof)
    assert prof[5] == pytest.approx(p.profundidade(x[5], y[5]))


def test_modo_invalido_e_troca_de_modo():
    with pytest.raises(ValueError):
        Projecao("perspectiva")
    p = Projecao(TRES_QUARTOS)
    p.modo = ISOMETRICA
    assert p.achatamento == pytest.approx(0.5)
    p.escala_iso = 0.6
    assert p.achatamento == pytest.approx(0.6)


def test_fila_ordena_por_y_depois_z_depois_camada():
    f = FilaProfundidade(8)
    f.adicionar(1, 50.0)
    f.adicionar(2, 10.0)
    f.adicionar(3, 50.0, z=30.0)  # mesmo y, mais alto: por cima
    f.adicionar(4, 50.0, z=0.0, camada=1)  # mesmo y e z do 1, camada maior: depois dele
    f.adicionar(5, -5.0, z=99.0)
    assert f.ordenar().tolist() == [5, 2, 1, 4, 3]
    f.limpar()
    assert len(f) == 0 and f.ordenar().tolist() == []


def test_fila_cheia_recusa_e_avisa():
    f = FilaProfundidade(2)
    assert f.adicionar(1, 0.0) and f.adicionar(2, 1.0)
    assert not f.adicionar(3, 2.0) and f.transbordou
    assert f.ordenar().tolist() == [1, 2]


def test_caminho_quente_nao_dispara_o_coletor():
    """Zero-GC: lote, escalar sem tupla, elipse com `out` e a fila, quadro apos quadro, nao
    disparam coleta. O controle prova que a sonda funciona."""
    p = Projecao(ISOMETRICA, tela=(960, 540))
    n = 500
    rng = np.random.default_rng(1)
    x, y, z = rng.uniform(0, 900, n), rng.uniform(0, 600, n), rng.uniform(0, 50, n)
    sx, sy, prof = np.zeros(n), np.zeros(n), np.zeros(n)
    elipse = np.zeros((20, 2))
    f = FilaProfundidade(n)
    p.reservar(n)
    p.pontos_elipse_chao(0, 0, 1, out=elipse)  # a tabela de seno/cosseno nasce aqui
    coletas = []

    def sonda(fase, info):
        if fase == "start":
            coletas.append(info)

    gc.collect()
    gc.callbacks.append(sonda)
    try:
        for quadro in range(300):
            p.cx = quadro * 0.5
            p.tela_de_lote(x, y, z, sx, sy)
            p.mundo_de_lote(sx, sy, x, y)
            p.profundidade_lote(x, y, prof)
            f.limpar()
            for i in range(0, n, 5):
                f.adicionar(i, prof[i], z[i], i & 1)
            f.ordenar()
            p.pontos_elipse_chao(10.0, 20.0, 8.0, 0.0, out=elipse)
            for i in range(20):
                p.tela_x(x[i], y[i])
                p.tela_y(x[i], y[i], z[i])
                p.profundidade(x[i], y[i])
        sem_lixo = len(coletas)
        lixo = [[k] for k in range(50000)]
        assert lixo and len(coletas) > sem_lixo
    finally:
        gc.callbacks.remove(sonda)
    assert sem_lixo == 0
    assert not math.isnan(sx[0])
