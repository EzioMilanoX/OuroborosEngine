# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Construtores de malha para o `IRenderer3D` (ROADMAP M21, passo 1).

Cada construtor devolve uma `Malha`: os tres arrays que `IRenderer3D.criar_malha` recebe
(posicoes (V, 3) float32, cores (V, 3) em 0..255, emissivo (V,) bool), com os triangulos
sem indice e VIRADOS PARA FORA (anti-horario visto de fora, a normal que o backend calcula
aponta para longe do solido) -- a luz por vertice depende disso (o `ModernGLRenderer3D`
desenha os dois lados, mas acende pela normal; o rasterizador de CPU da vitrine descarta as
faces de costas). Planos e terreno ficam virados para cima.

    chao = terreno(relevo, cor=lambda x, z: (90, 76, 52))
    casa = caixa((0, 0, 0), (4, 3, 3), (120, 96, 70)) + cone((2, 3, 1.5), 3.0, 1.6, (90, 40, 30), lados=4)
    id_chao = chao.criar_em(r3d)

Sao funcoes de carga (montam a cena uma vez, vetorizadas em NumPy), nao de quadro. O
`terreno` usa o mesmo `Relevo` (e a mesma diagonal por celula) que a colisao em
`ouroboros.core.colisao3d`: o pe pisa exatamente no chao desenhado.

Vieram dos construtores da vitrine (`games/vitrine_estilos/tres_d.py`), copiados no
TerrorPS1 (`terror_ps1/malhas.py`) e no Biogenia (`biogenia/malhas.py`); `bloco` mantem a
assinatura de la para a troca ser direta, e `Malha.de_triangulos` le o formato antigo
(lista de (v0, v1, v2, cor, emissivo, ...)).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Callable, List, Optional, Sequence, Tuple, Union

import numpy as np

from ouroboros.core.colisao3d import AABB, Relevo
from ouroboros.interfaces.renderer3d import triangulos_para_arrays

if TYPE_CHECKING:
    from ouroboros.interfaces.renderer3d import IRenderer3D

Vec3 = Tuple[float, float, float]
Cor = Tuple[int, int, int]
CorDoChao = Union[Cor, Callable[[float, float], Cor], np.ndarray]


