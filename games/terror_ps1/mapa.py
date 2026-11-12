# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""O mapa da floresta: 80x80, trilhas ligando sete marcos e o santuario do torii.

`gerar_mapa()` decide ONDE fica cada coisa (dados puros, deterministicos pela semente):
trilhas, arvores, pedras, marcos, os sete amuletos (um por marco), pilhas e armadilhas de
urso (quase todas nas trilhas -- e por onde se anda). `geometria()` transforma isso em
triangulos para o `IRenderer3D`; as malhas dos itens ficam centradas na origem e sao
desenhadas com matriz de modelo.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from games.vitrine_estilos.tres_d import (
    Tri,
    _altura_terra,
    _rot_z,
    bloco,
    chao,
    cone,
    icosaedro,
    lanterna,
    torii,
)

P = Tuple[float, float]
TAMANHO = 40.0  # o mapa vai de -40 a 40 em x e z
ESPACO_ARVORES = 3.4  # distancia minima entre troncos na area jogavel
LIMITE = 37.5  # ate onde se anda (o resto e a parede de arvores)
INICIO: P = (0.0, 34.0)
SANTUARIO: P = (0.0, -30.0)
MARCOS: Dict[str, P] = {
    "cabana": (-22.0, 2.0), "poco": (24.0, -6.0), "arvore_morta": (-18.0, -22.0), "pedras": (20.0, 22.0),
    "jizo": (8.0, -14.0), "troncos": (-8.0, 18.0), "acampamento": (-30.0, -8.0),
}
RAIO_MARCO = {"cabana": 6.0, "poco": 4.0, "arvore_morta": 4.5, "pedras": 5.0, "jizo": 4.5, "troncos": 5.0,
              "acampamento": 5.0}
# onde o amuleto de cada marco fica (relativo ao marco) e a que altura
AMULETO_NO_MARCO = {"cabana": (0.4, 0.6, 0.95), "poco": (0.0, 1.05, 0.95), "arvore_morta": (0.0, 0.85, 0.5),
                    "pedras": (0.0, 0.0, 0.75), "jizo": (3.4, -1.0, 0.45), "troncos": (0.5, 0.0, 0.95),
                    "acampamento": (0.0, 1.9, 0.4)}
TRILHAS: List[List[P]] = [
    [INICIO, (2.0, 24.0), (-4.0, 14.0), (0.0, 4.0), (6.0, -6.0), (8.0, -12.0), (2.0, -24.0), (0.0, -28.0)],
    [(0.0, 4.0), (-12.0, 4.0), (-19.0, 2.0)],
    [(0.0, 4.0), (12.0, 0.0), (22.0, -5.0)],
    [(-22.0, 0.0), (-26.0, -5.0), (-29.0, -6.5)],
    [(0.0, -28.0), (-10.0, -26.0), (-17.0, -22.5)],
    [(2.0, 24.0), (10.0, 27.0), (18.0, 23.0)],
    [(-4.0, 14.0), (-7.0, 17.0)],
    [(12.0, 0.0), (16.0, 12.0), (19.0, 19.0)],
]


def dist_segmento(p: P, a: P, b: P) -> float:
    ax, az, bx, bz = a[0], a[1], b[0], b[1]
    dx, dz = bx - ax, bz - az
    t = 0.0 if dx == dz == 0 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - az) * dz) / (dx * dx + dz * dz)))
    return math.hypot(p[0] - ax - t * dx, p[1] - az - t * dz)


def dist_trilha(p: P) -> float:
    return min(dist_segmento(p, t[i], t[i + 1]) for t in TRILHAS for i in range(len(t) - 1))


