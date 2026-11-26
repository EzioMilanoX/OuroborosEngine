# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Projecoes de camera (ROADMAP M20): do mundo (chao em x, y; altura z) para a tela, e de
volta. Logica pura, sem pygame (Regra 2).

Tres modos, todos o mesmo mapa linear do chao para a tela seguido do zoom:

- `DE_CIMA`: o chao como esta; a altura nao aparece (z nao mexe na tela).
- `TRES_QUARTOS` (3/4, 2.5D): o chao achatado na vertical por `escala_y` e a altura subindo
  na tela -- o que o Ryoiki faz com `ESCALA_Y = 0.62`.
- `ISOMETRICA`: o chao girado 45 graus e achatado por `escala_iso` (0.5 = o losango 2:1 da
  pixel art); a altura sobe na tela.

Em todos, `tela_de(x, y, z)` -> pixel e `mundo_de(sx, sy, z)` -> o ponto do chao (ou do plano
na altura z) sob aquele pixel. As versoes em lote escrevem em arrays de saida ja alocados
(Zero-GC, para muitas entidades por quadro).

Para ordenar quem esta na frente use `profundidade(x, y)` (a linha da tela do ponto do chao,
sem a camera): no 3/4 e de cima e o proprio y; na isometrica e x + y. A `FilaProfundidade`
ordena por (profundidade, z, camada) sem alocar.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple, Union

import numpy as np

DE_CIMA = "de_cima"
TRES_QUARTOS = "3/4"
ISOMETRICA = "isometrica"
MODOS = (DE_CIMA, TRES_QUARTOS, ISOMETRICA)

ESCALA_Y_PADRAO = 0.62  # o achatado do Ryoiki
ESCALA_ISO_PADRAO = 0.5  # o losango 2:1

ArrayOuEscalar = Union[np.ndarray, float]


