# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Demo de terror (ROADMAP M21): as regras da lanterna e do vulto, sem placa de video."""
from __future__ import annotations

import math

from games.terror_ps1 import regras


def _mirar_no_vulto(e: regras.Estado) -> None:
    vx, vz = e.vulto
    e.giro = math.atan2(vx - e.x, -(vz - e.z))
    e.inclina = 0.0
    e.feixe = regras.direcao(e.giro, 0.0)


def _segundos(e: regras.Estado, s: float, **kw) -> None:
    for _ in range(int(s * 60)):
        regras.atualizar(e, 1 / 60, kw.get("frente", 0.0), 0.0, 0.0, False)
        if kw.get("mirar"):
            _mirar_no_vulto(e)


def test_iluminado_o_vulto_congela():
    e = regras.Estado()
    _mirar_no_vulto(e)
    antes = e.vulto
    _segundos(e, 5, mirar=True)
    assert e.vulto == antes


def test_no_escuro_ele_chega_mais_perto():
    e = regras.Estado(acesa=False)
    d0 = math.hypot(e.x - e.vulto[0], e.z - e.vulto[1])
    _segundos(e, 3)
    assert math.hypot(e.x - e.vulto[0], e.z - e.vulto[1]) < d0 - 2


def test_olhar_para_o_outro_lado_tambem_e_escuro():
    e = regras.Estado()
    e.giro = math.pi  # de costas para a cena
    e.feixe = regras.direcao(e.giro)
    antes = e.vulto
    _segundos(e, 2)
    assert e.vulto != antes


def test_a_pilha_gasta_acesa_e_recarrega_apagada():
    e = regras.Estado()
    _segundos(e, 10, mirar=True)
    gasta = e.pilha
    assert gasta < 0.9
    regras.atualizar(e, 1 / 60, 0, 0, 0, True)  # apaga
    e.vulto = (100.0, 100.0)  # longe, para nao atrapalhar
    _segundos(e, 5)
    assert e.pilha > gasta


def test_pilha_fraca_faz_a_lanterna_falhar():
    e = regras.Estado(pilha=0.1)
    forcas = set()
    for i in range(240):
        e.tempo = i / 60
        forcas.add(round(regras.forca_da_luz(e), 2))
    assert len(forcas) > 1 and max(forcas) < 1.0


def test_quando_ele_chega_a_noite_recomeca():
    e = regras.Estado(acesa=False)
    _segundos(e, 30)
    assert e.pego > 0 or (e.x, e.z) == regras.INICIO  # pegou (e ja pode ter recomecado)
    _segundos(e, 3)
    assert e.vulto != (e.x, e.z)


def test_nao_atravessa_arvore_nem_pilar():
    e = regras.Estado(x=0.0, z=0.0, acesa=False)
    e.vulto = (100.0, 100.0)
    obstaculo = [(0.0, -2.0, 0.35)]
    for _ in range(120):  # 2 s andando reto contra o tronco
        regras.atualizar(e, 1 / 60, 1.0, 0.0, 0.0, False, obstaculos=obstaculo)
    assert math.hypot(e.x - 0.0, e.z + 2.0) >= 0.35 + regras.RAIO_JOGADOR - 1e-6


def test_o_mouse_olha_e_a_inclinacao_tem_limite():
    e = regras.Estado()
    regras.atualizar(e, 1 / 60, 0, 0, 0, False, olhar=(100.0, 0.0))
    assert e.giro > 0.2
    regras.atualizar(e, 1 / 60, 0, 0, 0, False, olhar=(0.0, -100000.0))
    assert e.inclina == regras.INCLINA_MAX


def test_o_som_do_vulto_vem_do_lado_dele():
    e = regras.Estado(x=0.0, z=0.0, giro=0.0, acesa=False)  # olhando para -z
    e.vulto = (5.0, 0.0)  # a direita
    assert regras.lado_do_vulto(e) > 0.9
    e.vulto = (-5.0, 0.0)
    assert regras.lado_do_vulto(e) < -0.9
    eventos = []
    for _ in range(90):
        regras.atualizar(e, 1 / 60, 0, 0, 0, False)
        eventos += e.eventos
    assert "vulto" in eventos  # no escuro ele anda, e da para ouvir


def test_o_coracao_acelera_com_ele_perto():
    e = regras.Estado(x=0.0, z=0.0)
    e.vulto = (20.0, 0.0)
    assert regras.batimento(e) == 0.0
    e.vulto = (6.0, 0.0)
    longe = regras.batimento(e)
    e.vulto = (2.0, 0.0)
    assert 0 < regras.batimento(e) < longe


