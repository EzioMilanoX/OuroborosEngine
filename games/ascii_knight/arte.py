# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A arte ASCII do ASCII Knight (original, feita para esta demo). Tudo olhando para a DIREITA;
o lado esquerdo sai do espelho da engine (`SpriteAscii`, que troca `/`<->`\\`, `(`<->`)`...).

Cada quadro do cavaleiro tem o corpo nas mesmas colunas e a ancora nos pes (coluna 4 da
ultima linha), para a animacao nao tremer. As cores vem de um mapa do mesmo formato da arte.
"""
from __future__ import annotations

from ouroboros.core.ascii import AnimacaoAscii, SpriteAscii

PALETA = {
    "s": (196, 204, 220),  # aco
    "d": (120, 126, 142),  # aco na sombra (pernas)
    "k": (120, 220, 255),  # o brilho da viseira
    "r": (200, 50, 60),  # a sobreveste
    "g": (238, 196, 70),  # o penacho
    "b": (160, 104, 52),  # o escudo
    "w": (240, 246, 255),  # a lamina
    "h": (210, 170, 90),  # o punho da espada
}


def _cavaleiro(arte: str, mapa: str) -> SpriteAscii:
    linhas = [linha for linha in arte.split("\n") if linha.strip()]
    return SpriteAscii(linhas, mapa_cores=[m for m in mapa.split("\n") if m.strip()], paleta=PALETA,
                       cor=PALETA["s"], ancora=(4, len(linhas) - 1))


PARADO_0 = _cavaleiro("""
    ,~
   [o=]
  /|##|\\
 (O|##| +
   /  \\ |
  _|  |_|
""", """
    gg
   sksx
  ssrrss
 bbsrrs h
   dddd w
  dddddhw
""")

PARADO_1 = _cavaleiro("""
    ~,
   [o=]
  /|##|\\
 (O|##| +
   /  \\ |
  _|  |_|
""", """
    gg
   sksx
  ssrrss
 bbsrrs h
   dddd w
  dddddhw
""")

ANDANDO_0 = _cavaleiro("""
    ,~
   [o=]
  /|##|\\
 (O|##| +
   /  \\ |
  /    \\|
""", """
    gg
   sksx
  ssrrss
 bbsrrs h
   dddd w
  dddddhw
""")

ANDANDO_1 = _cavaleiro("""
     ,~
   [o=]
  /|##|\\
 (O|##| +
    ||  |
   _||_ |
""", """
     gg
   sksx
  ssrrss
 bbsrrs h
    dd  w
   dddd w
""")

ANDANDO_2 = _cavaleiro("""
    ,~
   [o=]
  /|##|\\
 (O|##| +
   |  \\ |
  _|   \\|
""", """
    gg
   sksx
  ssrrss
 bbsrrs h
   dddd w
  ddddddw
""")

# o golpe: levanta a espada, corta para a frente, acompanha para baixo
ATAQUE_0 = _cavaleiro("""
        |
    ,~  |
   [o=] +
  /|##|/
 (O|##|
   /  \\
  _|  |_
""", """
        w
    gg  w
   sksx h
  ssrrss
 bbsrrs
   dddd
  dddddd
""")

ATAQUE_1 = _cavaleiro("""
    ,~
   [o=]
  /|##|\\
 (O|##|-+======-
   /  \\
  _|  |_
""", """
    gg
   sksx
  ssrrss
 bbsrrsshwwwwwww
   dddd
  dddddd
""")

ATAQUE_2 = _cavaleiro("""
    ,~
   [o=]
  /|##|\\
 (O|##| \\
   /  \\  \\
  _|  |_  \\
""", """
    gg
   sksx
  ssrrss
 bbsrrs h
   dddd  w
  dddddd  w
""")

PULO = _cavaleiro("""
    ,~
   [o=]
  \\|##|/+
 (O|##| |
   \\__/ |
""", """
    gg
   sksx
  ssrrssh
 bbsrrs w
   dddd w
""")

PARADO = AnimacaoAscii([PARADO_0, PARADO_1], fps=2.0)
ANDANDO = AnimacaoAscii([ANDANDO_0, ANDANDO_1, ANDANDO_2, ANDANDO_1], fps=9.0)
ATAQUE = AnimacaoAscii([ATAQUE_0, ATAQUE_1, ATAQUE_2], fps=10.0, laco=False)
QUADRO_DO_CORTE = 1  # o quadro em que a espada acerta

# o arco do corte, na frente do cavaleiro (ancora fora do desenho: fica a direita dos pes)
CORTE = SpriteAscii("""
 ~-.
    `.
      )
    .'
 ~-'
""", cor=(170, 230, 255), ancora=(-6, 5))

# ------------------------------------------------------------------ inimigos

VERDE = (110, 210, 100)
_OLHOS = {"o": (250, 250, 240)}

GOSMA_0 = SpriteAscii("""
  .--.
 ( oo )
(______)
""", cor=VERDE, cor_por_caractere=_OLHOS)

GOSMA_1 = SpriteAscii("""
 .------.
(__o__o__)
""", cor=VERDE, cor_por_caractere=_OLHOS)

GOSMA_NO_AR = SpriteAscii("""
  .-.
 (o o)
 (   )
  '-'
""", cor=VERDE, cor_por_caractere=_OLHOS)

GOSMA = AnimacaoAscii([GOSMA_0, GOSMA_1], fps=3.0)

ROXO = (176, 116, 226)
_OLHO_MORCEGO = {"o": (255, 90, 90)}

MORCEGO_0 = SpriteAscii("""
 /\\ _ /\\
/  (o)  \\
""", cor=ROXO, cor_por_caractere=_OLHO_MORCEGO)

MORCEGO_1 = SpriteAscii("""
   _
\\_(o)_/
""", cor=ROXO, cor_por_caractere=_OLHO_MORCEGO)

MORCEGO = AnimacaoAscii([MORCEGO_0, MORCEGO_1], fps=8.0)

# ------------------------------------------------------------------ cenario

PEDRA = (176, 170, 156)

# o pilar e solido: "~" e o transparente dele, e os espacos de dentro tapam quem passa atras
PILAR = SpriteAscii("""
~_______~
[_______]
~~|   |~~
~~| . |~~
~~|   |~~
~~|  .|~~
~~|   |~~
~_|___|_~
[_______]
""", cor=PEDRA, cor_por_caractere={".": (120, 116, 104), "[": (140, 134, 120), "]": (140, 134, 120)},
    transparente="~")

FOLHA = (70, 160, 70)
TRONCO = (140, 96, 56)

ARVORE = SpriteAscii("""
    .@@.
  .@@@@@@.
 @@@@@@@@@@
  @@@@@@@@
   '@@@@'
     ||
     ||
    /||\\
""", cor=FOLHA, cor_por_caractere={"|": TRONCO, "/": TRONCO, "\\": TRONCO}, ancora=(5, 7))

# ------------------------------------------------------------------ efeitos

FAISCA = (255, 236, 160)

PUF = AnimacaoAscii([
    SpriteAscii("""
 . .
. * .
 ' '
""", cor=FAISCA),
    SpriteAscii("""
.  *  .
 * @ *
'  *  '
""", cor=FAISCA),
    SpriteAscii("""
.     .
   .
'     '
""", cor=(170, 150, 110)),
], fps=10.0, laco=False)