@dataclass
class Mapa:
    arvores: List[Tuple[float, float, float, bool]] = field(default_factory=list)  # x, z, altura, seca
    pedras: List[Tuple[float, float, float]] = field(default_factory=list)  # x, z, raio
    amuletos: List[Tuple[float, float, float]] = field(default_factory=list)  # x, z, altura
    pilhas: List[P] = field(default_factory=list)
    armadilhas: List[P] = field(default_factory=list)
    circulos: List[Tuple[float, float, float]] = field(default_factory=list)  # colisao: x, z, raio
    caixas: List[Tuple[float, float, float, float]] = field(default_factory=list)  # colisao: x0, z0, x1, z1
    luzes: List[Tuple[Tuple[float, float, float], Tuple[float, float, float], float]] = field(default_factory=list)
    _grade: Dict[Tuple[int, int], List[Tuple[float, float, float]]] = field(default_factory=dict)

    def montar_grade(self) -> None:
        """Os circulos de colisao por celula de 4x4: a colisao so olha os vizinhos."""
        self._grade = {}
        for c in self.circulos:
            self._grade.setdefault((int(c[0] // 4), int(c[1] // 4)), []).append(c)

    def circulos_perto(self, x: float, z: float) -> List[Tuple[float, float, float]]:
        cx, cz = int(x // 4), int(z // 4)
        return [c for i in (-1, 0, 1) for j in (-1, 0, 1) for c in self._grade.get((cx + i, cz + j), ())]


def gerar_mapa(semente: int = 7) -> Mapa:
    rng = random.Random(semente)
    m = Mapa()
    for nome, (mx, mz) in MARCOS.items():
        dx, dz, y = AMULETO_NO_MARCO[nome]
        m.amuletos.append((mx + dx, mz + dz, y))
    _colisao_dos_marcos(m)

    livres = [INICIO, SANTUARIO] + list(MARCOS.values())
    raios = [5.0, 7.5] + list(RAIO_MARCO.values())
    ocupado: Dict[Tuple[int, int], List[P]] = {}
    for _ in range(4200):  # arvores: longe das trilhas, dos marcos e umas das outras
        x, z = rng.uniform(-TAMANHO - 4, TAMANHO + 4), rng.uniform(-TAMANHO - 4, TAMANHO + 4)
        dentro = abs(x) < LIMITE + 1 and abs(z) < LIMITE + 1
        if dentro and (dist_trilha((x, z)) < 1.8 or any(math.hypot(x - a, z - b) < r for (a, b), r in zip(livres, raios))):
            continue
        cel = (int(x // 4), int(z // 4))
        vizinhos = [p for i in (-1, 0, 1) for j in (-1, 0, 1) for p in ocupado.get((cel[0] + i, cel[1] + j), ())]
        # espaco entre os troncos para enxergar longe; so a borda do mapa e uma parede fechada
        if any(math.hypot(x - a, z - b) < (ESPACO_ARVORES if dentro else 1.3) for a, b in vizinhos):
            continue
        ocupado.setdefault(cel, []).append((x, z))
        seca = rng.random() < 0.12
        m.arvores.append((x, z, rng.uniform(8.0, 13.0), seca))
        m.circulos.append((x, z, 0.35))
    for _ in range(70):  # pedras soltas
        x, z = rng.uniform(-LIMITE, LIMITE), rng.uniform(-LIMITE, LIMITE)
        if dist_trilha((x, z)) > 1.5 and all(math.hypot(x - a, z - b) > r for (a, b), r in zip(livres, raios)):
            r = rng.uniform(0.2, 0.7)
            m.pedras.append((x, z, r))
            if r > 0.35:
                m.circulos.append((x, z, r * 0.9))

    pontos = [(t, i) for t in TRILHAS for i in range(len(t) - 1)]
    while len(m.armadilhas) < 18:  # armadilhas: na trilha (ou rente a ela), longe do inicio e dos itens
        t, i = rng.choice(pontos)
        k = rng.random()
        a, b = t[i], t[i + 1]
        x = a[0] + (b[0] - a[0]) * k + rng.uniform(-0.7, 0.7)
        z = a[1] + (b[1] - a[1]) * k + rng.uniform(-0.7, 0.7)
        longe = [INICIO, SANTUARIO] + [(ax, az) for ax, az, _ in m.amuletos] + m.armadilhas
        if all(math.hypot(x - p[0], z - p[1]) > 4.0 for p in longe):
            m.armadilhas.append((x, z))
    for (ax, az), (bx, bz) in [((-12.0, 4.0), (-19.0, 2.0)), ((12.0, 0.0), (22.0, -5.0)), ((-4.0, 14.0), (0.0, 4.0)),
                               ((10.0, 27.0), (18.0, 23.0)), ((-10.0, -26.0), (-17.0, -22.5))]:
        m.pilhas.append(((ax + bx) / 2 + 1.3, (az + bz) / 2 + 0.8))  # pilhas: na beira da trilha

    m.luzes = [((SANTUARIO[0] - 1.6, 1.0, SANTUARIO[1] + 0.6), (1.5, 0.3, 0.15), 3.0),  # a vela do santuario
               ((-22.0, 1.4, 2.0), (1.1, 0.5, 0.2), 4.5),  # um lampiao esquecido na cabana
               ((-30.0, 0.4, -6.0), (1.3, 0.45, 0.12), 3.5),  # brasas no acampamento
               ((8.0, 0.5, -15.0), (1.0, 0.8, 0.4), 3.0)]  # velas dos jizo
    m.montar_grade()
    return m


def _colisao_dos_marcos(m: Mapa) -> None:
    cx, cz = MARCOS["cabana"]  # paredes da cabana (porta no lado leste)
    m.caixas += [(cx - 2.1, cz - 1.6, cx + 2.1, cz - 1.4), (cx - 2.1, cz + 1.4, cx + 2.1, cz + 1.6),
                 (cx - 2.1, cz - 1.6, cx - 1.9, cz + 1.6), (cx + 1.9, cz - 1.6, cx + 2.1, cz - 0.5),
                 (cx + 1.9, cz + 0.5, cx + 2.1, cz + 1.6), (cx - 0.3, cz + 0.2, cx + 1.1, cz + 1.0)]  # + a mesa
    px, pz = MARCOS["poco"]
    m.circulos.append((px, pz, 1.0))
    ax, az = MARCOS["arvore_morta"]
    m.circulos.append((ax, az, 0.55))
    sx, sz = MARCOS["pedras"]
    m.circulos += [(sx + 3.2 * math.cos(k * math.pi / 4), sz + 3.2 * math.sin(k * math.pi / 4), 0.45) for k in range(8)]
    jx, jz = MARCOS["jizo"]
    m.circulos += [(jx - 2.0 + k * 1.1, jz - 1.6, 0.3) for k in range(6)]
    tx, tz = MARCOS["troncos"]
    m.caixas += [(tx - 3.0, tz - 0.3, tx + 2.5, tz + 0.3), (tx - 1.5, tz + 1.2, tx + 3.0, tz + 1.7)]
    ax, az = MARCOS["acampamento"]
    m.circulos += [(ax, az, 1.3), (ax, az + 2.0, 0.55)]  # a barraca e a fogueira
    sx, sz = SANTUARIO
    m.circulos += [(sx - 1.3, sz, 0.3), (sx + 1.3, sz, 0.3), (sx - 1.6, sz + 0.6, 0.33), (sx + 1.6, sz + 0.6, 0.33)]
    m.caixas.append((sx - 1.6, sz - 5.2, sx + 1.6, sz - 2.8))  # o santuario (honden)


# ------------------------------------------------------------------ geometria

MADEIRA, MADEIRA_ESCURA, PEDRA = (74, 56, 44), (46, 36, 30), (96, 94, 90)


def _pinheiro(x, z, alto, cor) -> List[Tri]:
    """Pinheiro de floresta fechada: tronco alto e fino ate acima da cabeca, copa estreita
    so la em cima. Na altura dos olhos sobram os troncos -- e entre eles, a neblina."""
    tris = bloco((x, 0, z), alto * 0.8, 0.26, 0.1, 0.26, (58, 44, 38))
    base = max(2.6, alto * 0.38)
    for k in range(4):
        y = base + (alto - base) * k / 4
        r = (0.95 - 0.18 * k) * min(1.0, alto / 10)
        tom = tuple(min(255, int(c * (0.8 + 0.1 * k))) for c in cor)
        tris += cone((x, y, z), r, (alto - base) * 0.45, tom, lados=6)
    for k in range(2):  # galhinhos secos no tronco, na altura dos olhos
        b = (x, 1.4 + 0.6 * k, z)
        tris += bloco(b, b[1] + 0.5, 0.04, 0.01, 0.04, (58, 44, 38), 1.2 if k else -1.3, b)
    return tris


def _arvore_seca(x, z, alto) -> List[Tri]:
    tris = bloco((x, 0, z), alto, 0.3, 0.08, 0.3, (58, 50, 44))
    for k, (y, ang, comp) in enumerate(((0.45, 0.9, 1.6), (0.6, -1.0, 1.3), (0.75, 0.7, 1.0))):
        base = (x, alto * y, z + (k - 1) * 0.05)
        tris += bloco(base, base[1] + comp, 0.1, 0.03, 0.1, (58, 50, 44), ang, base)
    return tris


def _cabana(x, z) -> List[Tri]:
    t: List[Tri] = []
    for x0, z0, x1, z1 in [(-2.1, -1.6, 2.1, -1.4), (-2.1, 1.4, 2.1, 1.6), (-2.1, -1.6, -1.9, 1.6),
                           (1.9, -1.6, 2.1, -0.5), (1.9, 0.5, 2.1, 1.6)]:
        t += bloco((x + (x0 + x1) / 2, 0, z + (z0 + z1) / 2), 2.4, x1 - x0, x1 - x0, z1 - z0, MADEIRA)
    t += bloco((x + 2.0, 2.0, z), 2.4, 0.2, 0.2, 1.0, MADEIRA)  # verga da porta
    t += bloco((x, 2.4, z), 3.4, 4.8, 0.25, 3.6, MADEIRA_ESCURA)  # o telhado
    t += bloco((x + 0.4, 0, z + 0.6), 0.85, 1.4, 1.4, 0.8, MADEIRA)  # a mesa
    t += bloco((x - 1.2, 0, z - 0.9), 0.5, 0.5, 0.5, 0.5, MADEIRA_ESCURA)  # um banco
    t += bloco((x - 0.2, 0.85, z + 0.6), 1.15, 0.12, 0.08, 0.12, (200, 150, 80), emissivo=True)  # o lampiao
    return t


def _poco(x, z) -> List[Tri]:
    t: List[Tri] = []
    for k in range(10):
        a = k * 2 * math.pi / 10
        t += bloco((x + 0.85 * math.cos(a), 0, z + 0.85 * math.sin(a)), 0.9, 0.5, 0.45, 0.5, PEDRA)
    t += bloco((x, -0.5, z), 0.05, 1.2, 1.2, 1.2, (8, 8, 10))  # o buraco escuro
    for dx in (-0.95, 0.95):
        t += bloco((x + dx, 0, z), 2.2, 0.14, 0.12, 0.14, MADEIRA)
    t += bloco((x, 2.2, z), 2.65, 2.6, 0.2, 1.4, MADEIRA_ESCURA)
    return t


def _arvore_morta(x, z) -> List[Tri]:
    t = bloco((x, 0, z), 6.5, 0.9, 0.2, 0.8, (52, 44, 40))
    galhos = [(2.6, 1.0, 2.6), (3.4, -1.1, 2.2), (4.3, 0.8, 1.8), (5.0, -0.7, 1.4)]
    for y, ang, comp in galhos:
        base = (x, y, z)
        t += bloco(base, y + comp, 0.16, 0.04, 0.16, (52, 44, 40), ang, base)
        ponta = _rot_z((x, y + comp * 0.8, z), base, ang)
        t += bloco((ponta[0], ponta[1] - 1.1, ponta[2]), ponta[1], 0.12, 0.12, 0.01, (196, 190, 176))  # tiras de pano
    return t


def _pedras(x, z) -> List[Tri]:
    t: List[Tri] = []
    for k in range(8):
        a = k * math.pi / 4
        t += bloco((x + 3.2 * math.cos(a), 0, z + 3.2 * math.sin(a)), 1.7 + 0.4 * (k % 3), 0.7, 0.4, 0.5, PEDRA)
    return t + bloco((x, 0, z), 0.7, 1.4, 1.2, 1.0, (82, 80, 76))  # o altar


def _jizo(x, z) -> List[Tri]:
    t: List[Tri] = []
    for k in range(6):
        jx = x - 2.0 + k * 1.1
        t += bloco((jx, 0, z - 1.6), 0.55, 0.36, 0.28, 0.3, PEDRA)
        t += bloco((jx, 0.4, z - 1.48), 0.56, 0.3, 0.34, 0.08, (150, 30, 30))  # o babador vermelho
        t += icosaedro((jx, 0.68, z - 1.6), 0.14, PEDRA)
    t += bloco((x - 2.5, 0, z - 1.0), 0.15, 0.06, 0.06, 0.06, (240, 220, 160), emissivo=True)  # velas
    t += bloco((x + 3.6, 0, z - 1.0), 0.12, 0.06, 0.06, 0.06, (240, 220, 160), emissivo=True)
    return t


def _troncos(x, z) -> List[Tri]:
    t: List[Tri] = []
    for x0, zz, comp, larg in ((x - 3.0, z, 5.5, 0.55), (x - 1.5, z + 1.45, 4.5, 0.45)):
        base = (x0, larg / 2, zz)
        t += bloco(base, base[1] + comp, larg, larg * 0.85, larg, MADEIRA_ESCURA, -math.pi / 2, base)
    return t


def _acampamento(x, z) -> List[Tri]:
    lona = (70, 78, 64)
    t = bloco((x, 0, z), 1.6, 2.6, 0.1, 2.2, lona)  # a barraca caida
    t += bloco((x + 0.6, 0, z + 0.4), 0.9, 1.4, 0.1, 1.2, (56, 62, 52), 0.35, (x + 0.6, 0, z + 0.4))
    for k in range(7):
        a = k * 2 * math.pi / 7
        t += bloco((x + 0.5 * math.cos(a), 0, z + 2.0 + 0.5 * math.sin(a)), 0.15, 0.18, 0.15, 0.18, PEDRA)
    for k in range(3):
        t += icosaedro((x - 0.15 + 0.15 * k, 0.07, z + 2.0 + 0.1 * (k - 1)), 0.08, (200, 70, 20), emissivo=True)
    return t


def _placa(x, z) -> List[Tri]:
    return bloco((x, 0, z), 1.3, 0.1, 0.1, 0.1, MADEIRA) + bloco((x, 1.0, z), 1.35, 0.8, 0.8, 0.05, MADEIRA)


def geometria(m: Mapa) -> List[Tri]:
    """Tudo que nao se mexe, em triangulos."""
    rng = random.Random(11)

    def terra(x, z):
        tom = rng.uniform(-7, 7)
        if dist_trilha((x, z)) < 1.1:
            return (int(80 + tom), int(74 + tom), int(64 + tom))
        if rng.random() < 0.2:
            return (int(44 + tom), int(52 + tom), int(36 + tom))  # musgo
        return (int(54 + tom), int(47 + tom), int(39 + tom))

    tris = chao(-TAMANHO - 4, TAMANHO + 4, -TAMANHO - 4, TAMANHO + 4, 0.6, terra, _altura_terra)
    for x, z, alto, seca in m.arvores:
        tris += _arvore_seca(x, z, alto * 0.75) if seca else _pinheiro(x, z, alto, (30, 40, 36))
    for x, z, r in m.pedras:
        pts = icosaedro((x, 0.0, z), r, (78, 78, 74))
        tris += [tuple((p[0], max(0.0, p[1]) * 0.6, p[2]) for p in t[:3]) + t[3:] for t in pts]
    rb = random.Random(5)
    for _ in range(300):  # moitas baixas (sem colisao)
        x, z = rb.uniform(-LIMITE, LIMITE), rb.uniform(-LIMITE, LIMITE)
        if dist_trilha((x, z)) > 1.3:
            tris += cone((x, 0, z), rb.uniform(0.3, 0.6), rb.uniform(0.3, 0.7), (34, 46, 34), lados=5)
    construtores = {"cabana": _cabana, "poco": _poco, "arvore_morta": _arvore_morta, "pedras": _pedras,
                    "jizo": _jizo, "troncos": _troncos, "acampamento": _acampamento}
    for nome, (x, z) in MARCOS.items():
        tris += construtores[nome](x, z)
    sx, sz = SANTUARIO
    tris += torii(sx, sz, (100, 30, 26), (64, 20, 18), inclina=math.radians(3))
    tris += lanterna(sx - 1.6, sz + 0.6, (110, 108, 104), (255, 70, 40))
    tris += lanterna(sx + 1.6, sz + 0.6, (110, 108, 104), (0, 0, 0), acesa=False, quebrada=True)
    tris += bloco((sx, 0, sz - 4.0), 2.2, 3.2, 3.2, 2.4, MADEIRA_ESCURA)  # o santuario (honden)
    tris += bloco((sx, 2.2, sz - 4.0), 3.0, 4.0, 0.3, 3.0, (40, 30, 28))
    tris += _placa(INICIO[0] + 1.5, INICIO[1] - 1.0)
    return tris


def malha_amuleto() -> List[Tri]:
    """O omamori: saquinho vermelho com faixa e cordao (centrado na origem)."""
    t = bloco((0, -0.13, 0), 0.13, 0.18, 0.16, 0.05, (190, 30, 34))
    t += bloco((0, 0.0, 0), 0.05, 0.19, 0.17, 0.055, (220, 210, 190), emissivo=False)
    t += bloco((0, 0.13, 0), 0.2, 0.03, 0.03, 0.03, (230, 200, 90))
    return t


def malha_pilha() -> List[Tri]:
    return bloco((0, 0, 0), 0.24, 0.1, 0.1, 0.1, (210, 170, 40)) + bloco((0, 0.24, 0), 0.27, 0.05, 0.05, 0.05, (30, 30, 30))


def malha_armadilha(fechada: bool) -> List[Tri]:
    """A armadilha de urso: base, mola e duas mandibulas de dentes. Aberta, deitada no chao;
    fechada, as mandibulas em pe, mordendo o meio."""
    metal, dente, ferrugem = (88, 84, 78), (128, 122, 114), (86, 58, 42)
    t = bloco((0, 0, 0), 0.03, 0.22, 0.22, 0.22, ferrugem)
    t += bloco((-0.45, 0, 0), 0.03, 0.4, 0.4, 0.06, metal)  # a mola
    for lado in (-1, 1):
        for k in range(7):
            a = math.pi * (k + 0.5) / 7
            if fechada:  # em pe: o arco no plano xy, dentes para o centro
                x, y = 0.32 * math.cos(a), 0.32 * math.sin(a)
                base = (x, y, 0.03 * lado)
                t += bloco(base, y + 0.1, 0.04, 0.0, 0.02, dente, a + math.pi / 2, base)
            else:  # deitada: o arco no chao, dentes para cima
                x, z = 0.32 * math.cos(a), 0.32 * math.sin(a) * lado
                t += bloco((x, 0.02, z), 0.12, 0.04, 0.0, 0.03, dente)
        t += bloco((0, 0, 0.3 * lado) if not fechada else (0, 0.3, 0.03 * lado), 0.04 if not fechada else 0.34,
                   0.64, 0.64, 0.04, metal)
    return t