class Malha:
    """Triangulos soltos prontos para o renderer. `+` junta duas malhas (uma chamada de
    desenho em vez de duas)."""

    __slots__ = ("posicoes", "cores", "emissivo")

    def __init__(self, posicoes: np.ndarray, cores: np.ndarray, emissivo: Optional[np.ndarray] = None) -> None:
        pos = np.ascontiguousarray(posicoes, dtype=np.float32).reshape(-1, 3)
        if len(pos) % 3:
            raise ValueError("posicoes precisa ter um multiplo de 3 vertices (triangulos soltos)")
        cor = np.ascontiguousarray(cores, dtype=np.float32).reshape(-1, 3)
        if len(cor) != len(pos):
            raise ValueError("cores precisa ter uma cor por vertice")
        emi = np.zeros(len(pos), dtype=np.bool_) if emissivo is None else np.asarray(emissivo, dtype=np.bool_)
        if emi.shape != (len(pos),):
            raise ValueError("emissivo precisa ter um valor por vertice")
        self.posicoes, self.cores, self.emissivo = pos, cor, emi

    # ------------------------------------------------------------------ montagem
    @staticmethod
    def vazia() -> "Malha":
        return Malha(np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32))

    @staticmethod
    def de_triangulos(tris: Sequence[tuple]) -> "Malha":
        """Do formato antigo (TerrorPS1/Biogenia/vitrine): lista de (v0, v1, v2, cor, emissivo, ...)."""
        if not tris:
            return Malha.vazia()
        return Malha(*triangulos_para_arrays(list(tris)))

    def __add__(self, outra: "Malha") -> "Malha":
        return juntar(self, outra)

    @property
    def triangulos(self) -> int:
        return len(self.posicoes) // 3

    def transformada(self, modelo: np.ndarray) -> "Malha":
        """A malha levada por uma matriz 4x4 (ex.: `renderer3d.translacao_e_giro_y`)."""
        m = np.asarray(modelo, dtype=np.float64)
        p = self.posicoes.astype(np.float64) @ m[:3, :3].T + m[:3, 3]
        if np.linalg.det(m[:3, :3]) < 0:  # espelhar inverte o giro: desvira os triangulos
            p = p.reshape(-1, 3, 3)[:, [0, 2, 1]].reshape(-1, 3)
        return Malha(p, self.cores.copy(), self.emissivo.copy())

    def girada(self, eixo: str, angulo: float, pivo: Vec3 = (0.0, 0.0, 0.0)) -> "Malha":
        """Gira `angulo` radianos em volta do eixo "x", "y" ou "z" passando por `pivo`
        (o `bloco(..., ang, pivo)` da vitrine e `bloco(...).girada("z", ang, pivo)`)."""
        c, s = math.cos(angulo), math.sin(angulo)
        r = {"x": [[1, 0, 0], [0, c, -s], [0, s, c]],
             "y": [[c, 0, s], [0, 1, 0], [-s, 0, c]],
             "z": [[c, -s, 0], [s, c, 0], [0, 0, 1]]}[eixo]
        m = np.eye(4)
        m[:3, :3] = r
        pv = np.asarray(pivo, dtype=np.float64)
        m[:3, 3] = pv - m[:3, :3] @ pv
        return self.transformada(m)

    def com_cor(self, cor: Cor) -> "Malha":
        return Malha(self.posicoes.copy(), np.broadcast_to(np.asarray(cor, np.float32), self.cores.shape), self.emissivo)

    def normais(self) -> np.ndarray:
        """A normal unitaria de cada triangulo (T, 3), como o backend calcula."""
        t = self.posicoes.reshape(-1, 3, 3).astype(np.float64)
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        return n / (np.linalg.norm(n, axis=1)[:, None] + 1e-12)

    def aabb(self) -> AABB:
        """A caixa que envolve a malha (para pôr um colisor grosso no `MundoColisao3D`)."""
        if not len(self.posicoes):
            raise ValueError("malha vazia nao tem caixa")
        mn, mx = self.posicoes.min(axis=0), self.posicoes.max(axis=0)
        return AABB(tuple(float(v) for v in mn), tuple(float(v) for v in mx))

    # ------------------------------------------------------------------ renderer
    def criar_em(self, r3d: "IRenderer3D", dinamica: bool = False) -> int:
        return r3d.criar_malha(self.posicoes, self.cores, self.emissivo, dinamica=dinamica)

    def atualizar_em(self, r3d: "IRenderer3D", malha_id: int) -> None:
        r3d.atualizar_malha(malha_id, self.posicoes, self.cores, self.emissivo)


def juntar(*malhas: Malha) -> Malha:
    """Uma malha so com todas as outras (na ordem)."""
    malhas = tuple(m for m in malhas if m.triangulos)
    if not malhas:
        return Malha.vazia()
    return Malha(np.concatenate([m.posicoes for m in malhas]), np.concatenate([m.cores for m in malhas]),
                 np.concatenate([m.emissivo for m in malhas]))


# ===================================================================== montagem interna

def _orientar(tri: np.ndarray, esperado: np.ndarray) -> np.ndarray:
    """Desvira (troca o 2o e o 3o vertice) os triangulos cuja normal nao aponta para
    `esperado` (T, 3) -- assim nenhum construtor depende de acertar a ordem a mao."""
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    virar = np.einsum("ij,ij->i", n, esperado) < 0
    tri = tri.copy()
    tri[virar, 1], tri[virar, 2] = tri[virar, 2], tri[virar, 1].copy()
    return tri


def _malha(tri: np.ndarray, cor, emissivo: bool) -> Malha:
    """`tri` (T, 3, 3); `cor` uma cor so ou (T, 3) uma por triangulo."""
    t = len(tri)
    cores = np.asarray(cor, dtype=np.float32)
    if cores.ndim == 1:
        cores = np.broadcast_to(cores, (t, 3))
    elif cores.shape != (t, 3):
        raise ValueError(f"cor por triangulo precisa ter shape ({t}, 3)")
    return Malha(tri.reshape(-1, 3), np.repeat(cores, 3, axis=0), np.full(t * 3, bool(emissivo)))


def _fechada(vertices: np.ndarray, faces: Sequence[Tuple[int, int, int]], centro) -> np.ndarray:
    """Os triangulos de um solido convexo, virados para longe do `centro`."""
    v = np.asarray(vertices, dtype=np.float64)
    tri = v[np.asarray(faces, dtype=np.int64)]
    return _orientar(tri, tri.mean(axis=1) - np.asarray(centro, dtype=np.float64))


def _para_cima(tri: np.ndarray) -> np.ndarray:
    esperado = np.zeros((len(tri), 3))
    esperado[:, 1] = 1.0
    return _orientar(tri, esperado)


