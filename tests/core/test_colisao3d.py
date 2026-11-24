# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""ROADMAP M21 passo 1: colisao 3D (primitivas, relevo, mundo com grade, movimento)."""
from __future__ import annotations

import gc
import math

import numpy as np
import pytest

from ouroboros.core.colisao3d import (
    AABB,
    NENHUMA,
    RELEVO,
    Capsula,
    Esfera,
    MundoColisao3D,
    Raio,
    Relevo,
    ResultadoMovimento,
    ResultadoRaio,
    contato,
    raio_triangulo,
    raycast,
    sobrepoe,
)

# ===================================================================== primitivas


def test_aabb_de_centro_e_contem():
    c = AABB.de_centro((1, 2, 3), (0.5, 1, 1.5))
    assert c.minimo == (0.5, 1, 1.5) and c.maximo == (1.5, 3, 4.5)
    assert c.centro == (1, 2, 3)
    assert c.contem((1, 2, 3)) and not c.contem((2, 2, 3))


def test_capsula_em_pe_vai_da_sola_ao_topo():
    c = Capsula.em_pe((1, 0, 2), 1.8, 0.3)
    assert c.a == (1, 0.3, 2) and c.b == pytest.approx((1, 1.5, 2))
    baixa = Capsula.em_pe((0, 0, 0), 0.4, 0.3)  # mais baixa que o diametro: vira esfera
    assert baixa.a == baixa.b


def test_raio_normaliza_e_recusa_direcao_nula():
    r = Raio((0, 0, 0), (0, 0, 5))
    assert r.direcao == (0, 0, 1) and r.ponto(2) == (0, 0, 2)
    with pytest.raises(ValueError):
        Raio((0, 0, 0), (0, 0, 0))


@pytest.mark.parametrize("a,b,esperado", [
    (AABB((0, 0, 0), (1, 1, 1)), AABB((1, 1, 1), (2, 2, 2)), True),  # encostando no canto
    (AABB((0, 0, 0), (1, 1, 1)), AABB((1.01, 0, 0), (2, 1, 1)), False),
    (Esfera((0, 0, 0), 1), Esfera((1.9, 0, 0), 1), True),
    (Esfera((0, 0, 0), 1), Esfera((2.1, 0, 0), 1), False),
    (Esfera((2, 2, 0.5), 1.0), AABB((0, 0, 0), (1, 1, 1)), False),  # canto: distancia sqrt(2) > 1
    (Esfera((1.6, 1.6, 0.5), 1.0), AABB((0, 0, 0), (1, 1, 1)), True),
    (Capsula((0, 0, 0), (0, 4, 0), 0.5), Capsula((0.9, 2, -3), (0.9, 2, 3), 0.5), True),  # cruzadas
    (Capsula((0, 0, 0), (0, 4, 0), 0.5), Capsula((1.1, 2, -3), (1.1, 2, 3), 0.5), False),
    (Capsula((-3, 1.4, 0.5), (3, 1.4, 0.5), 0.5), AABB((0, 0, 0), (1, 1, 1)), True),  # deitada em cima
    (Capsula((-3, 1.6, 0.5), (3, 1.6, 0.5), 0.5), AABB((0, 0, 0), (1, 1, 1)), False),
    (Capsula((0, 0, 0), (0, 3, 0), 0.5), Esfera((0, 3.9, 0), 0.5), True),  # na ponta de cima
])
def test_sobrepoe_nos_dois_sentidos(a, b, esperado):
    assert sobrepoe(a, b) is esperado
    assert sobrepoe(b, a) is esperado


def _dist_ponto_aabb(p, caixa: AABB) -> float:
    q = np.clip(p, caixa.minimo, caixa.maximo)
    return float(np.linalg.norm(p - q))


def test_capsula_contra_caixa_bate_com_a_forca_bruta():
    """O ponto do eixo mais perto da caixa (projecoes alternadas) contra 2000 amostras."""
    rng = np.random.default_rng(7)
    caixa = AABB((-1, 0, -0.5), (1, 2, 0.5))
    for _ in range(300):
        a, b = rng.uniform(-3, 3, 3), rng.uniform(-3, 3, 3)
        r = float(rng.uniform(0.1, 1.0))
        amostras = a + np.linspace(0, 1, 2000)[:, None] * (b - a)
        minima = min(_dist_ponto_aabb(p, caixa) for p in amostras)
        if abs(minima - r) < 0.01:
            continue  # rente demais para a amostragem decidir
        assert sobrepoe(Capsula(tuple(a), tuple(b), r), caixa) is (minima < r)


