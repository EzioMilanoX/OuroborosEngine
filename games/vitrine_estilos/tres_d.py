# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Os estilos 3D da vitrine: um renderizador 3D minimo (numpy + pygame) que mostra o que uma
engine 3D faz com poligonos -- e como a MESMA tecnica sai bonita ou macabra.

Cada objeto e uma MALHA de triangulos virados para fora. A camera leva os vertices para o
espaco dela e os projeta em perspectiva; triangulos de costas para a camera sao descartados
(backface culling). A luz e calculada em cada VERTICE, como no PS1 e nas GPUs antigas:
ceu e chao em volta (luz hemisferica), luzes direcionais, pontuais e um foco (lanterna).

    lowpoly  bonito: uma cor por face (flat shading), luz de tres pontos (chave quente por
             tras, preenchimento frio pela frente, ambiente do ceu), sombras projetadas no
             chao, lanternas que acendem o que esta perto, brilho no que emite luz e o pintor
             (do longe para o perto) em camadas: fundo, chao, sombras, objetos
    terror   o que o PS1 fazia, e por que assusta: 320x180 ampliado sem suavizar; vertices
             grudados no pixel inteiro (a malha treme quando a camera mexe); cor interpolada
             sem correcao de perspectiva; z-buffer por pixel; neblina preta que engole a
             distancia; cor de 15 bits com pontilhado; so a lanterna ilumina -- e o que ela
             nao toca, o jogador imagina