_FACES_CAIXA = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
                (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def _cores_das_celulas(cor: CorDoChao, xs: np.ndarray, zs: np.ndarray) -> np.ndarray:
    """Uma cor por celula (nz, nx, 3) a partir de uma cor, uma funcao (x, z) do centro da
    celula, ou um array ja pronto."""
    nz, nx = len(zs), len(xs)
    if callable(cor):
        return np.array([[cor(float(x), float(z)) for x in xs] for z in zs], dtype=np.float32)
    arr = np.asarray(cor, dtype=np.float32)
    if arr.shape == (3,):
        return np.broadcast_to(arr, (nz, nx, 3))
    if arr.shape != (nz, nx, 3):
        raise ValueError(f"cores por celula precisa ter shape ({nz}, {nx}, 3)")
    return arr


def _grade_para_triangulos(vx: np.ndarray, vy: np.ndarray, vz: np.ndarray) -> np.ndarray:
    """Vertices de uma grade (nz+1, nx+1) -> triangulos (2 por celula, diagonal do canto
    (i, j) ao (i+1, j+1) -- a mesma do `Relevo`), na ordem celula a celula."""
    p = np.stack([vx, vy, vz], axis=-1)
    a, b = p[:-1, :-1], p[:-1, 1:]
    c, d = p[1:, 1:], p[1:, :-1]
    t1 = np.stack([a, b, c], axis=2)
    t2 = np.stack([a, c, d], axis=2)
    return np.stack([t1, t2], axis=2).reshape(-1, 3, 3)


# ===================================================================== construtores

def caixa(minimo: Vec3, maximo: Vec3, cor: Cor, emissivo: bool = False) -> Malha:
    """Caixa alinhada aos eixos (12 triangulos) -- a par do `AABB(minimo, maximo)` da colisao."""
    (x0, y0, z0), (x1, y1, z1) = minimo, maximo
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
         (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1)]
    centro = ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    return _malha(_fechada(v, _FACES_CAIXA, centro), cor, emissivo)


def bloco(base: Vec3, topo: float, larg_base: float, larg_topo: float, prof: float, cor: Cor,
          emissivo: bool = False) -> Malha:
    """Tronco de piramide (caixa se as larguras forem iguais) com o centro da base em `base`
    e o topo na altura `topo`; largura em x, `prof` em z. A mesma assinatura do `bloco` da
    vitrine/TerrorPS1 (sem `ang`/`pivo`: use `.girada("z", ang, pivo)`)."""
    bx, by, bz = base
    lb, lt, d = larg_base / 2, larg_topo / 2, prof / 2
    v = [(bx - lb, by, bz - d), (bx + lb, by, bz - d), (bx + lb, by, bz + d), (bx - lb, by, bz + d),
         (bx - lt, topo, bz - d), (bx + lt, topo, bz - d), (bx + lt, topo, bz + d), (bx - lt, topo, bz + d)]
    return _malha(_fechada(v, _FACES_CAIXA, (bx, (by + topo) / 2, bz)), cor, emissivo)


def plano(x0: float, x1: float, z0: float, z1: float, cor: CorDoChao, y: float = 0.0,
          passo: Optional[float] = None, emissivo: bool = False) -> Malha:
    """Chao plano virado para cima. Com `passo`, vira uma grade de ladrilhos: triangulo
    grande demais some perto da camera (sem recorte no plano proximo) e a luz por vertice
    precisa de vertices para variar. `cor`: uma cor, uma funcao (x, z) do centro do
    ladrilho, ou (nz, nx, 3)."""
    if passo is None:
        nx = nz = 1
        px, pz = x1 - x0, z1 - z0
    else:
        nx, nz = max(1, round((x1 - x0) / passo)), max(1, round((z1 - z0) / passo))
        px, pz = (x1 - x0) / nx, (z1 - z0) / nz
    xs, zs = x0 + px * np.arange(nx + 1), z0 + pz * np.arange(nz + 1)
    vx, vz = np.meshgrid(xs, zs)
    tri = _para_cima(_grade_para_triangulos(vx, np.full_like(vx, y), vz))
    cores = _cores_das_celulas(cor, xs[:-1] + px / 2, zs[:-1] + pz / 2)
    return _malha(tri, np.repeat(cores.reshape(-1, 3), 2, axis=0), emissivo)