@pytest.mark.parametrize("corpo", [Esfera((0.3, 0.9, 0.2), 0.5), Capsula((0.4, -0.5, 0.1), (0.6, 1.5, 0.3), 0.4)])
@pytest.mark.parametrize("forma", [AABB((0, 0, 0), (1, 1, 1)), Esfera((0.5, 0.4, 0.5), 0.6),
                                   Capsula((-1, 0.5, 0.5), (2, 0.5, 0.5), 0.3)])
def test_contato_empurra_para_fora(corpo, forma):
    """Um empurrao resolve esfera; capsula torta atravessando uma caixa pode precisar de mais
    de um (o `MundoColisao3D` itera ate 4 vezes por passo) -- e a profundidade cai a cada um."""
    assert contato(corpo, forma) is not None
    anterior = math.inf
    for _ in range(4):
        c = contato(corpo, forma)
        if c is None:
            break
        (nx, ny, nz), prof = c
        assert 0 < prof < anterior and math.isclose(nx * nx + ny * ny + nz * nz, 1.0, rel_tol=1e-6)
        anterior = prof
        d = (nx * (prof + 1e-4), ny * (prof + 1e-4), nz * (prof + 1e-4))
        if isinstance(corpo, Esfera):
            corpo = Esfera(tuple(np.add(corpo.centro, d)), corpo.raio)
        else:
            corpo = Capsula(tuple(np.add(corpo.a, d)), tuple(np.add(corpo.b, d)), corpo.raio)
    assert contato(corpo, forma) is None


def test_contato_raso_resolve_num_empurrao_so():
    for corpo in (Esfera((0.5, 1.3, 0.5), 0.4), Capsula((-1, 1.2, 0.5), (2, 1.3, 0.6), 0.3),
                  Capsula((1.2, 0.2, 0.5), (1.25, 2.5, 0.5), 0.3)):
        (n, prof) = contato(corpo, AABB((0, 0, 0), (1, 1, 1)))
        d = np.multiply(n, prof + 1e-6)
        movido = (Esfera(tuple(np.add(corpo.centro, d)), corpo.raio) if isinstance(corpo, Esfera)
                  else Capsula(tuple(np.add(corpo.a, d)), tuple(np.add(corpo.b, d)), corpo.raio))
        assert contato(movido, AABB((0, 0, 0), (1, 1, 1))) is None


def test_contato_com_o_centro_dentro_da_caixa_sai_pela_face_mais_perto():
    (n, prof) = contato(Esfera((0.5, 0.9, 0.5), 0.2), AABB((0, 0, 0), (1, 1, 1)))
    assert n == (0, 1, 0) and prof == pytest.approx(0.3)


def test_raycast_na_caixa():
    caixa = AABB((-1, 0, 4), (1, 2, 5))
    t, n = raycast(Raio((0, 1, 0), (0, 0, 1)), caixa)
    assert t == pytest.approx(4) and n == (0, 0, -1)
    t, n = raycast(Raio((0, 5, 4.5), (0, -1, 0)), caixa)
    assert t == pytest.approx(3) and n == (0, 1, 0)
    assert raycast(Raio((0, 1, 0), (0, 0, 1)), caixa, dist_max=3.9) is None
    assert raycast(Raio((0, 1, 0), (0, 0, -1)), caixa) is None
    assert raycast(Raio((0, 1, 4.5), (1, 0, 0)), caixa) == (0.0, (-1.0, -0.0, -0.0))  # de dentro: t = 0


def test_raycast_na_esfera():
    t, n = raycast(Raio((0, 0, -5), (0, 0, 1)), Esfera((0, 0, 0), 1))
    assert t == pytest.approx(4) and n == pytest.approx((0, 0, -1))
    assert raycast(Raio((0, 1.01, -5), (0, 0, 1)), Esfera((0, 0, 0), 1)) is None


