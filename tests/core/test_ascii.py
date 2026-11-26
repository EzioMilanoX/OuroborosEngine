# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""TelaAscii, SpriteAscii e AnimacaoAscii (ROADMAP M22): primitivas, transparencia, espelho,
a conversao por luminancia do filtro e Zero-GC nas primitivas de quadro."""
from __future__ import annotations

import gc

import numpy as np
import pytest

from ouroboros.core.ascii import (
    RAMPA_PADRAO, AnimacaoAscii, FiltroAscii, SpriteAscii, TelaAscii, espelhar_linha,
)

VERMELHO = (255, 0, 0)


def test_por_e_texto_cortam_nas_bordas():
    t = TelaAscii(6, 3)
    t.por(0, 0, "A", VERMELHO)
    t.por(99, 0, "Z")  # fora: nada
    t.por(-1, 1, "Z")
    t.texto(3, 1, "OLA!!", (0, 255, 0))  # passa da borda direita: corta
    t.texto(0, 7, "nada")
    assert t.linha_texto(0) == "A     "
    assert t.linha_texto(1) == "   OLA"
    assert tuple(t.cores[0, 0]) == VERMELHO and tuple(t.cores[1, 5]) == (0, 255, 0)


def test_limpar_volta_ao_padrao():
    t = TelaAscii(4, 2, cor=(1, 2, 3), fundo=(9, 9, 9))
    t.texto(0, 0, "xx", VERMELHO, fundo=(50, 0, 0))
    t.limpar()
    assert t.texto_completo() == "    \n    "
    assert tuple(t.cores[0, 0]) == (1, 2, 3) and tuple(t.fundos[0, 0]) == (9, 9, 9)
    sem_fundo = TelaAscii(2, 2, fundo=None)
    assert sem_fundo.fundos is None
    sem_fundo.limpar()
    sem_fundo.por(0, 0, "x", fundo=(1, 1, 1))  # sem fundo: ignora


def test_linha_escolhe_o_caractere_pela_inclinacao():
    t = TelaAscii(10, 6)
    t.linha(0, 0, 9, 0)
    t.linha(0, 1, 0, 5)
    t.linha(2, 2, 5, 5)
    t.linha(9, 2, 6, 5, "*")
    assert t.linha_texto(0) == "-" * 10
    assert t.ler(0, 3) == "|"
    assert [t.ler(2 + i, 2 + i) for i in range(4)] == ["\\"] * 4
    assert [t.ler(9 - i, 2 + i) for i in range(4)] == ["*"] * 4
    t2 = TelaAscii(5, 5)
    t2.linha(0, 4, 4, 0)
    assert t2.ler(2, 2) == "/"


def test_retangulo_contorno_e_cheio():
    t = TelaAscii(6, 4)
    t.retangulo(0, 0, 6, 4)
    assert t.texto_completo().split("\n") == ["+----+", "|    |", "|    |", "+----+"]
    t2 = TelaAscii(5, 3, fundo=(0, 0, 0))
    t2.retangulo(1, 1, 10, 10, "#", preenchido=True, fundo=(0, 0, 200))  # corta fora
    assert t2.linha_texto(2) == " ####"
    assert tuple(t2.fundos[2, 4]) == (0, 0, 200) and tuple(t2.fundos[0, 0]) == (0, 0, 0)


def test_elipse_cheia_e_borda():
    t = TelaAscii(21, 9)
    t.elipse(10, 4, 8, 3, "o")
    linhas = t.texto_completo().split("\n")
    assert linhas[4].count("o") == 17  # a linha do meio: 2*8 + 1
    assert linhas[0].strip() == "" and linhas[8].strip() == ""
    assert linhas[1].count("o") < linhas[4].count("o")  # afina nas pontas
    b = TelaAscii(21, 9)
    b.elipse(10, 4, 8, 3, "o", preenchido=False)
    assert b.ler(10, 4) == " " and b.ler(2, 4) == "o" and b.ler(18, 4) == "o"  # oca
    assert b.ler(10, 1) == "o"  # o topo


ARTE = """
  ,~
 [o=>
 /|#\\
"""


def test_sprite_com_transparencia_e_ancora_nos_pes():
    s = SpriteAscii(ARTE, cor=(200, 200, 200), cor_por_caractere={"#": VERMELHO})
    assert (s.largura, s.altura) == (4, 3) and s.ancora == (2, 2)  # a indentacao comum sai
    t = TelaAscii(9, 4)
    t.texto(0, 1, ".........")
    t.sprite(s, 4, 3)  # pes em (4, 3)
    assert t.linha_texto(1) == "...,~...."  # o espaco da arte e transparente: o fundo fica
    assert t.linha_texto(2) == "  [o=>   "
    assert t.linha_texto(3) == "  /|#\\   "
    assert tuple(t.cores[3, 4]) == VERMELHO and tuple(t.cores[3, 3]) == (200, 200, 200)
    t.sprite(s, 4, 3, cor=(0, 0, 255))  # pintar tudo de uma cor
    assert tuple(t.cores[3, 4]) == (0, 0, 255)


def test_sprite_cortado_na_borda_e_fora():
    s = SpriteAscii(ARTE)
    t = TelaAscii(4, 3)
    t.sprite(s, 0, 2)  # metade para fora a esquerda
    assert t.linha_texto(2) == "#\\  "
    t.sprite(s, 99, 99)  # fora: nada (e nao levanta)
    t.sprite(s, -99, -99)


def test_espelho_troca_pares_e_ancora():
    assert espelhar_linha("(o)-/<[") == "]>\\-(o)"
    s = SpriteAscii(ARTE)
    assert s.linhas(espelhado=True) == [" ~, ", "<=o]", "/#|\\"]
    assert s.ancora_esp == (1, 2)  # os pes continuam sob o mesmo ponto do corpo
    t = TelaAscii(9, 4)
    t.sprite(s, 4, 3, espelhado=True)
    assert t.linha_texto(3) == "   /#|\\  "


def test_transparente_escolhido_deixa_o_espaco_opaco():
    s = SpriteAscii(["~|  |~"], transparente="~")
    t = TelaAscii(6, 1)
    t.texto(0, 0, "xxxxxx")
    t.sprite(s, 3, 0)
    assert t.linha_texto(0) == "x|  |x"


def test_mapa_de_cores_e_paleta():
    s = SpriteAscii(["ab", "cd"], mapa_cores=["rg", " r"], paleta={"r": VERMELHO, "g": (0, 255, 0)},
                    cor=(9, 9, 9))
    assert tuple(s.cores[0, 0]) == VERMELHO and tuple(s.cores[0, 1]) == (0, 255, 0)
    assert tuple(s.cores[1, 0]) == (9, 9, 9) and tuple(s.cores_esp[1, 0]) == VERMELHO
    with pytest.raises(ValueError):
        SpriteAscii(["a"], mapa_cores=["r"])
    with pytest.raises(ValueError):
        SpriteAscii("   \n  ")


def test_animacao_laco_e_sem_laco():
    a, b, c = SpriteAscii("a"), SpriteAscii("b"), SpriteAscii("c")
    laco = AnimacaoAscii([a, b, c], fps=10)
    assert laco.quadro(0.0) is a and laco.quadro(0.15) is b and laco.quadro(0.31) is a
    golpe = AnimacaoAscii([a, b, c], fps=10, laco=False)
    assert golpe.quadro(5.0) is c and golpe.acabou(0.31) and not golpe.acabou(0.2)
    assert golpe.duracao == pytest.approx(0.3)


def test_luminancia_vira_caractere_da_rampa():
    t = TelaAscii(10, 2, fundo=(0, 0, 0))
    rgb = np.zeros((2, 10, 3), np.uint8)
    for i in range(10):
        rgb[0, i] = 255 * i // 9  # cinza do preto ao branco
    rgb[1, :] = (255, 0, 0)  # vermelho puro: luminancia 54
    t.preencher_por_luminancia(rgb, RAMPA_PADRAO, fundo=0.5)
    assert t.ler(0, 0) == " " and t.ler(9, 0) == "@"
    linha = t.linha_texto(0)
    assert [RAMPA_PADRAO.index(c) for c in linha] == sorted(RAMPA_PADRAO.index(c) for c in linha)
    assert t.ler(0, 1) == RAMPA_PADRAO[int(0.2126 * 255 * 10 / 256)]
    assert tuple(t.cores[1, 0]) == (255, 0, 0) and tuple(t.fundos[1, 0]) == (127, 0, 0)


def test_realce_e_niveis_de_cor():
    t = TelaAscii(1, 1, fundo=None)
    rgb = np.array([[[100, 50, 0]]], np.uint8)
    t.preencher_por_luminancia(rgb, realce=1.0)
    assert tuple(t.cores[0, 0]) == (255, 127, 0)  # o matiz fica, o brilho vai ao maximo
    t.preencher_por_luminancia(rgb, niveis_cor=4)  # degraus de 64, no meio do degrau
    assert tuple(t.cores[0, 0]) == (96, 32, 32)
    with pytest.raises(ValueError):
        t.preencher_por_luminancia(np.zeros((2, 2, 3), np.uint8))


def test_filtro_valida_a_configuracao():
    assert FiltroAscii().rampa == RAMPA_PADRAO
    with pytest.raises(ValueError):
        FiltroAscii(rampa="#")
    with pytest.raises(ValueError):
        FiltroAscii(niveis_cor=1)


def test_primitivas_de_quadro_nao_disparam_o_coletor():
    t = TelaAscii(120, 40, fundo=(0, 0, 0))
    s = SpriteAscii(ARTE, cor_por_caractere={"#": VERMELHO})
    rgb = np.random.default_rng(2).integers(0, 255, (40, 120, 3), dtype=np.uint8)
    t.preencher_por_luminancia(rgb)  # a rampa e preparada aqui
    coletas = []

    def sonda(fase, info):
        if fase == "start":
            coletas.append(info)

    gc.collect()
    gc.callbacks.append(sonda)
    try:
        for quadro in range(300):
            t.limpar()
            t.retangulo(0, 0, 120, 40)
            t.texto(2, 1, "HP 10  ouro 32", (255, 220, 0))
            t.linha(1, 1, 100, 30, None, VERMELHO)
            t.elipse(60, 20, 10, 4, ".", (40, 40, 40), fundo=(5, 5, 5))
            t.elipse(30, 20, 6, 3, "o", preenchido=False)
            for i in range(20):
                t.sprite(s, (quadro + i * 7) % 130 - 5, 10 + i, espelhado=bool(i & 1))
            t.sprite(s, 50, 30, cor=(255, 255, 255))
            t.preencher_por_luminancia(rgb, realce=0.5, fundo=0.2, niveis_cor=8)
        sem_lixo = len(coletas)
        lixo = [[k] for k in range(50000)]
        assert lixo and len(coletas) > sem_lixo
    finally:
        gc.callbacks.remove(sonda)
    assert sem_lixo == 0
