# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ROADMAP M21 passo 1: construtores de malha (ouroboros.interfaces.malhas3d)."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
import pytest

from ouroboros.core.colisao3d import AABB, Raio, Relevo, raio_triangulo
from ouroboros.interfaces import malhas3d as m
from ouroboros.interfaces.renderer3d import translacao_e_giro_y

COR = (200, 100, 50)


def _fechada_e_consistente(malha: m.Malha) -> bool:
    """Toda aresta orientada aparece uma vez e a inversa tambem: solido fechado, com todos os
    triangulos girando para o mesmo lado (nenhum virado ao contrario do vizinho)."""
    v = np.round(malha.posicoes.astype(np.float64), 5)
    arestas = Counter()
    for t in v.reshape(-1, 3, 3):
        p = [tuple(x) for x in t]
        if len(set(p)) < 3:
            continue  # degenerado (ex.: topo de cone)
        for i in range(3):
            arestas[(p[i], p[(i + 1) % 3])] += 1
    return all(n == 1 and arestas.get((b, a)) == 1 for (a, b), n in arestas.items())


def _para_fora(malha: m.Malha, centro) -> bool:
    meio = malha.posicoes.reshape(-1, 3, 3).mean(axis=1)
    return bool(np.all(np.einsum("ij,ij->i", malha.normais(), meio - np.asarray(centro)) > -1e-6))


@pytest.mark.parametrize("malha,centro,tris", [
    (m.caixa((0, 0, 0), (2, 1, 3), COR), (1, 0.5, 1.5), 12),
    (m.bloco((0, 0, 0), 2.0, 1.0, 0.6, 0.8, COR), (0, 1, 0), 12),
    (m.cilindro((1, 0, 1), 0.5, 2.0, COR, lados=7), (1, 1, 1), 28),
    (m.cilindro((0, 0, 0), 1.0, 2.0, COR, lados=6, raio_topo=0.4), (0, 1, 0), 24),
    (m.cone((0, 0, 0), 1.0, 2.0, COR, lados=5), (0, 0.6, 0), 10),
    (m.esfera((0, 1, 0), 2.0, COR, subdivisoes=0), (0, 1, 0), 20),
    (m.esfera((0, 1, 0), 2.0, COR, subdivisoes=2), (0, 1, 0), 320),
])
def test_solidos_fechados_e_virados_para_fora(malha, centro, tris):
    assert malha.triangulos == tris
    assert _fechada_e_consistente(malha)
    assert _para_fora(malha, centro)


def test_arrays_no_formato_do_renderer():
    c = m.caixa((0, 0, 0), (1, 1, 1), COR, emissivo=True)
    assert c.posicoes.dtype == np.float32 and c.posicoes.shape == (36, 3)
    assert c.cores.shape == (36, 3) and np.all(c.cores == COR)
    assert c.emissivo.dtype == np.bool_ and c.emissivo.all()
    with pytest.raises(ValueError):
        m.Malha(np.zeros((4, 3)), np.zeros((4, 3)))


def test_plano_virado_para_cima_com_cor_por_ladrilho():
    p = m.plano(0, 4, 0, 2, lambda x, z: (int(x * 10), 0, int(z * 10)), y=0.5, passo=1.0)
    assert p.triangulos == 16
    assert np.allclose(p.normais(), [0, 1, 0])
    assert np.allclose(p.posicoes[:, 1], 0.5)
    assert tuple(p.cores[0]) == (5, 0, 5) and tuple(p.cores[-1]) == (35, 0, 15)
    assert m.plano(0, 1, 0, 1, COR).triangulos == 2


def test_terreno_e_o_mesmo_chao_que_o_relevo():
    """O pe pisa no que se ve: raio vertical na malha do terreno == Relevo.altura."""
    rel = Relevo.de_funcao(lambda x, z: math.sin(x) + 0.4 * math.cos(1.3 * z), -3, 3, -2, 2, 0.75)
    t = m.terreno(rel, COR)
    nx, nz = rel.celulas
    assert t.triangulos == 2 * nx * nz
    assert np.all(t.normais()[:, 1] > 0)
    tris = t.posicoes.reshape(-1, 3, 3).astype(np.float64)
    rng = np.random.default_rng(4)
    x0, x1, z0, z1 = rel.limites
    for x, z in rng.uniform([x0, z0], [x1, z1], (30, 2)):
        raio = Raio((x, 10.0, z), (0, -1, 0))
        hits = [h[0] for tri in tris if (h := raio_triangulo(raio, *map(tuple, tri))) is not None]
        assert 10.0 - min(hits) == pytest.approx(rel.altura(x, z), abs=1e-5)


def test_terreno_com_cores_prontas_valida_o_shape():
    rel = Relevo(np.zeros((3, 4)), 0, 0, 1)
    cores = np.zeros((2, 3, 3))
    cores[1, 2] = (9, 9, 9)
    t = m.terreno(rel, cores)
    assert tuple(t.cores[-1]) == (9, 9, 9)
    with pytest.raises(ValueError):
        m.terreno(rel, np.zeros((3, 3, 3)))


def test_disco_virado_para_cima():
    d = m.disco((1, 0.2, 1), 0.5, COR, lados=12)
    assert d.triangulos == 12 and np.allclose(d.normais(), [0, 1, 0])


