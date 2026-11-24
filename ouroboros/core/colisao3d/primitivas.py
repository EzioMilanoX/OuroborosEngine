# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""As primitivas de colisao 3D e os testes entre elas, puros (sem mundo, sem grade).

Formas: `AABB` (caixa alinhada aos eixos), `Esfera`, `Capsula` (segmento com raio -- o
corpo de um personagem em pe) e `Raio` (origem + direcao unitaria). Mundo com y para cima,
como o `IRenderer3D`.

Duas camadas, de proposito:
- as funcoes publicas (`sobrepoe`, `contato`, `raycast`, `raio_triangulo`) recebem as
  dataclasses e devolvem tuplas -- para ferramentas, testes e regras que rodam poucas vezes;
- as funcoes `_k_*` recebem so floats e escrevem o resultado numa lista ja alocada pelo
  chamador (`saida`): e o que o `MundoColisao3D` usa no caminho quente, sem criar tupla nem
  objeto por teste (Zero-GC: floats nao entram no coletor de ciclos, tuplas e listas sim).

Convencoes: `contato` devolve a normal que EMPURRA o corpo para fora da forma e a
profundidade da sobreposicao; um raio que comeca dentro da forma acerta em t = 0 com a
normal contra a direcao do raio.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple, Union

Vec3 = Tuple[float, float, float]
INF = math.inf
_EPS = 1e-9