def test_os_sons_sao_gerados_uma_vez(tmp_path):
    from games.terror_ps1 import sons
    caminhos = sons.gerar(tmp_path)
    assert set(caminhos) == set(sons.SONS) and all(c.stat().st_size > 1000 for c in caminhos.values())
    antes = {c: c.stat().st_mtime_ns for c in caminhos.values()}
    sons.gerar(tmp_path)
    assert {c: c.stat().st_mtime_ns for c in caminhos.values()} == antes


# ---------------------------------------------------------------- o mapa da floresta

import pytest  # noqa: E402

from games.terror_ps1 import mapa as mapa_mod  # noqa: E402


@pytest.fixture(scope="module")
def floresta():
    return mapa_mod.gerar_mapa()


def _no_mapa(m, **kw):
    e = regras.Estado(mapa=m)
    for k, v in kw.items():
        setattr(e, k, v)
    return e


def test_o_mapa_e_sempre_o_mesmo_e_as_trilhas_ficam_livres(floresta):
    outro = mapa_mod.gerar_mapa()
    assert floresta.arvores == outro.arvores and floresta.armadilhas == outro.armadilhas
    assert len(floresta.arvores) > 600 and len(floresta.amuletos) == 7 and len(floresta.armadilhas) >= 15
    dentro = [(x, z) for x, z, _, _ in floresta.arvores if abs(x) < mapa_mod.LIMITE and abs(z) < mapa_mod.LIMITE]
    assert all(mapa_mod.dist_trilha(p) >= 1.8 for p in dentro)  # nenhuma arvore no caminho


def test_da_para_pegar_todo_amuleto_e_toda_pilha(floresta):
    for x, z in [(a[0], a[1]) for a in floresta.amuletos] + floresta.pilhas:
        px, pz = regras.colidir(x, z, floresta.circulos_perto(x, z), floresta.caixas, (-40, 40, -40, 40))
        assert math.hypot(px - x, pz - z) < regras.PEGAR_ITEM  # a colisao deixa chegar perto o bastante


def test_pegar_amuleto_e_pilha(floresta):
    a = floresta.amuletos[0]
    x, z = regras.colidir(a[0], a[1], floresta.circulos_perto(a[0], a[1]), floresta.caixas, (-40, 40, -40, 40))
    e = _no_mapa(floresta, x=x, z=z, pilha=0.2, vulto=(a[0] + 20, a[1]))
    regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    assert e.coletados == 1 and "amuleto" in e.eventos
    p = floresta.pilhas[0]
    e.x, e.z = p[0] + 0.3, p[1]
    regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    assert e.pilha > 0.6 and "pilha" in e.eventos


def test_armadilha_prende_faz_barulho_e_o_vulto_ouve(floresta):
    tx, tz = floresta.armadilhas[0]
    e = _no_mapa(floresta, x=tx, z=tz + 0.2, vulto=(tx + 20.0, tz))
    regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    assert e.preso > 0 and "armadilha" in e.eventos and e.armadilhas[0][2] == 1.0
    assert math.hypot(e.vulto[0] - tx, e.vulto[1] - tz) <= 10.5  # correu para o barulho
    x0 = e.x
    regras.atualizar(e, 1 / 60, 1.0, 0, 0, False)
    assert e.x == x0  # preso nao anda
    for _ in range(4):  # forcando, sai antes dos 3 s
        regras.atualizar(e, 1 / 60, 0, 0, 0, False, soltar=True)
    for _ in range(120):
        regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    assert e.preso == 0 and e.mancando > 0  # solto, mas mancando
    regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    assert "armadilha" not in e.eventos  # fechada, nao morde de novo


def test_com_todos_os_amuletos_o_santuario_termina_a_noite(floresta):
    sx, sz = mapa_mod.SANTUARIO
    e = _no_mapa(floresta, x=sx, z=sz + 2.0, vulto=(sx + 15, sz + 15))
    regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    assert not e.venceu  # sem os amuletos, nada
    e.coletados, e.amuletos = 7, []
    regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    assert e.venceu and "venceu" in e.eventos
    regras.reiniciar(e)
    assert not e.venceu and e.coletados == 0 and len(e.amuletos) == 7


def test_longe_demais_ele_reaparece_atras(floresta):
    e = _no_mapa(floresta, vulto=(-35.0, -35.0))
    for _ in range(80):
        regras.atualizar(e, 1 / 60, 0, 0, 0, False)
    vx, vz = e.vulto
    assert math.hypot(e.x - vx, e.z - vz) < 17 and vz > e.z  # atras (giro 0 olha para -z)


def test_caixa_nao_deixa_atravessar_parede():
    x, z = regras.colidir(0.0, 0.05, (), [(-1.0, -0.1, 1.0, 0.1)], (-9, 9, -9, 9))
    assert abs(z) >= 0.1 + regras.RAIO_JOGADOR - 1e-9