def test_raycast_na_capsula_corpo_pontas_e_eixo():
    c = Capsula((0, 0, 0), (0, 4, 0), 0.5)
    t, n = raycast(Raio((-5, 2, 0), (1, 0, 0)), c)  # no cilindro
    assert t == pytest.approx(4.5) and n == pytest.approx((-1, 0, 0))
    t, n = raycast(Raio((0, 10, 0), (0, -1, 0)), c)  # paralelo ao eixo: a ponta de cima
    assert t == pytest.approx(5.5) and n == pytest.approx((0, 1, 0))
    t, _ = raycast(Raio((0, -10, 0), (0, 1, 0)), c)  # de baixo
    assert t == pytest.approx(9.5)
    t, n = raycast(Raio((-5, 4.3, 0), (1, 0, 0)), c)  # acima do cilindro, na meia-esfera de cima
    assert t == pytest.approx(5 - math.sqrt(0.25 - 0.09)) and n[1] > 0
    assert raycast(Raio((-5, 4.6, 0), (1, 0, 0)), c) is None
    assert raycast(Raio((0, 2, 0), (1, 0, 0)), c)[0] == 0.0  # de dentro


def test_raycast_bate_com_amostragem_densa():
    """O t do raycast e o primeiro ponto do raio dentro da forma (amostrado de 0,001 em 0,001)."""
    rng = np.random.default_rng(3)
    formas = [AABB((-1, -0.5, -0.7), (0.8, 1.2, 0.6)), Esfera((0.2, 0.1, -0.3), 0.9),
              Capsula((-0.8, -0.4, 0.2), (0.7, 0.9, -0.4), 0.45)]
    ts = np.arange(0, 8, 0.001)
    for forma in formas:
        for _ in range(40):
            o = rng.uniform(-4, 4, 3)
            alvo = rng.uniform(-0.5, 0.5, 3)
            raio = Raio(tuple(o), tuple(alvo - o))
            pts = np.asarray(raio.origem) + ts[:, None] * np.asarray(raio.direcao)
            dentro = [contato(Esfera(tuple(p), 1e-9), forma) is not None for p in pts[::10]]
            primeiro = next((k * 10 for k, v in enumerate(dentro) if v), None)
            hit = raycast(raio, forma, 8.0)
            if primeiro is None:
                assert hit is None
            else:
                assert hit is not None and abs(hit[0] - ts[primeiro]) < 0.012


def test_raio_triangulo_dos_dois_lados():
    v0, v1, v2 = (0, 0, 0), (1, 0, 0), (0, 0, 1)
    t, n = raio_triangulo(Raio((0.2, 3, 0.2), (0, -1, 0)), v0, v1, v2)
    assert t == pytest.approx(3) and n == pytest.approx((0, 1, 0))
    t, n = raio_triangulo(Raio((0.2, -3, 0.2), (0, 1, 0)), v0, v1, v2)
    assert t == pytest.approx(3) and n == pytest.approx((0, -1, 0))
    assert raio_triangulo(Raio((0.8, 3, 0.8), (0, -1, 0)), v0, v1, v2) is None


# ===================================================================== relevo


def _relevo_ondulado() -> Relevo:
    return Relevo.de_funcao(lambda x, z: math.sin(x * 0.7) + 0.5 * math.cos(z * 0.9), -5, 5, -4, 6, 1.0)


def test_relevo_nos_vertices_e_no_plano_de_cada_triangulo():
    r = Relevo(np.array([[0.0, 1.0], [2.0, 5.0]]), 0.0, 0.0, 1.0)  # a=0 b=1 (x) d=2 (z) c=5
    assert r.altura(0, 0) == 0 and r.altura(1, 0) == 1 and r.altura(0, 1) == 2 and r.altura(1, 1) == 5
    assert r.altura(0.75, 0.25) == pytest.approx(0 + 1 * 0.75 + 4 * 0.25)  # triangulo (a, b, c)
    assert r.altura(0.25, 0.75) == pytest.approx(0 + 3 * 0.25 + 2 * 0.75)  # triangulo (a, c, d)
    assert r.altura(-10, -10) == 0 and r.altura(10, 10) == 5  # fora: repete a borda
    assert r.celulas == (1, 1) and r.limites == (0, 1, 0, 1)


def test_relevo_normal_de_uma_rampa():
    r = Relevo.de_funcao(lambda x, z: 0.5 * x, 0, 4, 0, 4, 1.0)
    n = r.normal(1.3, 2.2)
    assert n == pytest.approx((-0.5 / math.sqrt(1.25), 1 / math.sqrt(1.25), 0))