@dataclass(frozen=True)
class AABB:
    """Caixa alinhada aos eixos, de `minimo` a `maximo` (cada eixo minimo <= maximo)."""

    minimo: Vec3
    maximo: Vec3

    @staticmethod
    def de_centro(centro: Vec3, meia: Vec3) -> "AABB":
        """A caixa com este centro e estas meias-medidas (metade da largura, altura e profundidade)."""
        return AABB((centro[0] - meia[0], centro[1] - meia[1], centro[2] - meia[2]),
                    (centro[0] + meia[0], centro[1] + meia[1], centro[2] + meia[2]))

    @property
    def centro(self) -> Vec3:
        a, b = self.minimo, self.maximo
        return ((a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5, (a[2] + b[2]) * 0.5)

    def contem(self, p: Vec3) -> bool:
        a, b = self.minimo, self.maximo
        return a[0] <= p[0] <= b[0] and a[1] <= p[1] <= b[1] and a[2] <= p[2] <= b[2]


@dataclass(frozen=True)
class Esfera:
    centro: Vec3
    raio: float


@dataclass(frozen=True)
class Capsula:
    """Segmento de `a` a `b` engordado por `raio` (as pontas sao meias-esferas)."""

    a: Vec3
    b: Vec3
    raio: float

    @staticmethod
    def em_pe(pe: Vec3, altura: float, raio: float) -> "Capsula":
        """Capsula vertical com a sola em `pe` e `altura` total (da sola ao topo da cabeca):
        o corpo de um personagem. `altura` menor que `2 * raio` vira uma esfera."""
        meio = max(0.0, altura - 2.0 * raio)
        y0 = pe[1] + raio
        return Capsula((pe[0], y0, pe[2]), (pe[0], y0 + meio, pe[2]), raio)


@dataclass(frozen=True)
class Raio:
    """Origem e direcao; a direcao e normalizada na construcao (t = distancia)."""

    origem: Vec3
    direcao: Vec3

    def __post_init__(self) -> None:
        d = self.direcao
        n = math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        if n < _EPS:
            raise ValueError("Raio sem direcao (vetor nulo)")
        object.__setattr__(self, "direcao", (d[0] / n, d[1] / n, d[2] / n))

    def ponto(self, t: float) -> Vec3:
        o, d = self.origem, self.direcao
        return (o[0] + d[0] * t, o[1] + d[1] * t, o[2] + d[2] * t)


Forma = Union[AABB, Esfera, Capsula]

# --------------------------------------------------------------------- nucleos escalares
# Todos recebem floats soltos. Os de contato devolvem a profundidade (> 0 = encostou) e
# escrevem a normal em saida[0:3]; os de raio devolvem t (INF = errou) e escrevem a normal.


def _k_param_segmento(px: float, py: float, pz: float, ax: float, ay: float, az: float,
                      bx: float, by: float, bz: float) -> float:
    """O parametro t em [0, 1] do ponto do segmento ab mais perto de p."""
    dx, dy, dz = bx - ax, by - ay, bz - az
    dd = dx * dx + dy * dy + dz * dz
    if dd < _EPS:
        return 0.0
    t = ((px - ax) * dx + (py - ay) * dy + (pz - az) * dz) / dd
    return 0.0 if t < 0.0 else (1.0 if t > 1.0 else t)


def _k_params_segmentos(p1x: float, p1y: float, p1z: float, q1x: float, q1y: float, q1z: float,
                        p2x: float, p2y: float, p2z: float, q2x: float, q2y: float, q2z: float,
                        saida: List[float]) -> None:
    """Os parametros (s, t) dos pontos mais perto entre os segmentos p1q1 e p2q2 (Ericson,
    Real-Time Collision Detection, 5.1.9), em saida[0] e saida[1]."""
    d1x, d1y, d1z = q1x - p1x, q1y - p1y, q1z - p1z
    d2x, d2y, d2z = q2x - p2x, q2y - p2y, q2z - p2z
    rx, ry, rz = p1x - p2x, p1y - p2y, p1z - p2z
    a = d1x * d1x + d1y * d1y + d1z * d1z
    e = d2x * d2x + d2y * d2y + d2z * d2z
    f = d2x * rx + d2y * ry + d2z * rz
    if a < _EPS and e < _EPS:
        saida[0] = saida[1] = 0.0
        return
    if a < _EPS:
        s, t = 0.0, min(max(f / e, 0.0), 1.0)
    else:
        c = d1x * rx + d1y * ry + d1z * rz
        if e < _EPS:
            s, t = min(max(-c / a, 0.0), 1.0), 0.0
        else:
            b = d1x * d2x + d1y * d2y + d1z * d2z
            den = a * e - b * b
            s = min(max((b * f - c * e) / den, 0.0), 1.0) if den > _EPS else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                s, t = min(max(-c / a, 0.0), 1.0), 0.0
            elif t > 1.0:
                s, t = min(max((b - c) / a, 0.0), 1.0), 1.0
    saida[0], saida[1] = s, t


def _k_param_segmento_aabb(ax: float, ay: float, az: float, bx: float, by: float, bz: float,
                           x0: float, y0: float, z0: float, x1: float, y1: float, z1: float) -> float:
    """O parametro t do ponto do segmento ab mais perto da caixa, exato.

    A distancia ao quadrado f(t) e convexa e quadratica por trechos: os trechos mudam onde
    o segmento cruza um dos 6 planos da caixa. Em cada trecho, os eixos "fora" sao fixos e o
    minimo sai de uma conta fechada. Se o segmento atravessa a caixa (f = 0 num intervalo),
    devolve o meio do pedaco de dentro -- o ponto mais fundo, para o contato empurrar para
    fora pelo lado certo. Os pontos de quebra vao para `_QUEBRAS` (pre-alocada; sem lixo)."""
    dx, dy, dz = bx - ax, by - ay, bz - az
    q = _QUEBRAS
    q[0], q[1] = 0.0, 1.0
    n = 2
    for k in range(3):
        if k == 0:
            o, d, lo, hi = ax, dx, x0, x1
        elif k == 1:
            o, d, lo, hi = ay, dy, y0, y1
        else:
            o, d, lo, hi = az, dz, z0, z1
        if abs(d) > _EPS:
            t = (lo - o) / d
            if 0.0 < t < 1.0:
                q[n] = t
                n += 1
            t = (hi - o) / d
            if 0.0 < t < 1.0:
                q[n] = t
                n += 1
    for i in range(1, n):  # insercao: no maximo 8 valores
        v, j = q[i], i - 1
        while j >= 0 and q[j] > v:
            q[j + 1] = q[j]
            j -= 1
        q[j + 1] = v
    melhor_t, melhor_f = 0.0, INF
    zi = zf = -1.0
    for i in range(n - 1):
        t0, t1 = q[i], q[i + 1]
        tm = (t0 + t1) * 0.5
        num = den = cte = 0.0
        ativos = 0
        for k in range(3):
            if k == 0:
                o, d, lo, hi = ax, dx, x0, x1
            elif k == 1:
                o, d, lo, hi = ay, dy, y0, y1
            else:
                o, d, lo, hi = az, dz, z0, z1
            p = o + d * tm
            if p < lo:
                c = o - lo
            elif p > hi:
                c = o - hi
            else:
                continue
            ativos += 1
            num += c * d
            den += d * d
            cte += c * c
        if ativos == 0:  # o trecho inteiro esta dentro da caixa
            if zi < 0.0:
                zi = t0
            zf = t1
            continue
        t = tm if den < _EPS else -num / den
        t = t0 if t < t0 else (t1 if t > t1 else t)
        f = cte + 2.0 * num * t + den * t * t
        if f < melhor_f:
            melhor_f, melhor_t = f, t
    if zi >= 0.0:
        return (zi + zf) * 0.5
    return melhor_t


_QUEBRAS = [0.0] * 8


def _k_contato_esfera_aabb(cx: float, cy: float, cz: float, r: float, x0: float, y0: float, z0: float,
                           x1: float, y1: float, z1: float, saida: List[float]) -> float:
    qx = x0 if cx < x0 else (x1 if cx > x1 else cx)
    qy = y0 if cy < y0 else (y1 if cy > y1 else cy)
    qz = z0 if cz < z0 else (z1 if cz > z1 else cz)
    dx, dy, dz = cx - qx, cy - qy, cz - qz
    d2 = dx * dx + dy * dy + dz * dz
    if d2 >= r * r:
        return 0.0
    if d2 > _EPS:
        d = math.sqrt(d2)
        saida[0], saida[1], saida[2] = dx / d, dy / d, dz / d
        return r - d
    # o centro entrou na caixa: sai pela face mais perto
    melhor, nx, ny, nz = cx - x0, -1.0, 0.0, 0.0
    if x1 - cx < melhor:
        melhor, nx, ny, nz = x1 - cx, 1.0, 0.0, 0.0
    if cy - y0 < melhor:
        melhor, nx, ny, nz = cy - y0, 0.0, -1.0, 0.0
    if y1 - cy < melhor:
        melhor, nx, ny, nz = y1 - cy, 0.0, 1.0, 0.0
    if cz - z0 < melhor:
        melhor, nx, ny, nz = cz - z0, 0.0, 0.0, -1.0
    if z1 - cz < melhor:
        melhor, nx, ny, nz = z1 - cz, 0.0, 0.0, 1.0
    saida[0], saida[1], saida[2] = nx, ny, nz
    return melhor + r


def _k_contato_esferas(cx: float, cy: float, cz: float, r: float, sx: float, sy: float, sz: float, sr: float,
                       saida: List[float]) -> float:
    dx, dy, dz = cx - sx, cy - sy, cz - sz
    soma = r + sr
    d2 = dx * dx + dy * dy + dz * dz
    if d2 >= soma * soma:
        return 0.0
    if d2 > _EPS:
        d = math.sqrt(d2)
        saida[0], saida[1], saida[2] = dx / d, dy / d, dz / d
        return soma - d
    saida[0], saida[1], saida[2] = 0.0, 1.0, 0.0  # centros iguais: sai para cima
    return soma


def _k_raio_aabb(ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, tmax: float,
                 x0: float, y0: float, z0: float, x1: float, y1: float, z1: float, saida: List[float]) -> float:
    """Metodo das placas (slabs). `d` unitario."""
    tmin, tsai = 0.0, tmax
    eixo, sinal = -1, 0.0
    for k in range(3):
        if k == 0:
            o, d, lo, hi = ox, dx, x0, x1
        elif k == 1:
            o, d, lo, hi = oy, dy, y0, y1
        else:
            o, d, lo, hi = oz, dz, z0, z1
        if abs(d) < _EPS:
            if o < lo or o > hi:
                return INF
            continue
        inv = 1.0 / d
        ta, tb = (lo - o) * inv, (hi - o) * inv
        s = -1.0
        if ta > tb:
            ta, tb, s = tb, ta, 1.0
        if ta > tmin:
            tmin, eixo, sinal = ta, k, s
        if tb < tsai:
            tsai = tb
        if tmin > tsai:
            return INF
    if eixo < 0:  # a origem esta dentro da caixa
        saida[0], saida[1], saida[2] = -dx, -dy, -dz
        return 0.0
    saida[0] = sinal if eixo == 0 else 0.0
    saida[1] = sinal if eixo == 1 else 0.0
    saida[2] = sinal if eixo == 2 else 0.0
    return tmin


def _k_raio_esfera(ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, tmax: float,
                   cx: float, cy: float, cz: float, r: float, saida: List[float]) -> float:
    mx, my, mz = ox - cx, oy - cy, oz - cz
    c = mx * mx + my * my + mz * mz - r * r
    if c <= 0.0:
        saida[0], saida[1], saida[2] = -dx, -dy, -dz
        return 0.0
    b = mx * dx + my * dy + mz * dz
    if b > 0.0:
        return INF
    h = b * b - c
    if h < 0.0:
        return INF
    t = -b - math.sqrt(h)
    if t > tmax:
        return INF
    saida[0], saida[1], saida[2] = (mx + dx * t) / r, (my + dy * t) / r, (mz + dz * t) / r
    return t


def _k_raio_capsula(ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, tmax: float,
                    ax: float, ay: float, az: float, bx: float, by: float, bz: float, r: float,
                    saida: List[float]) -> float:
    """Raio contra capsula: o cilindro do meio e, se cair fora dele, a esfera da ponta."""
    u = _k_param_segmento(ox, oy, oz, ax, ay, az, bx, by, bz)
    qx, qy, qz = ax + (bx - ax) * u, ay + (by - ay) * u, az + (bz - az) * u
    if (ox - qx) ** 2 + (oy - qy) ** 2 + (oz - qz) ** 2 <= r * r:
        saida[0], saida[1], saida[2] = -dx, -dy, -dz
        return 0.0
    bax, bay, baz = bx - ax, by - ay, bz - az
    oax, oay, oaz = ox - ax, oy - ay, oz - az
    baba = bax * bax + bay * bay + baz * baz
    bard = bax * dx + bay * dy + baz * dz
    baoa = bax * oax + bay * oay + baz * oaz
    rdoa = dx * oax + dy * oay + dz * oaz
    oaoa = oax * oax + oay * oay + oaz * oaz
    a = baba - bard * bard
    if baba > _EPS and a > _EPS:
        b = baba * rdoa - baoa * bard
        c = baba * oaoa - baoa * baoa - r * r * baba
        h = b * b - a * c
        if h < 0.0:
            return INF
        t = (-b - math.sqrt(h)) / a
        y = baoa + t * bard
        if 0.0 < y < baba:
            if t < 0.0 or t > tmax:
                return INF
            k = y / baba
            px, py, pz = ox + dx * t, oy + dy * t, oz + dz * t
            nx, ny, nz = px - (ax + bax * k), py - (ay + bay * k), pz - (az + baz * k)
            n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            saida[0], saida[1], saida[2] = nx / n, ny / n, nz / n
            return t
        if y <= 0.0:
            return _k_raio_esfera(ox, oy, oz, dx, dy, dz, tmax, ax, ay, az, r, saida)
        return _k_raio_esfera(ox, oy, oz, dx, dy, dz, tmax, bx, by, bz, r, saida)
    # raio paralelo ao eixo (ou capsula degenerada): so as pontas podem ser o primeiro toque
    t1 = _k_raio_esfera(ox, oy, oz, dx, dy, dz, tmax, ax, ay, az, r, saida)
    n0, n1, n2 = saida[0], saida[1], saida[2]
    t2 = _k_raio_esfera(ox, oy, oz, dx, dy, dz, tmax, bx, by, bz, r, saida)
    if t1 <= t2:
        saida[0], saida[1], saida[2] = n0, n1, n2
        return t1
    return t2


def _k_raio_triangulo(ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, tmax: float,
                      v0x: float, v0y: float, v0z: float, v1x: float, v1y: float, v1z: float,
                      v2x: float, v2y: float, v2z: float, saida: List[float]) -> float:
    """Moller-Trumbore, dos dois lados. A normal sai virada contra o raio."""
    e1x, e1y, e1z = v1x - v0x, v1y - v0y, v1z - v0z
    e2x, e2y, e2z = v2x - v0x, v2y - v0y, v2z - v0z
    px, py, pz = dy * e2z - dz * e2y, dz * e2x - dx * e2z, dx * e2y - dy * e2x
    det = e1x * px + e1y * py + e1z * pz
    if abs(det) < 1e-12:
        return INF
    inv = 1.0 / det
    sx, sy, sz = ox - v0x, oy - v0y, oz - v0z
    u = (sx * px + sy * py + sz * pz) * inv
    if u < 0.0 or u > 1.0:
        return INF
    qx, qy, qz = sy * e1z - sz * e1y, sz * e1x - sx * e1z, sx * e1y - sy * e1x
    v = (dx * qx + dy * qy + dz * qz) * inv
    if v < 0.0 or u + v > 1.0:
        return INF
    t = (e2x * qx + e2y * qy + e2z * qz) * inv
    if t < 0.0 or t > tmax:
        return INF
    nx, ny, nz = e1y * e2z - e1z * e2y, e1z * e2x - e1x * e2z, e1x * e2y - e1y * e2x
    n = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    if nx * dx + ny * dy + nz * dz > 0.0:
        n = -n
    saida[0], saida[1], saida[2] = nx / n, ny / n, nz / n
    return t


# --------------------------------------------------------------------- API publica


def _ponto_capsula(c: Capsula, t: float) -> Vec3:
    a, b = c.a, c.b
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def _como_esfera(corpo: Union[Esfera, Capsula], forma: Forma) -> Esfera:
    """A esfera do corpo que conta contra `forma`: a propria esfera, ou a do ponto do eixo da
    capsula mais perto da forma."""
    if isinstance(corpo, Esfera):
        return corpo
    a, b = corpo.a, corpo.b
    if isinstance(forma, Esfera):
        c = forma.centro
        t = _k_param_segmento(c[0], c[1], c[2], *a, *b)
    elif isinstance(forma, AABB):
        t = _k_param_segmento_aabb(*a, *b, *forma.minimo, *forma.maximo)
    else:
        st = [0.0, 0.0]
        _k_params_segmentos(*a, *b, *forma.a, *forma.b, st)
        t = st[0]
    return Esfera(_ponto_capsula(corpo, t), corpo.raio)


def contato(corpo: Union[Esfera, Capsula], forma: Forma) -> Optional[Tuple[Vec3, float]]:
    """Se `corpo` (esfera ou capsula) invade `forma`: (normal que empurra o corpo para fora,
    profundidade). Mover o corpo `normal * profundidade` desfaz a sobreposicao."""
    e = _como_esfera(corpo, forma)
    c, r = e.centro, e.raio
    s = [0.0, 0.0, 0.0]
    if isinstance(forma, AABB):
        p = _k_contato_esfera_aabb(c[0], c[1], c[2], r, *forma.minimo, *forma.maximo, s)
    elif isinstance(forma, Esfera):
        p = _k_contato_esferas(c[0], c[1], c[2], r, *forma.centro, forma.raio, s)
    else:
        t = _k_param_segmento(c[0], c[1], c[2], *forma.a, *forma.b)
        q = _ponto_capsula(forma, t)
        p = _k_contato_esferas(c[0], c[1], c[2], r, q[0], q[1], q[2], forma.raio, s)
    return ((s[0], s[1], s[2]), p) if p > 0.0 else None


def sobrepoe(a: Forma, b: Forma) -> bool:
    """As duas formas se tocam? (qualquer par entre AABB, Esfera e Capsula)"""
    if isinstance(a, AABB) and isinstance(b, AABB):
        return all(a.minimo[k] <= b.maximo[k] and b.minimo[k] <= a.maximo[k] for k in range(3))
    if isinstance(a, AABB):
        a, b = b, a
    return contato(a, b) is not None  # type: ignore[arg-type]


def raycast(raio: Raio, forma: Forma, dist_max: float = INF) -> Optional[Tuple[float, Vec3]]:
    """Primeiro toque do raio na forma ate `dist_max`: (distancia, normal no ponto), ou None."""
    o, d = raio.origem, raio.direcao
    s = [0.0, 0.0, 0.0]
    if isinstance(forma, AABB):
        t = _k_raio_aabb(*o, *d, dist_max, *forma.minimo, *forma.maximo, s)
    elif isinstance(forma, Esfera):
        t = _k_raio_esfera(*o, *d, dist_max, *forma.centro, forma.raio, s)
    else:
        t = _k_raio_capsula(*o, *d, dist_max, *forma.a, *forma.b, forma.raio, s)
    return (t, (s[0], s[1], s[2])) if t != INF and t <= dist_max else None


def raio_triangulo(raio: Raio, v0: Vec3, v1: Vec3, v2: Vec3,
                   dist_max: float = INF) -> Optional[Tuple[float, Vec3]]:
    """Raio contra um triangulo (dos dois lados): (distancia, normal contra o raio) ou None."""
    s = [0.0, 0.0, 0.0]
    t = _k_raio_triangulo(*raio.origem, *raio.direcao, dist_max, *v0, *v1, *v2, s)
    return (t, (s[0], s[1], s[2])) if t != INF and t <= dist_max else None
