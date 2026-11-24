# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Relevo: um chao por mapa de alturas (heightmap) numa grade regular em x/z.

E a mesma superficie que `ouroboros.interfaces.malhas3d.terreno` desenha: cada celula e
dividida em dois triangulos pela diagonal do canto (x0, z0) ao (x1, z1), e a altura dentro
da celula e a do plano do triangulo -- entao o pe do personagem fica exatamente em cima do
que aparece na tela (uma interpolacao bilinear afundaria ou flutuaria no meio da celula).

Fora da grade, `altura` repete a borda (o chao nao some se alguem escapar do mapa);
`raycast` so acerta dentro dela.
"""
from __future__ import annotations

import math
from typing import Callable, List, Tuple

import numpy as np

from ouroboros.core.colisao3d.primitivas import INF, Vec3, _k_raio_triangulo


class Relevo:
    """`alturas[j, i]` e a altura do vertice (x0 + i * passo, z0 + j * passo): shape
    (celulas_z + 1, celulas_x + 1). Use `de_funcao` para amostrar uma funcao altura(x, z)."""

    def __init__(self, alturas: np.ndarray, x0: float, z0: float, passo: float) -> None:
        alt = np.asarray(alturas, dtype=np.float64)
        if alt.ndim != 2 or alt.shape[0] < 2 or alt.shape[1] < 2:
            raise ValueError("alturas precisa ser 2D com pelo menos 2x2 vertices")
        if passo <= 0:
            raise ValueError("passo precisa ser positivo")
        self._alt = alt
        self._x0, self._z0, self._passo = float(x0), float(z0), float(passo)
        self._nz, self._nx = alt.shape[0] - 1, alt.shape[1] - 1  # celulas
        self._lista = alt.tolist()  # leitura escalar rapida no caminho quente
        self._s = [0.0, 0.0, 0.0]

    @classmethod
    def de_funcao(cls, altura: Callable[[float, float], float], x0: float, x1: float, z0: float, z1: float,
                  passo: float) -> "Relevo":
        """Amostra `altura(x, z)` nos vertices de uma grade de `x0..x1` por `z0..z1`."""
        nx, nz = max(1, round((x1 - x0) / passo)), max(1, round((z1 - z0) / passo))
        alt = np.array([[altura(x0 + i * passo, z0 + j * passo) for i in range(nx + 1)] for j in range(nz + 1)])
        return cls(alt, x0, z0, passo)

    # ------------------------------------------------------------------ dados
    @property
    def alturas(self) -> np.ndarray:
        """Copia somente-leitura das alturas (mude criando outro `Relevo`)."""
        return self._alt.copy()

    @property
    def passo(self) -> float:
        return self._passo

    @property
    def celulas(self) -> Tuple[int, int]:
        """(celulas em x, celulas em z)."""
        return self._nx, self._nz

    @property
    def limites(self) -> Tuple[float, float, float, float]:
        """(x0, x1, z0, z1)."""
        return (self._x0, self._x0 + self._nx * self._passo, self._z0, self._z0 + self._nz * self._passo)

    def vertice(self, i: int, j: int) -> Vec3:
        return (self._x0 + i * self._passo, self._lista[j][i], self._z0 + j * self._passo)

    # ------------------------------------------------------------------ consultas
    def _celula(self, x: float, z: float) -> Tuple[int, int, float, float]:
        fx = (x - self._x0) / self._passo
        fz = (z - self._z0) / self._passo
        fx = 0.0 if fx < 0.0 else (float(self._nx) if fx > self._nx else fx)
        fz = 0.0 if fz < 0.0 else (float(self._nz) if fz > self._nz else fz)
        i = min(int(fx), self._nx - 1)
        j = min(int(fz), self._nz - 1)
        return i, j, fx - i, fz - j

    def altura(self, x: float, z: float) -> float:
        """A altura do chao em (x, z) (fora da grade: a da borda mais perto)."""
        i, j, u, v = self._celula(x, z)
        linha, prox = self._lista[j], self._lista[j + 1]
        ha, hb, hc, hd = linha[i], linha[i + 1], prox[i + 1], prox[i]
        if u >= v:  # triangulo (a, b, c)
            return ha + (hb - ha) * u + (hc - hb) * v
        return ha + (hc - hd) * u + (hd - ha) * v  # triangulo (a, c, d)

    def _k_normal(self, x: float, z: float, saida: List[float]) -> None:
        i, j, u, v = self._celula(x, z)
        linha, prox = self._lista[j], self._lista[j + 1]
        ha, hb, hc, hd = linha[i], linha[i + 1], prox[i + 1], prox[i]
        if u >= v:
            gx, gz = (hb - ha) / self._passo, (hc - hb) / self._passo
        else:
            gx, gz = (hc - hd) / self._passo, (hd - ha) / self._passo
        n = math.sqrt(gx * gx + 1.0 + gz * gz)
        saida[0], saida[1], saida[2] = -gx / n, 1.0 / n, -gz / n

    def normal(self, x: float, z: float) -> Vec3:
        """A normal (unitaria, para cima) do triangulo do chao em (x, z)."""
        s = [0.0, 0.0, 0.0]
        self._k_normal(x, z, s)
        return (s[0], s[1], s[2])

    def dentro(self, x: float, z: float) -> bool:
        x0, x1, z0, z1 = self.limites
        return x0 <= x <= x1 and z0 <= z <= z1

    # ------------------------------------------------------------------ raio
    def _k_raycast(self, ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, tmax: float,
                   saida: List[float]) -> float:
        """Percorre as celulas cruzadas pelo raio (DDA de Amanatides-Woo em x/z) testando os
        dois triangulos de cada uma. `d` unitario. Devolve t (INF = errou) e a normal virada
        para o lado de onde o raio veio."""
        x0, x1, z0, z1 = self.limites
        # recorta o raio no retangulo da grade
        t0, t1 = 0.0, tmax
        for o, d, lo, hi in ((ox, dx, x0, x1), (oz, dz, z0, z1)):
            if abs(d) < 1e-12:
                if o < lo or o > hi:
                    return INF
                continue
            ta, tb = (lo - o) / d, (hi - o) / d
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                return INF
        passo = self._passo
        px, pz = ox + dx * t0, oz + dz * t0
        i = min(max(int((px - x0) / passo), 0), self._nx - 1)
        j = min(max(int((pz - z0) / passo), 0), self._nz - 1)
        si = 1 if dx > 0 else -1
        sj = 1 if dz > 0 else -1
        if abs(dx) > 1e-12:
            borda = x0 + (i + (1 if si > 0 else 0)) * passo
            tx, ddx = (borda - ox) / dx, passo / abs(dx)
        else:
            tx, ddx = INF, INF
        if abs(dz) > 1e-12:
            borda = z0 + (j + (1 if sj > 0 else 0)) * passo
            tz, ddz = (borda - oz) / dz, passo / abs(dz)
        else:
            tz, ddz = INF, INF
        lst = self._lista
        while True:
            xa, xb = x0 + i * passo, x0 + (i + 1) * passo
            za, zb = z0 + j * passo, z0 + (j + 1) * passo
            ha, hb, hc, hd = lst[j][i], lst[j][i + 1], lst[j + 1][i + 1], lst[j + 1][i]
            melhor = INF
            t = _k_raio_triangulo(ox, oy, oz, dx, dy, dz, tmax, xa, ha, za, xb, hb, za, xb, hc, zb, saida)
            if t < melhor:
                melhor = t
                n0, n1, n2 = saida[0], saida[1], saida[2]
            t = _k_raio_triangulo(ox, oy, oz, dx, dy, dz, tmax, xa, ha, za, xb, hc, zb, xa, hd, zb, saida)
            if t < melhor:
                melhor = t
                n0, n1, n2 = saida[0], saida[1], saida[2]
            if melhor < INF:
                saida[0], saida[1], saida[2] = n0, n1, n2
                return melhor
            if tx == INF and tz == INF:  # raio vertical: so a celula de partida conta
                return INF
            if tx < tz:
                if tx > t1:
                    return INF
                i += si
                tx += ddx
            else:
                if tz > t1:
                    return INF
                j += sj
                tz += ddz
            if i < 0 or j < 0 or i >= self._nx or j >= self._nz:
                return INF

    def raycast(self, origem: Vec3, direcao: Vec3, dist_max: float = INF):
        """Primeiro toque do raio no chao ate `dist_max`: (distancia, normal), ou None."""
        n = math.sqrt(direcao[0] ** 2 + direcao[1] ** 2 + direcao[2] ** 2)
        if n < 1e-12:
            return None
        t = self._k_raycast(origem[0], origem[1], origem[2], direcao[0] / n, direcao[1] / n, direcao[2] / n,
                            dist_max, self._s)
        return (t, (self._s[0], self._s[1], self._s[2])) if t != INF and t <= dist_max else None