class Projecao:
    """
    A camera: `centro` (o ponto do mundo no meio da tela), `tela` (largura, altura em pixels)
    e `zoom`. `cx`, `cy` e `zoom` sao atributos livres (mude a cada quadro para seguir alguem);
    `modo`, `escala_y`, `escala_iso` e `escala_z` refazem a matriz ao mudar.

    O chao vai para a tela por `M = achatar(a) . girar(ang)` (2x2), a altura por `-kz * z`,
    tudo vezes o zoom e somado ao meio da tela. `mundo_de` e a inversa no plano de altura z.
    """

    def __init__(self, modo: str = TRES_QUARTOS, *, centro: Tuple[float, float] = (0.0, 0.0),
                 tela: Tuple[float, float] = (960.0, 540.0), zoom: float = 1.0,
                 escala_y: float = ESCALA_Y_PADRAO, escala_iso: float = ESCALA_ISO_PADRAO,
                 escala_z: float = 1.0) -> None:
        self.cx = float(centro[0])
        self.cy = float(centro[1])
        self.largura = float(tela[0])
        self.altura = float(tela[1])
        self.zoom = float(zoom)
        self._modo = TRES_QUARTOS
        self._escala_y = float(escala_y)
        self._escala_iso = float(escala_iso)
        self._escala_z = float(escala_z)
        self._scratch = np.zeros(0, np.float64)
        self._scratch2 = np.zeros(0, np.float64)
        self._tabelas_elipse: dict = {}
        self.modo = modo

    # ------------------------------------------------------------ configuracao

    @property
    def modo(self) -> str:
        return self._modo

    @modo.setter
    def modo(self, valor: str) -> None:
        if valor not in MODOS:
            raise ValueError(f"modo desconhecido: {valor!r} (use um de {MODOS})")
        self._modo = valor
        self._recalcular()

    @property
    def escala_y(self) -> float:
        return self._escala_y

    @escala_y.setter
    def escala_y(self, valor: float) -> None:
        self._escala_y = float(valor)
        self._recalcular()

    @property
    def escala_iso(self) -> float:
        return self._escala_iso

    @escala_iso.setter
    def escala_iso(self, valor: float) -> None:
        self._escala_iso = float(valor)
        self._recalcular()

    @property
    def escala_z(self) -> float:
        return self._escala_z

    @escala_z.setter
    def escala_z(self, valor: float) -> None:
        self._escala_z = float(valor)
        self._recalcular()

    @property
    def achatamento(self) -> float:
        """Quanto o chao encolhe na vertical da tela (1 de cima; `escala_y` no 3/4;
        `escala_iso` na isometrica). Um circulo de raio r no chao vira uma elipse r x a*r."""
        return self._a

    def centralizar(self, x: float, y: float) -> None:
        """Poe o ponto (x, y) do chao no meio da tela."""
        self.cx = float(x)
        self.cy = float(y)

    def _recalcular(self) -> None:
        if self._modo == DE_CIMA:
            ang, a, kz = 0.0, 1.0, 0.0
        elif self._modo == TRES_QUARTOS:
            ang, a, kz = 0.0, self._escala_y, self._escala_z
        else:
            ang, a, kz = math.pi / 4, self._escala_iso, self._escala_z
        if a <= 0:
            raise ValueError("o achatamento precisa ser positivo")
        c, s = math.cos(ang), math.sin(ang)
        # M = [[1, 0], [0, a]] . [[c, -s], [s, c]]
        self._m00, self._m01 = c, -s
        self._m10, self._m11 = a * s, a * c
        det = self._m00 * self._m11 - self._m01 * self._m10
        self._i00, self._i01 = self._m11 / det, -self._m01 / det
        self._i10, self._i11 = -self._m10 / det, self._m00 / det
        self._a = a
        self._kz = kz

    # ------------------------------------------------------------ escalar

    def tela_x(self, x: float, y: float) -> float:
        """So o x da tela (sem tupla: Zero-GC no escalar)."""
        return (self._m00 * (x - self.cx) + self._m01 * (y - self.cy)) * self.zoom + self.largura * 0.5

    def tela_y(self, x: float, y: float, z: float = 0.0) -> float:
        """So o y da tela (sem tupla: Zero-GC no escalar)."""
        return ((self._m10 * (x - self.cx) + self._m11 * (y - self.cy) - self._kz * z) * self.zoom
                + self.altura * 0.5)

    def tela_de(self, x: float, y: float, z: float = 0.0) -> Tuple[float, float]:
        """Do mundo (chao em x, y; altura z) para o pixel da tela."""
        return self.tela_x(x, y), self.tela_y(x, y, z)

    def mundo_de(self, sx: float, sy: float, z: float = 0.0) -> Tuple[float, float]:
        """Do pixel para o ponto do chao (ou do plano na altura z) que aparece nele."""
        u = (sx - self.largura * 0.5) / self.zoom
        v = (sy - self.altura * 0.5) / self.zoom + self._kz * z
        return (self._i00 * u + self._i01 * v + self.cx,
                self._i10 * u + self._i11 * v + self.cy)

    def profundidade(self, x: float, y: float) -> float:
        """A chave de ordem de desenho do ponto do chao (maior = mais perto = desenha depois).
        Nao depende da camera nem do zoom: serve entre quadros."""
        return self._m10 * x + self._m11 * y

    def eixos_elipse_chao(self, raio: float) -> Tuple[float, float]:
        """Os semi-eixos na tela (rx, ry) de um circulo de raio `raio` deitado no chao."""
        return raio * self.zoom, raio * self._a * self.zoom

    def sombra(self, x: float, y: float, z: float, raio: float,
               altura_some: float = 160.0) -> Tuple[float, float, float, float, float]:
        """A sombra de quem esta em (x, y, z): `(sx, sy, rx, ry, forca)`. Fica no chao embaixo
        da figura e encolhe/clareia com a altura (`forca` 1 no chao, perto de 0.35 em
        `altura_some`); use `forca` para multiplicar o alfa."""
        k = 1.0 / (1.0 + max(z, 0.0) / max(altura_some, 1e-9) * 1.85)
        rx, ry = raio * k * self.zoom, raio * k * self._a * self.zoom
        return self.tela_x(x, y), self.tela_y(x, y, 0.0), rx, ry, k

    def pontos_elipse_chao(self, x: float, y: float, raio: float, z: float = 0.0,
                           out: Optional[np.ndarray] = None, n: int = 24) -> np.ndarray:
        """Os vertices na tela de um circulo deitado no chao (o anel de um dominio, a sombra),
        num array (n, 2). Com `out` (shape (n, 2) float) nao aloca: escreve nele."""
        if out is None:
            out = np.empty((n, 2), np.float64)
        n = out.shape[0]
        tab = self._tabelas_elipse.get(n)
        if tab is None:  # uma vez por n: fora do caminho quente
            t = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False)
            tab = (np.cos(t), np.sin(t))
            self._tabelas_elipse[n] = tab
        rx, ry = raio * self.zoom, raio * self._a * self.zoom
        np.multiply(tab[0], rx, out=out[:, 0])
        out[:, 0] += self.tela_x(x, y)
        np.multiply(tab[1], ry, out=out[:, 1])
        out[:, 1] += self.tela_y(x, y, z)
        return out

    # ------------------------------------------------------------ lote (Zero-GC)

    def _rascunho(self, n: int) -> Tuple[np.ndarray, np.ndarray]:
        if self._scratch.shape[0] < n:  # cresce so quando falta: fora do regime
            self._scratch = np.zeros(max(n, 64), np.float64)
            self._scratch2 = np.zeros(max(n, 64), np.float64)
        return self._scratch[:n], self._scratch2[:n]

    def reservar(self, n: int) -> None:
        """Pre-aloca o rascunho dos lotes para `n` entidades (chame no carregamento)."""
        self._rascunho(n)

    def tela_de_lote(self, x: np.ndarray, y: np.ndarray, z: Optional[ArrayOuEscalar],
                     out_x: np.ndarray, out_y: np.ndarray, n: Optional[int] = None) -> None:
        """`tela_de` para `n` entidades de uma vez (default: todas). `z` pode ser array, numero
        ou None (chao). Escreve em `out_x`/`out_y`; com `reservar(n)` antes, nao aloca."""
        if n is None:
            n = x.shape[0]
        dx, dy = self._rascunho(n)
        np.subtract(x[:n], self.cx, out=dx)
        np.subtract(y[:n], self.cy, out=dy)
        ox, oy = out_x[:n], out_y[:n]
        # x da tela
        np.multiply(dx, self._m00, out=ox)
        if self._m01 != 0.0:
            np.multiply(dy, self._m01, out=oy)  # oy de rascunho: ainda nao foi calculado
            ox += oy
        ox *= self.zoom
        ox += self.largura * 0.5
        # y da tela
        np.multiply(dx, self._m10, out=oy)
        dy *= self._m11
        oy += dy
        if z is not None and self._kz != 0.0:
            if isinstance(z, np.ndarray):
                np.multiply(z[:n], self._kz, out=dy)
                oy -= dy
            else:
                oy -= self._kz * float(z)
        oy *= self.zoom
        oy += self.altura * 0.5

    def mundo_de_lote(self, sx: np.ndarray, sy: np.ndarray, out_x: np.ndarray, out_y: np.ndarray,
                      n: Optional[int] = None, z: float = 0.0) -> None:
        """`mundo_de` em lote (no plano de altura `z`), escrevendo em `out_x`/`out_y`."""
        if n is None:
            n = sx.shape[0]
        u, v = self._rascunho(n)
        np.subtract(sx[:n], self.largura * 0.5, out=u)
        u /= self.zoom
        np.subtract(sy[:n], self.altura * 0.5, out=v)
        v /= self.zoom
        v += self._kz * z
        ox, oy = out_x[:n], out_y[:n]
        np.multiply(u, self._i00, out=ox)
        np.multiply(v, self._i11, out=oy)
        if self._i01 != 0.0:
            v *= self._i01  # v so falta no x: vira o termo cruzado no lugar
            ox += v
        if self._i10 != 0.0:
            u *= self._i10  # idem para u no y
            oy += u
        ox += self.cx
        oy += self.cy

    def profundidade_lote(self, x: np.ndarray, y: np.ndarray, out: np.ndarray,
                          n: Optional[int] = None) -> None:
        """`profundidade` em lote, escrevendo em `out`."""
        if n is None:
            n = x.shape[0]
        _, t = self._rascunho(n)
        o = out[:n]
        np.multiply(x[:n], self._m10, out=o)
        np.multiply(y[:n], self._m11, out=t)
        o += t