def test_relevo_raycast_vertical_acha_a_altura_e_bate_com_os_triangulos():
    r = _relevo_ondulado()
    rng = np.random.default_rng(1)
    for x, z in rng.uniform([-5, -4], [5, 6], (50, 2)):
        t, n = r.raycast((x, 10.0, z), (0, -1, 0))
        assert 10.0 - t == pytest.approx(r.altura(x, z), abs=1e-9)
        assert n[1] > 0


def test_relevo_raycast_obliquo_contra_forca_bruta():
    r = _relevo_ondulado()
    rng = np.random.default_rng(2)
    tris = []
    nx, nz = r.celulas
    for j in range(nz):
        for i in range(nx):
            a, b, c, d = r.vertice(i, j), r.vertice(i + 1, j), r.vertice(i + 1, j + 1), r.vertice(i, j + 1)
            tris += [(a, b, c), (a, c, d)]
    for _ in range(60):
        o = (float(rng.uniform(-8, 8)), float(rng.uniform(2, 5)), float(rng.uniform(-7, 9)))
        alvo = (float(rng.uniform(-5, 5)), float(rng.uniform(-2, 0)), float(rng.uniform(-4, 6)))
        raio = Raio(o, tuple(np.subtract(alvo, o)))
        bruto = min((h[0] for t in tris if (h := raio_triangulo(raio, *t)) is not None), default=None)
        hit = r.raycast(raio.origem, raio.direcao)
        if bruto is None:
            assert hit is None
        else:
            assert hit is not None and hit[0] == pytest.approx(bruto, abs=1e-9)


def test_relevo_valida_entrada():
    with pytest.raises(ValueError):
        Relevo(np.zeros(4), 0, 0, 1)
    with pytest.raises(ValueError):
        Relevo(np.zeros((2, 2)), 0, 0, 0)


# ===================================================================== mundo: cenario


def test_mundo_adiciona_remove_e_reusa_ids():
    m = MundoColisao3D((-10, -10, 10, 10), max_formas=3)
    a = m.adicionar(AABB((0, 0, 0), (1, 1, 1)))
    b = m.adicionar_esfera((3, 1, 3), 0.5)
    c = m.adicionar_capsula((5, 0, 5), (5, 2, 5), 0.3)
    assert len(m) == 3 and m.forma(b) == Esfera((3, 1, 3), 0.5)
    with pytest.raises(OverflowError):
        m.adicionar_esfera((0, 0, 0), 1)
    m.remover(b)
    assert len(m) == 2
    with pytest.raises(KeyError):
        m.forma(b)
    assert m.adicionar_esfera((0, 5, 0), 1) == b
    m.atualizar(a, AABB((0, 0, 0), (2, 2, 2)))
    assert m.forma(a) == AABB((0, 0, 0), (2, 2, 2)) and m.forma(c).raio == pytest.approx(0.3)
    with pytest.raises(ValueError):
        m.atualizar(a, AABB((1, 0, 0), (0, 1, 1)))
    with pytest.raises(ValueError):
        MundoColisao3D((0, 0, 0, 0))


def _cena_aleatoria(seed: int, n: int = 150):
    rng = np.random.default_rng(seed)
    m = MundoColisao3D((-20, -20, 20, 20), tamanho_celula=3.0)
    formas = []
    for _ in range(n):
        p = rng.uniform([-22, 0, -22], [22, 4, 22])  # algumas fora da grade, de proposito
        tipo = rng.integers(3)
        if tipo == 0:
            f = AABB(tuple(p), tuple(p + rng.uniform(0.2, 5.0, 3)))
        elif tipo == 1:
            f = Esfera(tuple(p), float(rng.uniform(0.2, 2.0)))
        else:
            f = Capsula(tuple(p), tuple(p + rng.uniform(-3, 3, 3)), float(rng.uniform(0.1, 1.0)))
        formas.append((m.adicionar(f, camada=1 << int(rng.integers(2))), f))
    return m, formas, rng


def test_broadphase_nao_perde_nem_inventa_pares():
    m, formas, rng = _cena_aleatoria(11)
    saida = [0] * 256
    for _ in range(200):
        c = tuple(rng.uniform(-21, 21, 3))
        q = Esfera(c, float(rng.uniform(0.1, 3)))
        n = m.consultar(q, saida)
        assert sorted(saida[:n]) == sorted(fid for fid, f in formas if sobrepoe(q, f))
        caixa = AABB(c, tuple(np.add(c, rng.uniform(0.1, 4, 3))))
        n = m.consultar(caixa, saida)
        assert sorted(saida[:n]) == sorted(fid for fid, f in formas if sobrepoe(caixa, f))