@pytest.mark.parametrize("contorno", [
    [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)],  # L, anti-horario
    [(0, 3), (1, 3), (1, 1), (3, 1), (3, 0), (0, 0)],  # o mesmo L, horario
    [(0, 0), (2, 0), (2, 2), (0, 2)],
])
def test_extrusao_fecha_e_as_paredes_saem_do_poligono(contorno):
    e = m.extrusao(contorno, 0.0, 2.5, COR)
    assert _fechada_e_consistente(e)
    n = len(contorno)
    assert e.triangulos == 2 * n + 2 * (n - 2)
    assert np.all(e.normais()[2 * n:2 * n + n - 2, 1] > 0.99)  # tampa de cima


def _dentro(p, contorno) -> bool:
    x, z = p
    dentro = False
    for (x1, z1), (x2, z2) in zip(contorno, contorno[1:] + contorno[:1]):
        if (z1 > z) != (z2 > z) and x < x1 + (z - z1) * (x2 - x1) / (z2 - z1):
            dentro = not dentro
    return dentro


@pytest.mark.parametrize("contorno", [
    [(0, 0), (3, 0), (3, 1), (1, 1), (1, 3), (0, 3)],
    [(0, 3), (1, 3), (1, 1), (3, 1), (3, 0), (0, 0)],
])
def test_extrusao_normais_das_paredes_apontam_para_fora(contorno):
    e = m.extrusao(contorno, 0.0, 2.5, COR, tampas=False)
    meio = e.posicoes.reshape(-1, 3, 3).mean(axis=1)
    for c, nrm in zip(meio, e.normais()):
        assert abs(nrm[1]) < 1e-6
        assert not _dentro((c[0] + 0.05 * nrm[0], c[2] + 0.05 * nrm[2]), contorno)
        assert _dentro((c[0] - 0.05 * nrm[0], c[2] - 0.05 * nrm[2]), contorno)


def test_triangular_poligono_cobre_a_area():
    contorno = [(0, 0), (4, 0), (4, 4), (2, 1.5), (0, 4)]  # nao convexo (o "M" invertido)
    tris = m.triangular_poligono(contorno)
    p = np.asarray(contorno)
    def area_tri(a, b, c):
        (ux, uz), (vx, vz) = p[b] - p[a], p[c] - p[a]
        return abs(ux * vz - uz * vx) / 2

    area = sum(area_tri(*t) for t in tris)
    assert len(tris) == 3 and area == pytest.approx(abs(m._area_xz(p)))
    assert len(m.triangular_poligono([(0, 0), (1, 0), (2, 0), (2, 2), (0, 2)])) >= 2  # com ponto colinear
    with pytest.raises(ValueError):
        m.triangular_poligono([(0, 0), (1, 1), (2, 2)])


def test_juntar_transformar_girar_e_caixa_envolvente():
    a = m.caixa((0, 0, 0), (1, 1, 1), COR)
    b = m.esfera((5, 0, 0), 1.0, (1, 2, 3), subdivisoes=0)
    j = a + b
    assert j.triangulos == 32 and tuple(j.cores[-1]) == (1, 2, 3)
    assert m.juntar().triangulos == 0 and (m.Malha.vazia() + a).triangulos == 12
    movida = a.transformada(translacao_e_giro_y(10, 0, 0, math.pi / 2))
    caixa = movida.aabb()
    assert isinstance(caixa, AABB)
    assert np.allclose([*caixa.minimo, *caixa.maximo], [10, 0, -1, 11, 1, 0], atol=1e-6)
    assert _fechada_e_consistente(movida) and _para_fora(movida, (10.5, 0.5, -0.5))
    espelho = np.diag([-1.0, 1, 1, 1])
    assert _para_fora(a.transformada(espelho), (-0.5, 0.5, 0.5))  # espelhar nao vira o solido do avesso
    girado = m.bloco((0, 0, 0), 2.0, 0.5, 0.5, 0.5, COR).girada("z", math.pi / 2, (0, 0, 0))
    assert np.allclose(girado.aabb().minimo, (-2, -0.25, -0.25), atol=1e-6)
    assert np.all(a.com_cor((7, 7, 7)).cores == 7)


def test_de_triangulos_le_o_formato_antigo():
    tris = [((0, 0, 0), (1, 0, 0), (0, 1, 0), (10, 20, 30), True, 2),
            ((0, 0, 1), (1, 0, 1), (0, 1, 1), (40, 50, 60), False, 2)]
    mm = m.Malha.de_triangulos(tris)
    assert mm.triangulos == 2 and mm.emissivo.tolist() == [True] * 3 + [False] * 3
    assert tuple(mm.cores[3]) == (40, 50, 60)
    assert m.Malha.de_triangulos([]).triangulos == 0


class _R3DFalso:
    def __init__(self):
        self.criadas, self.atualizadas = [], []

    def criar_malha(self, posicoes, cores, emissivo=None, dinamica=False):
        self.criadas.append((posicoes.shape, dinamica))
        return 7

    def atualizar_malha(self, malha_id, posicoes, cores, emissivo=None):
        self.atualizadas.append(malha_id)


def test_criar_e_atualizar_no_renderer():
    r = _R3DFalso()
    c = m.caixa((0, 0, 0), (1, 1, 1), COR)
    assert c.criar_em(r, dinamica=True) == 7 and r.criadas == [((36, 3), True)]
    c.atualizar_em(r, 7)
    assert r.atualizadas == [7]