class FilaProfundidade:
    """
    A ordem de desenho de um quadro: adicione cada coisa em pe (figura, pilar, projetil,
    efeito) com `adicionar(id, profundidade, z, camada)` e `ordenar()` devolve os ids de tras
    para a frente -- por profundidade, depois z (quem esta no alto sai por cima), depois
    camada (desempate pedido pelo jogo: a espada na frente do braco), depois id (estavel).

    Tudo em um array estruturado pre-alocado ordenado no lugar: nada de lista nem `sorted`
    por quadro (Zero-GC). A profundidade vem de `Projecao.profundidade(x, y)` (no 3/4 e de
    cima pode ser o proprio y).
    """

    _DTYPE = np.dtype([("y", "f8"), ("z", "f8"), ("camada", "i4"), ("id", "i8")])

    def __init__(self, capacidade: int = 1024) -> None:
        if capacidade <= 0:
            raise ValueError("capacidade precisa ser positiva")
        self._buf = np.zeros(capacidade, self._DTYPE)
        self._y = self._buf["y"]
        self._z = self._buf["z"]
        self._camada = self._buf["camada"]
        self._id = self._buf["id"]
        self._n = 0
        self.transbordou = False  # True se alguem foi recusado por falta de espaco neste quadro

    @property
    def capacidade(self) -> int:
        return self._buf.shape[0]

    def __len__(self) -> int:
        return self._n

    def limpar(self) -> None:
        self._n = 0
        self.transbordou = False

    def adicionar(self, ident: int, y: float, z: float = 0.0, camada: int = 0) -> bool:
        """Poe um item; False (e `transbordou`) se a fila esta cheia."""
        n = self._n
        if n >= self._buf.shape[0]:
            self.transbordou = True
            return False
        self._y[n] = y
        self._z[n] = z
        self._camada[n] = camada
        self._id[n] = ident
        self._n = n + 1
        return True

    def ordenar(self) -> np.ndarray:
        """Ordena no lugar e devolve a view dos ids (de tras para a frente). Valida ate o
        proximo `limpar`/`adicionar`."""
        n = self._n
        self._buf[:n].sort()  # campos na ordem do dtype: y, z, camada, id
        return self._id[:n]