def terreno(relevo: Relevo, cor: CorDoChao, emissivo: bool = False) -> Malha:
    """O chao de um `Relevo` (mapa de alturas), um vertice por amostra. `cor` como em `plano`."""
    alt = relevo.alturas
    nx, nz = relevo.celulas
    x0, _, z0, _ = relevo.limites
    xs, zs = x0 + relevo.passo * np.arange(nx + 1), z0 + relevo.passo * np.arange(nz + 1)
    vx, vz = np.meshgrid(xs, zs)
    tri = _para_cima(_grade_para_triangulos(vx, alt, vz))
    meio = relevo.passo / 2
    cores = _cores_das_celulas(cor, xs[:-1] + meio, zs[:-1] + meio)
    return _malha(tri, np.repeat(cores.reshape(-1, 3), 2, axis=0), emissivo)


def disco(centro: Vec3, raio: float, cor: Cor, lados: int = 16, emissivo: bool = False) -> Malha:
    """Disco horizontal virado para cima (poca, buraco, base de algo)."""
    cx, cy, cz = centro
    a = 2 * np.pi * np.arange(lados) / lados
    borda = np.stack([cx + raio * np.cos(a), np.full(lados, cy), cz + raio * np.sin(a)], axis=1)
    meio = np.broadcast_to(np.asarray(centro, np.float64), (lados, 3))
    tri = np.stack([meio, borda, np.roll(borda, -1, axis=0)], axis=1)
    return _malha(_para_cima(tri), cor, emissivo)


def cilindro(base: Vec3, raio: float, altura: float, cor: Cor, lados: int = 8, raio_topo: Optional[float] = None,
             tampas: bool = True, emissivo: bool = False) -> Malha:
    """Cilindro vertical com o centro da base em `base`. `raio_topo` diferente afina (tronco
    de cone); 0 vira cone. `tampas`: fecha embaixo (e em cima, se o topo tiver raio)."""
    rt = raio if raio_topo is None else raio_topo
    bx, by, bz = base
    a = 2 * np.pi * np.arange(lados) / lados
    ca, sa = np.cos(a), np.sin(a)
    baixo = np.stack([bx + raio * ca, np.full(lados, by), bz + raio * sa], axis=1)
    cima = np.stack([bx + rt * ca, np.full(lados, by + altura), bz + rt * sa], axis=1)
    b2, c2 = np.roll(baixo, -1, axis=0), np.roll(cima, -1, axis=0)
    centro = np.array([bx, by + altura / 2, bz])
    partes = [np.stack([baixo, b2, c2], axis=1)]
    if rt > 0:
        partes.append(np.stack([baixo, c2, cima], axis=1))
    if tampas:
        partes.append(np.stack([np.broadcast_to([bx, by, bz], (lados, 3)), baixo, b2], axis=1))
        if rt > 0:
            partes.append(np.stack([np.broadcast_to([bx, by + altura, bz], (lados, 3)), cima, c2], axis=1))
    tri = np.concatenate(partes)
    # para fora: lados pelo raio (o centro do eixo na altura do triangulo), tampas por cima/baixo
    meio = tri.mean(axis=1)
    esperado = meio - np.stack([np.full(len(tri), bx), meio[:, 1], np.full(len(tri), bz)], axis=1)
    nlados = lados * (2 if rt > 0 else 1)
    if rt == 0:  # cone: o lado tambem aponta um pouco para cima
        esperado[:nlados] = meio[:nlados] - centro
    esperado[nlados:, :] = 0.0
    esperado[nlados:, 1] = np.where(meio[nlados:, 1] > centro[1], 1.0, -1.0)
    return _malha(_orientar(tri, esperado), cor, emissivo)


def cone(base: Vec3, raio: float, altura: float, cor: Cor, lados: int = 8, tampa: bool = True,
         emissivo: bool = False) -> Malha:
    """Cone vertical (pinheiro, telhado de 4 aguas com `lados=4`)."""
    return cilindro(base, raio, altura, cor, lados, raio_topo=0.0, tampas=tampa, emissivo=emissivo)