def test_raycast_do_mundo_e_o_menor_dos_raycasts_individuais():
    m, formas, rng = _cena_aleatoria(12)
    res = ResultadoRaio()
    for _ in range(300):
        o = tuple(rng.uniform([-19, -1, -19], [19, 6, 19]))
        d = tuple(rng.normal(size=3))
        dist = float(rng.uniform(1, 40))
        hits = [(h[0], fid) for fid, f in formas if (h := raycast(Raio(o, d), f, dist)) is not None]
        m.raycast(o, d, dist, resultado=res)
        if not hits:
            assert not res.acertou and res.forma == NENHUMA
        else:
            assert res.acertou and res.distancia == pytest.approx(min(hits)[0], abs=1e-9)


def test_mascara_filtra_camadas():
    m = MundoColisao3D((-10, -10, 10, 10))
    m.adicionar(AABB((-1, 0, 3), (1, 2, 3.2)), camada=2)  # vidro: so bloqueia o corpo
    assert m.raycast((0, 1, 0), (0, 0, 1)).acertou
    assert not m.raycast((0, 1, 0), (0, 0, 1), mascara=1).acertou
    assert m.tem_visao((0, 1, 0), (0, 1, 8), mascara=1)
    assert not m.tem_visao((0, 1, 0), (0, 1, 8))
    assert not m.sobrepoe_esfera((0, 1, 3.1), 0.2, mascara=1) and m.sobrepoe_esfera((0, 1, 3.1), 0.2)


def test_tem_visao_com_morro_no_meio():
    m = MundoColisao3D((-10, -10, 10, 10))
    m.definir_relevo(Relevo.de_funcao(lambda x, z: 3.0 * math.exp(-x * x), -10, 10, -10, 10, 0.5))
    assert not m.tem_visao((-6, 1, 0), (6, 1, 0))
    assert m.tem_visao((-6, 5, 0), (6, 5, 0))
    assert not m.tem_visao((-6, 1, 0), (6, 1, 0), relevo=True) and m.tem_visao((-6, 1, 0), (6, 1, 0), relevo=False)
    r = m.raycast((-6, 1, 0), (1, 0, 0))
    assert r.forma == RELEVO and r.ponto[1] == pytest.approx(1.0)


# ===================================================================== mundo: movimento


def _sala() -> MundoColisao3D:
    m = MundoColisao3D((-10, -10, 10, 10), tamanho_celula=2.0)
    m.adicionar(AABB((-10, -1, -10), (10, 0, 10)))  # chao
    m.adicionar(AABB((-5, 0, 3), (5, 3, 3.2)))  # parede a frente (z = 3)
    m.construir()
    return m


def test_parede_para_o_corpo_no_raio():
    r = _sala().mover_capsula((0, 0, 0), 1.7, 0.3, (0, 0, 5))
    assert r.posicao[2] == pytest.approx(2.7, abs=1e-3)
    assert r.bateu and r.posicao[0] == pytest.approx(0) and r.posicao[1] == pytest.approx(0)


def test_andar_na_diagonal_desliza_na_parede():
    m = _sala()
    pe = (0.0, 0.0, 2.6)
    for _ in range(10):
        r = m.mover_capsula(pe, 1.7, 0.3, (0.1, 0, 0.1))
        pe = tuple(r.posicao)
    assert pe[0] == pytest.approx(1.0, abs=1e-3) and pe[2] == pytest.approx(2.7, abs=1e-3)


def test_passo_grande_nao_atravessa_parede_fina():
    m = MundoColisao3D((-10, -10, 10, 10))
    m.adicionar(AABB((-5, 0, 3), (5, 3, 3.05)))
    r = m.mover_esfera((0, 1, 0), 0.4, (0, 0, 9))
    assert r.posicao[2] < 3.0


def test_gravidade_assenta_no_chao_e_zera_a_queda():
    m = _sala()
    pe, vy = (0.0, 2.0, 0.0), 0.0
    for _ in range(120):
        vy -= 9.8 / 60
        r = m.mover_capsula(pe, 1.7, 0.3, (0, vy / 60, 0))
        pe = tuple(r.posicao)
        _, vy, _ = r.ajustar_velocidade(0, vy, 0)
    assert pe[1] == pytest.approx(0.0, abs=1e-3) and r.no_chao and vy == 0.0
    assert r.normal_chao == pytest.approx([0, 1, 0])