"""
from __future__ import annotations

import math
import random
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np
import pygame

from games.vitrine_estilos.arte import ALTURA, BAYER, LARGURA, QUADROS, _borrar, _degrade, pose

Vec = Tuple[float, float, float]
Cor = Tuple[int, int, int]
Tri = Tuple[Vec, Vec, Vec, Cor, bool, int]  # tres vertices, a cor, se emite luz, a camada
FUNDO, CHAO, OBJETO = 0, 1, 2


def _unit(v) -> np.ndarray:
    v = np.asarray(v, dtype=np.float64)
    return v / np.linalg.norm(v)


# ------------------------------------------------------------------ malhas

def _rot_z(p: Vec, pivo: Vec, ang: float) -> Vec:
    c, s = math.cos(ang), math.sin(ang)
    x, y = p[0] - pivo[0], p[1] - pivo[1]
    return (pivo[0] + x * c - y * s, pivo[1] + x * s + y * c, p[2])


def _normal(a: Vec, b: Vec, c: Vec) -> Vec:
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    return (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])


def _fechada(v: Sequence[Vec], faces, cor, emissivo=False, camada=OBJETO, centro=None) -> List[Tri]:
    """Os triangulos de uma malha fechada, cada um virado para FORA (a normal longe do
    centro): e o que o backface culling e a luz esperam."""
    c = centro or tuple(sum(p[i] for p in v) / len(v) for i in range(3))
    out: List[Tri] = []
    for i, j, k in faces:
        a, b, d = v[i], v[j], v[k]
        n = _normal(a, b, d)
        m = [(a[x] + b[x] + d[x]) / 3 - c[x] for x in range(3)]
        if n[0] * m[0] + n[1] * m[1] + n[2] * m[2] < 0:
            b, d = d, b
        out.append((a, b, d, cor, emissivo, camada))
    return out


def _para_cima(a: Vec, b: Vec, c: Vec, cor: Cor, camada: int) -> Tri:
    return (a, b, c, cor, False, camada) if _normal(a, b, c)[1] >= 0 else (a, c, b, cor, False, camada)


_FACES_BLOCO = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7), (0, 1, 5), (0, 5, 4),
                (1, 2, 6), (1, 6, 5), (2, 3, 7), (2, 7, 6), (3, 0, 4), (3, 4, 7)]


def bloco(base, topo, larg_base, larg_topo, prof, cor, ang=0.0, pivo=None, emissivo=False) -> List[Tri]:
    """Tronco de piramide (caixa se as larguras forem iguais) da `base` ate a altura `topo`,
    girado `ang` em volta de `pivo`: 8 vertices, 12 triangulos."""
    bx, by, bz = base
    lb, lt, d = larg_base / 2, larg_topo / 2, prof / 2
    v = [(bx - lb, by, bz - d), (bx + lb, by, bz - d), (bx + lb, by, bz + d), (bx - lb, by, bz + d),
         (bx - lt, topo, bz - d), (bx + lt, topo, bz - d), (bx + lt, topo, bz + d), (bx - lt, topo, bz + d)]
    if ang:
        v = [_rot_z(p, pivo or base, ang) for p in v]
    return _fechada(v, _FACES_BLOCO, cor, emissivo)


def icosaedro(centro, raio, cor, emissivo=False, sub=0, camada=OBJETO) -> List[Tri]:
    t = (1 + 5 ** 0.5) / 2
    vs = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
          (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    fs = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
          (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
          (8, 6, 7), (9, 8, 1)]
    vs = [tuple(c / math.sqrt(sum(x * x for x in p)) for c in p) for p in vs]
    for _ in range(sub):  # cada triangulo vira 4, empurrados para a esfera
        novos, meio = [], {}

        def m(a, b):
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
    p = [(centro[0] + x * raio, centro[1] + y * raio, centro[2] + z * raio) for x, y, z in vs]
    return _fechada(p, fs, cor, emissivo, camada, centro)


def cone(base, raio, altura, cor, lados=7) -> List[Tri]:
    bx, by, bz = base
    pts = [(bx + raio * math.cos(2 * math.pi * i / lados), by, bz + raio * math.sin(2 * math.pi * i / lados))
           for i in range(lados)]
    v = pts + [(bx, by + altura, bz)]
    return _fechada(v, [(i, (i + 1) % lados, lados) for i in range(lados)], cor, centro=(bx, by + altura / 3, bz))


def chao(x0, x1, z0, z1, passo, cor: Callable[[float, float], Cor],
         altura: Callable[[float, float], float] = lambda x, z: 0.0, camada=CHAO, passo_z=None) -> List[Tri]:
    """Uma grade de ladrilhos: triangulo grande demais some perto da camera, e a luz por
    vertice precisa de vertices para variar."""
    tris: List[Tri] = []

    def p(x, z):
        return (x, altura(x, z), z)

    pz = passo_z or passo
    for j in range(round((z1 - z0) / pz)):
        for i in range(round((x1 - x0) / passo)):
            xa, za = x0 + i * passo, z0 + j * pz
            a, b, c, d = p(xa, za), p(xa + passo, za), p(xa + passo, za + pz), p(xa, za + pz)
            k = cor(xa + passo / 2, za + pz / 2)
            tris += [_para_cima(a, b, c, k, camada), _para_cima(a, c, d, k, camada)]
    return tris


def montanhas(z0, z1, x0, x1, n, alto, seed, cor) -> List[Tri]:
    rng = random.Random(seed)
    alt = [[max(0.0, rng.uniform(0.2, 1.0) * alto * math.sin(math.pi * j / n)) for _ in range(n + 1)]
           for j in range(n + 1)]
    return chao(x0, x1, z0, z1, (x1 - x0) / n, lambda x, z: cor,
                lambda x, z: alt[round((z - z0) / (z1 - z0) * n)][round((x - x0) / (x1 - x0) * n)], FUNDO,
                (z1 - z0) / n)


# ------------------------------------------------------------------ a cena

def torii(x, z, vermelho, escuro, inclina=0.0) -> List[Tri]:
    tris: List[Tri] = []
    for dx in (-1.3, 1.3):  # dois pilares, a viga de cima e a de baixo
        tris += bloco((x + dx, 0, z), 3.0, 0.42, 0.34, 0.34, vermelho)
    tris += bloco((x, 3.0, z), 3.3, 4.2, 4.6, 0.5, vermelho)
    tris += bloco((x, 3.3, z), 3.42, 4.7, 4.9, 0.56, escuro)
    tris += bloco((x, 2.35, z), 2.55, 3.2, 3.2, 0.3, escuro)
    if inclina:
        tris = [tuple(_rot_z(p, (x, 0, z), inclina) for p in t[:3]) + t[3:] for t in tris]
    return tris


def lanterna(x, z, pedra, luz, acesa=True, quebrada=False) -> List[Tri]:
    """Um toro de pedra: base, haste, plataforma, a caixa da chama, o telhado e a ponta."""
    escura = tuple(int(c * 0.75) for c in pedra)
    tris = bloco((x, 0, z), 0.15, 0.5, 0.45, 0.5, pedra) + bloco((x, 0.15, z), 0.75, 0.18, 0.15, 0.18, pedra)
    if quebrada:
        return tris + bloco((x + 0.5, 0, z + 0.3), 0.2, 0.62, 0.55, 0.5, escura)  # o telhado caido
    tris += bloco((x, 0.75, z), 0.85, 0.42, 0.42, 0.42, pedra)
    tris += bloco((x, 0.85, z), 1.13, 0.28, 0.28, 0.28, luz if acesa else escura, emissivo=acesa)
    tris += bloco((x, 1.13, z), 1.33, 0.64, 0.1, 0.64, escura)
    return tris + icosaedro((x, 1.38, z), 0.06, escura)


def pinheiro(x, z, alto, cor) -> List[Tri]:
    tris = bloco((x, 0, z), alto * 0.3, 0.2, 0.14, 0.2, (64, 46, 40))
    for k in range(3):
        tom = tuple(min(255, int(c * (0.85 + 0.12 * k))) for c in cor)
        tris += cone((x, alto * (0.2 + 0.22 * k), z), alto * 0.27 * (1 - 0.24 * k), alto * 0.42, tom)
    return tris


PALETA_LP = {"hakama": (70, 78, 136), "kimono": (230, 222, 206), "obi": (190, 50, 60), "pele": (236, 196, 164),
             "cabelo": (40, 32, 48), "cabo": (50, 30, 40), "tsuba": (200, 160, 70), "aco": (226, 234, 244),
             "sandalia": (90, 60, 44), "bainha": (36, 26, 40), "corte": (220, 250, 255)}
PALETA_TERROR = {"hakama": (34, 34, 42), "kimono": (128, 122, 112), "obi": (84, 20, 20), "pele": (176, 168, 158),
                 "cabelo": (16, 14, 16), "cabo": (24, 18, 18), "tsuba": (90, 80, 60), "aco": (170, 172, 178),
                 "sandalia": (30, 24, 20), "bainha": (20, 16, 18), "corte": (150, 160, 170)}


def espadachim(f: Dict[str, object], px: float, pz: float, pal: Dict[str, Cor]) -> List[Tri]:
    """O espadachim da cena 2D, em blocos: segue a mesma pose (respiracao, braco e espada)."""
    r = -0.01 * f["respira"]
    tris: List[Tri] = []
    for dx in (-0.2, 0.2):
        tris += bloco((px + dx, 0, pz + 0.08), 0.08, 0.16, 0.14, 0.3, pal["sandalia"])
    tris += bloco((px, 0.05, pz), 0.9, 0.95, 0.55, 0.5, pal["hakama"])
    tris += bloco((px, 0.9, pz), 1.45 + r, 0.55, 0.64, 0.36, pal["kimono"])
    tris += bloco((px, 0.86, pz), 1.0, 0.6, 0.6, 0.4, pal["obi"])
    tris += icosaedro((px + 0.04, 1.66 + r, pz), 0.19, pal["pele"], sub=1)
    tris += bloco((px - 0.02, 1.76 + r, pz - 0.03), 1.9 + r, 0.42, 0.2, 0.36, pal["cabelo"])
    tris += icosaedro((px - 0.05, 1.96 + r, pz - 0.08), 0.08, pal["cabelo"])  # o coque
    tris += bloco((px - 0.05, 0.95, pz - 0.26), 1.85, 0.07, 0.05, 0.07, pal["bainha"], 1.95, (px - 0.05, 0.95, pz))
    ombro_b = (px - 0.3, 1.42 + r, pz - 0.12)  # o braco de tras, segurando a bainha
    tris += bloco((ombro_b[0], ombro_b[1] - 0.48, ombro_b[2]), ombro_b[1], 0.13, 0.24, 0.16, pal["kimono"], -0.2, ombro_b)
    ombro, mao = f["braco"]
    ang = math.atan2(-(mao[1] - ombro[1]), mao[0] - ombro[0])  # o angulo do braco na cena 2D (y para cima)
    piv = (px + 0.2, 1.38 + r, pz + 0.22)
    tris += bloco(piv, piv[1] + 0.5, 0.26, 0.13, 0.17, pal["kimono"], ang - math.pi / 2, piv)  # a manga
    p = _rot_z((piv[0], piv[1] + 0.5, piv[2]), piv, ang - math.pi / 2)
    tris += icosaedro(p, 0.07, pal["pele"])  # a mao
    a, y = -f["ang_espada"] - math.pi / 2, p[1]
    tris += bloco((p[0], y - 0.06, p[2]), y + 0.18, 0.055, 0.05, 0.055, pal["cabo"], a, p)
    tris += bloco((p[0], y + 0.18, p[2]), y + 0.21, 0.15, 0.15, 0.15, pal["tsuba"], a, p)
    tris += bloco((p[0], y + 0.21, p[2]), y + 1.15, 0.05, 0.015, 0.035, pal["aco"], a, p)
    if f["corte"]:  # o rastro do corte: uma fita de triangulos que emite luz
        _, _, _, a0, a1, _ = f["corte"]
        pts = [(piv[0] + math.cos(-(a0 + (a1 - a0) * i / 9)) * rr, piv[1] + math.sin(-(a0 + (a1 - a0) * i / 9)) * rr,
                pz + 0.3) for i in range(10) for rr in (1.15, 1.45)]
        for i in range(9):
            q0, q1, q2, q3 = pts[2 * i], pts[2 * i + 1], pts[2 * i + 3], pts[2 * i + 2]
            tris += [(q0, q1, q2, pal["corte"], True, OBJETO), (q0, q2, q3, pal["corte"], True, OBJETO)]
    return tris


# ------------------------------------------------------------------ camera e luz

def _arrays(tris: List[Tri]):
    V = np.array([t[:3] for t in tris], dtype=np.float64)  # (N, 3 vertices, xyz)
    base = np.array([t[3] for t in tris], dtype=np.float64)
    emiss = np.array([t[4] for t in tris], dtype=bool)
    camada = np.array([t[5] for t in tris])
    n = np.cross(V[:, 1] - V[:, 0], V[:, 2] - V[:, 0])
    n /= np.linalg.norm(n, axis=1)[:, None] + 1e-12
    return V, base, emiss, camada, n


def _camera(pos, alvo):
    pos = np.asarray(pos, dtype=np.float64)
    frente = _unit(np.asarray(alvo) - pos)
    direita = _unit(np.cross(frente, [0, 1, 0]))
    return pos, direita, np.cross(direita, frente), frente


def _projetar(P, cam, focal, w, h):
    pos, direita, cima, frente = cam
    rel = P - pos
    xv, yv, zv = rel @ direita, rel @ cima, rel @ frente
    zc = np.maximum(zv, 1e-3)
    return w / 2 + focal * xv / zc, h / 2 - focal * yv / zc, zv


def _passo(a, b, x):
    k = np.clip((x - a) / (b - a), 0, 1)
    return k * k * (3 - 2 * k)


def iluminar(V, n, base, emiss, ceu, solo, luzes) -> np.ndarray:
    """A cor em cada vertice (N, 3, rgb): luz hemisferica (ceu em cima, chao embaixo) mais
    cada luz: ("dir", direcao, cor), ("ponto", pos, cor, alcance) ou
    ("foco", pos, cor, alcance, direcao, cos_borda, cos_miolo). Quem emite luz fica com a
    propria cor."""
    amb = solo + (np.asarray(ceu) - solo) * (n[:, 1:2] * 0.5 + 0.5)
    luz = np.repeat(amb[:, None, :], 3, axis=1)
    nn = n[:, None, :]
    for spec in luzes:
        if spec[0] == "dir":
            luz += np.clip((nn * spec[1]).sum(-1), 0, 1)[..., None] * spec[2]
            continue
        pos, cor, alcance = spec[1], spec[2], spec[3]
        d = pos - V
        dist = np.linalg.norm(d, axis=-1) + 1e-9
        k = np.clip((nn * d).sum(-1) / dist, 0, 1) * np.clip(1 - dist / alcance, 0, 1) ** 2
        if spec[0] == "foco":
            k = k * _passo(spec[5], spec[6], ((-d / dist[..., None]) * spec[4]).sum(-1))
        luz += k[..., None] * cor
    return np.where(emiss[:, None, None], base[:, None, :], base[:, None, :] * luz)


# ------------------------------------------------------------------ low poly (bonito)

CHAVE = _unit((0.55, 0.55, -0.62))  # o por do sol, atras e a direita: sombras longas para a camera
LANTERNAS_LP = ((0.7, -0.9), (4.7, -0.9))
NEVOA_LP = np.array([200.0, 130.0, 140.0])


def cena_lowpoly(q: int) -> List[Tri]:
    t = q / QUADROS
    rng = random.Random(6)
    tris = montanhas(-34, -18, -40, 40, 10, 9.0, 3, (120, 84, 140))
    tris += montanhas(-18, -9, -30, 30, 8, 3.5, 8, (90, 120, 92))

    def grama(x, z):
        tom = rng.uniform(-8, 8)
        if abs(x - 2.7) < 1.0 and z > -1.5:  # o caminho de pedra ate o torii
            return (int(150 + tom), int(138 + tom), int(128 + tom))
        return (int(86 + tom), int(130 + tom), int(90 + tom))

    tris += chao(-24, 24, -18, 10, 1.0, grama)
    tris += icosaedro((8.5, 7.6, -30), 2.2, (255, 238, 204), emissivo=True, sub=1, camada=FUNDO)  # a lua
    tris += torii(2.7, -1.5, (214, 60, 50), (150, 36, 40))
    for x, z in LANTERNAS_LP:
        tris += lanterna(x, z, (160, 156, 150), (255, 214, 140))
    arv = random.Random(21)
    for _ in range(22):
        x, z = arv.uniform(-16, 16), arv.uniform(-16, -5)
        if abs(x - 2.7) > 2.2:
            tris += pinheiro(x, z, arv.uniform(3.5, 6.0), (44, 84, 66))
    tris += pinheiro(-5.4, -3.0, 5.5, (40, 78, 62))
    tris += espadachim(pose(q), -1.6, 0.0, PALETA_LP)
    for k in range(7):  # vaga-lumes, num laco que fecha
        fi = k * 0.9
        c = (2.7 + 2.4 * math.cos(fi * 2.1) + 0.3 * math.sin(2 * math.pi * t + fi),
             0.7 + 0.5 * (k % 3) / 2 + 0.2 * math.sin(4 * math.pi * t + fi),
             -0.6 + 0.8 * math.sin(fi * 1.7) + 0.3 * math.cos(2 * math.pi * t + fi))
        tris += icosaedro(c, 0.035, (255, 226, 130), emissivo=True)
    return tris


def lowpoly(q: int) -> pygame.Surface:
    s = 2
    w, h = LARGURA * s, ALTURA * s
    img = pygame.Surface((w, h))
    _degrade(img, (40, 30, 84), (236, 150, 112), 0, int(h * 0.62))
    img.fill((236, 150, 112), (0, int(h * 0.62), w, h))
    rng = random.Random(4)
    for _ in range(40):  # estrelas no alto do ceu
        pygame.draw.circle(img, (255, 236, 230), (rng.randrange(w), rng.randrange(int(h * 0.25))), rng.choice((1, 2)))

    V, base, emiss, camada, n = _arrays(cena_lowpoly(q))
    yaw = math.radians(7 * math.sin(q / QUADROS * 2 * math.pi))  # a camera passeia: e 3D
    cam = _camera((math.sin(yaw) * 9.0, 1.9, math.cos(yaw) * 9.0), (0.6, 1.4, -1.0))
    focal = (w / 2) / math.tan(math.radians(26))
    sx, sy, zv = _projetar(V, cam, focal, w, h)

    luzes = [("dir", CHAVE, np.array([0.95, 0.72, 0.55])),  # chave: quente, por tras
             ("dir", _unit((-0.5, 0.35, 0.8)), np.array([0.30, 0.33, 0.52]))]  # preenchimento: frio
    luzes += [("ponto", np.array([x, 1.0, z]), np.array([1.6, 1.0, 0.45]), 3.6) for x, z in LANTERNAS_LP]
    cor = iluminar(V, n, base, emiss, np.array([0.34, 0.27, 0.50]), np.array([0.20, 0.19, 0.15]), luzes).mean(1)
    dist = zv.mean(axis=1)
    nevoa = np.clip((dist - 12) / 30, 0, 0.75)[:, None]  # o longe some na cor do ceu
    cor = np.where(emiss[:, None], cor, cor + (NEVOA_LP - cor) * nevoa)
    cor = np.clip(cor, 0, 255).astype(int)
    visivel = (((n * (V[:, 0] - cam[0])).sum(1) < 0) | emiss) & (zv.min(axis=1) > 0.2)

    # sombras: cada triangulo de objeto projetado no chao ao longo da luz chave; pintadas
    # numa camada so (sobreposicoes nao escurecem duas vezes) e multiplicadas no chao
    obj = (camada == OBJETO) & ~emiss
    S = V[obj] - (V[obj][..., 1:2] / CHAVE[1]) * CHAVE
    ssx, ssy, szv = _projetar(S, cam, focal, w, h)
    sombra = pygame.Surface((w, h))
    sombra.fill((255, 255, 255))
    for i in np.nonzero(szv.min(axis=1) > 0.2)[0]:
        pygame.draw.polygon(sombra, (132, 118, 170), list(zip(ssx[i], ssy[i])))

    luz = pygame.Surface((w, h))  # o que emite luz, para o brilho em volta
    pintou_sombra = False
    for i in np.lexsort((-dist, camada)):  # o pintor: por camada, e do longe para o perto
        if not visivel[i]:
            continue
        if camada[i] == OBJETO and not pintou_sombra:
            img.blit(sombra, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
            pintou_sombra = True
        pts = list(zip(sx[i], sy[i]))
        pygame.draw.polygon(img, cor[i], pts)
        if emiss[i]:
            pygame.draw.polygon(luz, cor[i], pts)
    for div, peso in ((8, 0.35), (24, 0.22)):
        b = _borrar(luz, div)
        b.fill((int(255 * peso),) * 3, special_flags=pygame.BLEND_RGB_MULT)
        img.blit(b, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return pygame.transform.smoothscale(img, (LARGURA, ALTURA))


# ------------------------------------------------------------------ terror (o PS1)

W_PS1, H_PS1 = 320, 180
NEVOA_TERROR = np.array([5.0, 5.0, 8.0])
VULTO = (6.6, -8.5)


def _altura_terra(x: float, z: float) -> float:
    return 0.12 * math.sin(x * 1.3) * math.cos(z * 1.1) + 0.05 * math.sin(x * 3.1 + z * 2.3)


def vulto(x: float, z: float) -> List[Tri]:
    """Alto demais, magro demais, bracos ate abaixo dos joelhos, dedos compridos e a cabeca
    alongada e torta, com olhos e boca escuros. Olha para +z (o jogo gira para o jogador)."""
    pele, escuro = (150, 144, 132), (16, 10, 10)
    tris: List[Tri] = []
    for dx in (-0.09, 0.09):  # pernas finas
        tris += bloco((x + dx, 0, z), 1.05, 0.07, 0.09, 0.08, pele)
    tris += bloco((x, 1.0, z), 1.95, 0.2, 0.38, 0.16, pele)  # tronco: estreito embaixo, ombro largo
    for dx in (-0.22, 0.22):  # bracos compridos demais
        tris += bloco((x + dx, 0.55, z), 1.92, 0.05, 0.08, 0.06, pele)
        for k in (-1, 0, 1):
            tris += bloco((x + dx + k * 0.022, 0.36, z + 0.01), 0.56, 0.012, 0.014, 0.012, pele)
    tris += bloco((x, 1.93, z), 2.22, 0.06, 0.055, 0.06, pele)  # pescoco comprido
    cy = 2.38
    cabeca = icosaedro((x, cy, z), 0.14, pele, sub=1)
    cabeca = [tuple((p[0], cy + (p[1] - cy) * 1.45, p[2]) for p in t[:3]) + t[3:] for t in cabeca]
    for dx in (-0.05, 0.05):  # os olhos
        cabeca += bloco((x + dx, cy + 0.03, z + 0.13), cy + 0.08, 0.045, 0.04, 0.04, escuro)
    cabeca += bloco((x, cy - 0.15, z + 0.12), cy - 0.04, 0.025, 0.035, 0.04, escuro)  # a boca, aberta
    pivo = (x, 2.22, z)  # a cabeca tomba de lado
    return tris + [tuple(_rot_z(p, pivo, 0.38) for p in t[:3]) + t[3:] for t in cabeca]


def cena_terror(q: int) -> List[Tri]:
    return cena_terror_estatica() + espadachim(pose(q), 2.7, -1.2, PALETA_TERROR) + vulto(*VULTO)


def cena_terror_estatica(passo: float = 0.75) -> List[Tri]:
    """O que nao se mexe: chao, torii, lanternas e pinheiros (o jogo em 3D tambem usa)."""
    rng = random.Random(13)

    def terra(x, z):
        tom = rng.uniform(-7, 7)
        if abs(x - 2.7) < 0.9 and z > -1.5:
            return (int(78 + tom), int(74 + tom), int(68 + tom))
        return (int(54 + tom), int(48 + tom), int(40 + tom))

    tris = chao(-10, 12, -20, 8, passo, terra, _altura_terra)
    tris += torii(2.7, -1.5, (100, 30, 26), (64, 20, 18), inclina=math.radians(4))
    tris += lanterna(1.1, -1.0, (110, 108, 104), (255, 70, 40))
    tris += lanterna(4.4, -0.9, (110, 108, 104), (0, 0, 0), acesa=False, quebrada=True)
    for x, z, alto in pinheiros_terror():
        tris += pinheiro(x, z, alto, (30, 40, 36))
    return tris


def pinheiros_terror() -> List[Tuple[float, float, float]]:
    """(x, z, altura) de cada pinheiro da noite do torii."""
    arv = random.Random(31)
    out = []
    for _ in range(48):
        x, z, alto = arv.uniform(-10, 12), arv.uniform(-20, 4), arv.uniform(5.0, 8.0)
        perto = z > -3.5 and abs(x - 2.5) < 6.5  # nada colado na camera tampando a cena
        if perto or (abs(x - 2.7) < 2.6 and z > -12) or math.hypot(x - VULTO[0], z - VULTO[1]) < 0.9:
            continue
        out.append((x, z, alto))
    return out


def rasterizar(sx, sy, zv, cores, fundo: np.ndarray):
    """Z-buffer por pixel, o que uma GPU faz: cada triangulo testa a profundidade de cada
    pixel e so pinta se estiver mais perto do que o que ja esta la. A cor e interpolada
    entre os vertices (Gouraud) sem correcao de perspectiva -- o afim do PS1."""
    h, w = fundo.shape[:2]
    img = fundo.copy()
    zbuf = np.full((h, w), np.inf)
    for xa, ya, za, c in zip(sx, sy, zv, cores):
        x0, x1 = max(int(xa.min()), 0), min(int(math.ceil(xa.max())) + 1, w)
        y0, y1 = max(int(ya.min()), 0), min(int(math.ceil(ya.max())) + 1, h)
        if x0 >= x1 or y0 >= y1:
            continue
        area = (xa[1] - xa[0]) * (ya[2] - ya[0]) - (ya[1] - ya[0]) * (xa[2] - xa[0])
        if abs(area) < 1e-6:
            continue
        px = np.arange(x0, x1) + 0.5
        py = np.arange(y0, y1)[:, None] + 0.5
        b0 = ((xa[2] - xa[1]) * (py - ya[1]) - (ya[2] - ya[1]) * (px - xa[1])) / area
        b1 = ((xa[0] - xa[2]) * (py - ya[2]) - (ya[0] - ya[2]) * (px - xa[2])) / area
        b2 = 1.0 - b0 - b1
        z = b0 * za[0] + b1 * za[1] + b2 * za[2]
        zb = zbuf[y0:y1, x0:x1]
        m = (b0 >= 0) & (b1 >= 0) & (b2 >= 0) & (z < zb)
        if not m.any():
            continue
        zb[m] = z[m]
        img[y0:y1, x0:x1][m] = (b0[..., None] * c[0] + b1[..., None] * c[1] + b2[..., None] * c[2])[m]
    return img, zbuf


_VINHETA_PS1 = None


def terror(q: int) -> pygame.Surface:
    global _VINHETA_PS1
    t = q / QUADROS
    w, h = W_PS1, H_PS1
    V, base, emiss, _, n = _arrays(cena_terror(q))
    onda = math.sin(2 * math.pi * t)
    cam = _camera((2.3 + 0.05 * onda, 1.55 + 0.03 * math.sin(4 * math.pi * t), 6.4), (2.6 + 0.7 * onda, 1.15, -4.0))
    focal = (w / 2) / math.tan(math.radians(32))
    sx, sy, zv = _projetar(V, cam, focal, w, h)
    sx, sy = np.round(sx), np.round(sy)  # o vertice gruda no pixel inteiro: o tremor do PS1

    origem = cam[0] + cam[1] * 0.3 - cam[2] * 0.25  # a lanterna, na mao direita
    feixe = _unit(np.array([2.8 + 4.4 * onda, 0.5, -6.5]) - origem)  # varre da esquerda ao vulto
    forca = 0.25 if q in (29, 30, 36) else 1.0  # a pilha falha
    luzes = [("dir", _unit((0.3, 0.8, -0.5)), np.array([0.07, 0.08, 0.13])),
             ("foco", origem, np.array([4.6, 4.3, 3.7]) * forca, 30.0, feixe,
              math.cos(math.radians(23)), math.cos(math.radians(9))),
             ("ponto", np.array([1.1, 1.0, -1.0]), np.array([1.5, 0.3, 0.15]), 2.6)]  # a vela vermelha
    cv = iluminar(V, n, base, emiss, np.array([0.06, 0.065, 0.09]), np.array([0.015, 0.015, 0.018]), luzes)
    vis = (((n * (V[:, 0] - cam[0])).sum(1) < 0) | emiss) & (zv.min(axis=1) > 0.25)
    img, zb = rasterizar(sx[vis], sy[vis], zv[vis], cv[vis], np.broadcast_to(NEVOA_TERROR, (h, w, 3)).copy())

    f = np.clip((zb - 6.0) / 14.0, 0, 1)[..., None]  # a neblina preta engole a distancia
    img = img * (1 - f) + NEVOA_TERROR * f
    img += np.random.default_rng(q).normal(0, 2.5, (h, w, 1))  # grao
    if _VINHETA_PS1 is None:
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.hypot((xx - w / 2) / (w / 2), (yy - h / 2) / (h / 2))
        _VINHETA_PS1 = np.clip(1.15 - 0.55 * r ** 2, 0, 1)[..., None]
    img *= _VINHETA_PS1
    bayer = np.tile(np.array(BAYER) / 16 - 0.5, (h // 4 + 1, w // 4 + 1))[:h, :w, None]
    img = np.floor(np.clip(img + bayer * 10, 0, 255) / 8) * 8  # 15 bits com pontilhado, como o PS1
    surf = pygame.surfarray.make_surface(img.astype(np.uint8).swapaxes(0, 1))
    return pygame.transform.scale(surf, (LARGURA, ALTURA))  # sem suavizar: os pixels grandes