def _icosfera(subdivisoes: int) -> Tuple[np.ndarray, List[Tuple[int, int, int]]]:
    t = (1 + 5 ** 0.5) / 2
    vs = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
          (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    fs = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
          (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
          (8, 6, 7), (9, 8, 1)]
    vs = [tuple(c / math.sqrt(sum(x * x for x in p)) for c in p) for p in vs]
    for _ in range(subdivisoes):  # cada triangulo vira 4, empurrados para a esfera
        novos, meio = [], {}

        def m(a: int, b: int) -> int:
            k = (min(a, b), max(a, b))
            if k not in meio:
                p = [(vs[a][i] + vs[b][i]) / 2 for i in range(3)]
                n = math.sqrt(sum(x * x for x in p))
                vs.append(tuple(x / n for x in p))
                meio[k] = len(vs) - 1
            return meio[k]

        for a, b, c in fs:
            ab, bc, ca = m(a, b), m(b, c), m(c, a)
            novos += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        fs = novos
    return np.array(vs, dtype=np.float64), fs


def esfera(centro: Vec3, raio: float, cor: Cor, subdivisoes: int = 1, emissivo: bool = False) -> Malha:
    """Icosfera: 20 triangulos (`subdivisoes=0`, o icosaedro low poly), 80, 320..."""
    v, fs = _icosfera(subdivisoes)
    return _malha(_fechada(np.asarray(centro) + v * raio, fs, centro), cor, emissivo)


def _area_xz(pts: np.ndarray) -> float:
    x, z = pts[:, 0], pts[:, 1]
    return 0.5 * float(np.sum(x * np.roll(z, -1) - np.roll(x, -1) * z))


def triangular_poligono(contorno: Sequence[Tuple[float, float]]) -> List[Tuple[int, int, int]]:
    """Triangula um poligono simples (convexo ou nao, sem furos nem auto-intersecao) por
    corte de orelhas. Devolve triplas de indices do `contorno`."""
    pts = np.asarray(contorno, dtype=np.float64)
    if len(pts) < 3:
        raise ValueError("poligono precisa de pelo menos 3 pontos")
    area = _area_xz(pts)
    if abs(area) < 1e-12:
        raise ValueError("poligono degenerado (area zero)")
    idx = list(range(len(pts))) if area > 0 else list(range(len(pts)))[::-1]

    def cruz(a, b, c) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def dentro(p, a, b, c) -> bool:
        return cruz(a, b, p) >= 0 and cruz(b, c, p) >= 0 and cruz(c, a, p) >= 0

    tris: List[Tuple[int, int, int]] = []
    while len(idx) > 3:
        m = len(idx)
        for k in range(m):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cruz(a, b, c) <= 1e-12:
                continue  # vertice reflexo ou colinear: nao e orelha
            if any(dentro(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            del idx[k]
            break
        else:
            colinear = next((k for k in range(m) if abs(cruz(pts[idx[k - 1]], pts[idx[k]], pts[idx[(k + 1) % m]]))
                             <= 1e-12), None)
            if colinear is None:
                raise ValueError("poligono invalido (auto-intersecao?)")
            del idx[colinear]
    if abs(cruz(pts[idx[0]], pts[idx[1]], pts[idx[2]])) > 1e-12:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def extrusao(contorno: Sequence[Tuple[float, float]], y0: float, y1: float, cor: Cor, tampas: bool = True,
             emissivo: bool = False) -> Malha:
    """Um poligono (x, z) levantado de `y0` a `y1`: parede de casa, muro em L, plataforma,
    pedra recortada. Convexo ou nao, em qualquer sentido."""
    pts = np.asarray(contorno, dtype=np.float64)
    n = len(pts)
    sinal = 1.0 if _area_xz(pts) > 0 else -1.0
    p, q = pts, np.roll(pts, -1, axis=0)
    a0 = np.stack([p[:, 0], np.full(n, y0), p[:, 1]], axis=1)
    b0 = np.stack([q[:, 0], np.full(n, y0), q[:, 1]], axis=1)
    a1, b1 = a0.copy(), b0.copy()
    a1[:, 1] = b1[:, 1] = y1
    paredes = np.concatenate([np.stack([a0, b0, b1], axis=1), np.stack([a0, b1, a1], axis=1)])
    e = q - p
    fora = np.stack([sinal * e[:, 1], np.zeros(n), -sinal * e[:, 0]], axis=1)  # normal para fora da aresta
    partes = [_orientar(paredes, np.concatenate([fora, fora]))]
    if tampas:
        faces = np.asarray(triangular_poligono(contorno), dtype=np.int64)
        for y, sentido in ((y1, 1.0), (y0, -1.0)):
            v = np.stack([pts[:, 0], np.full(n, y), pts[:, 1]], axis=1)
            tri = v[faces]
            esperado = np.zeros((len(tri), 3))
            esperado[:, 1] = sentido
            partes.append(_orientar(tri, esperado))
    return _malha(np.concatenate(partes), cor, emissivo)