def test_parado_em_cima_do_chao_conta_como_no_chao_pela_sonda():
    m = _sala()
    assert m.mover_capsula((0, 0.01, 0), 1.7, 0.3, (0, 0, 0)).no_chao
    assert not m.mover_capsula((0, 0.5, 0), 1.7, 0.3, (0, 0, 0)).no_chao
    assert not m.mover_capsula((0, 0.01, 0), 1.7, 0.3, (0, 0, 0), sonda_chao=0.0).no_chao


def test_ajustar_velocidade_mantem_o_que_corre_pela_parede():
    r = _sala().mover_capsula((0, 0, 2.6), 1.7, 0.3, (0.1, 0, 0.3))
    vx, vy, vz = r.ajustar_velocidade(2.0, 0.0, 3.0)
    assert (vx, vy) == (pytest.approx(2.0), pytest.approx(0.0)) and vz == pytest.approx(0.0, abs=1e-9)


def test_rampa_suave_se_sobe_e_ingreme_nao():
    def empurrar(centro, raio):
        m = MundoColisao3D((-10, -10, 10, 10))
        m.adicionar(Esfera(centro, raio))
        pe = (0.0, 0.0, 0.0)
        for _ in range(60):
            pe = tuple(m.mover_capsula(pe, 1.7, 0.3, (0, 0, 0.05)).posicao)
        return pe

    assert empurrar((0, -0.5, 3), 1.0)[1] == pytest.approx(0.0)  # normal ~52 graus: parede
    assert empurrar((0, -1.5, 3), 2.0)[1] > 0.1  # normal ~39 graus: chao, sobe


def test_anda_sobre_o_relevo():
    m = MundoColisao3D((-10, -10, 10, 10))
    rel = Relevo.de_funcao(lambda x, z: 0.3 * x, -10, 10, -10, 10, 1.0)
    m.definir_relevo(rel)
    pe = (0.0, 0.0, 0.0)
    for _ in range(40):
        r = m.mover_capsula(pe, 1.7, 0.3, (0.1, -0.05, 0))
        pe = tuple(r.posicao)
    assert pe[1] == pytest.approx(rel.altura(pe[0], pe[2])) and r.no_chao
    assert r.normal_chao[0] < 0 and r.normal_chao[1] > 0.9
    bola = m.mover_esfera((2.0, -3.0, 0.0), 0.5, (0, 0, 0))
    assert bola.posicao[1] == pytest.approx(rel.altura(2.0, 0.0) + 0.5)


def test_relevo_e_formas_juntos_no_raycast():
    m = _sala()
    m.definir_relevo(Relevo(np.full((3, 3), -0.5), -10, -10, 10))
    r = m.raycast((0, 1, 0), (0, -1, 0))
    assert r.forma == 0 and r.distancia == pytest.approx(1.0)  # o chao-caixa vem antes do relevo
    assert m.raycast((0, 1, 0), (0, -1, 0), mascara=0).forma == RELEVO


def test_caminho_quente_nao_dispara_o_coletor():
    """Zero-GC: 5 mil movimentos + raios com resultados reaproveitados nao disparam nenhuma
    coleta. O controle prova que a sonda funciona: alocar listas dispara."""
    m, _, _ = _cena_aleatoria(5, n=80)
    m.definir_relevo(Relevo.de_funcao(lambda x, z: 0.1 * x, -20, 20, -20, 20, 2.0))
    m.construir()
    rm, rr = ResultadoMovimento(), ResultadoRaio()
    coletas = []

    def sonda(fase, info):
        if fase == "start":
            coletas.append(info)

    gc.collect()
    gc.callbacks.append(sonda)
    try:
        pe = (0.0, 0.0, 0.0)
        for _ in range(5000):
            m.mover_capsula(pe, 1.7, 0.3, (0.01, -0.05, 0.02), resultado=rm)
            m.raycast((0.1, 1.6, 0.2), (1.0, -0.1, 0.5), 30.0, resultado=rr)
        sem_lixo = len(coletas)
        lixo = [[k] for k in range(50000)]
        assert lixo and len(coletas) > sem_lixo
    finally:
        gc.callbacks.remove(sonda)
    assert sem_lixo == 0
