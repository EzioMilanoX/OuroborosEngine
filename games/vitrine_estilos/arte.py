# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
A arte da vitrine de estilos (ROADMAP fase 8): a MESMA cena -- um espadachim sob a
lua, ao lado de um torii, respirando e dando um corte -- pintada em quatro estilos.

`pose(q)` diz onde cada parte do personagem esta no quadro `q` (unidades de 960x540);
cada estilo so decide COMO pintar essas formas. E o que a fase 8 quer da engine:
o jogo descreve a cena, o estilo e uma escolha de apresentacao.

    celshading  contorno grosso, sombra e brilho em 3 tons, bordas lisas (2x reduzido)
    pixel       160x90 com paleta de 16 cores e pontilhado, ampliado sem suavizar
    sumie       tinta sobre papel: pincel de espessura variavel, aguadas e um selo
    neon        formas chapadas no escuro, contornos de luz e bloom aditivo
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Tuple

import pygame

LARGURA, ALTURA = 960, 540
QUADROS = 12  # 8 respirando + 4 do corte
ESTILOS: Tuple[str, ...] = ("celshading", "pixel", "sumie", "neon")
NOMES: Dict[str, Tuple[str, str]] = {
    "celshading": ("Ilustracao cel-shading", "contorno grosso, sombra em 3 tons, bordas lisas"),
    "pixel": ("Pixel art", "160x90, paleta de 16 cores, pontilhado, ampliado sem suavizar"),
    "sumie": ("Tinta / sumi-e", "pincel com espessura variavel, aguadas no papel, selo vermelho"),
    "neon": ("Flat com luz", "formas chapadas no escuro, contornos de luz e bloom"),
}
HORIZONTE = 400
LUA = (740, 120, 58)


# --------------------------------------------------------------- a cena (geometria)

def pose(q: int) -> Dict[str, object]:
    """As formas do espadachim no quadro `q`, em coordenadas de 960x540."""
    respira = math.sin(q / 8 * 2 * math.pi) * 3 if q < 8 else 0.0
    ataque = (q - 8) / 3 if q >= 8 else -1.0
    px, pe = 330.0, 425.0
    topo = pe - 150 + respira
    ombro = (px + 14, topo + 44)
    if ataque < 0:  # a espada baixa, em guarda
        mao = (px + 46, topo + 92)
        ang = math.radians(-28)
    else:  # o corte: a espada varre de cima para a frente
        a = math.radians(-110 + 150 * min(1.0, ataque))
        mao = (ombro[0] + math.cos(a) * 44, ombro[1] + math.sin(a) * 44)
        ang = a
    ponta = (mao[0] + math.cos(ang) * 92, mao[1] + math.sin(ang) * 92)
    corte = None
    if 0 <= ataque <= 1:
        corte = (ombro[0] + 10, ombro[1] + 6, 120, math.radians(-120), math.radians(-120 + 160 * ataque), ataque)
    return {
        "cabeca": (px + 6, topo + 20, 17),
        "coque": [(px - 8, topo + 2), (px + 2, topo - 12), (px + 10, topo + 2)],
        "tronco": [(px - 26, topo + 38), (px + 30, topo + 38), (px + 36, topo + 100), (px - 30, topo + 100)],
        "obi": [(px - 30, topo + 92), (px + 36, topo + 92), (px + 36, topo + 104), (px - 30, topo + 104)],
        "hakama": [(px - 30, topo + 102), (px + 36, topo + 102), (px + 52, pe), (px + 8, pe), (px + 4, topo + 124),
                   (px - 2, pe), (px - 44, pe)],
        "braco": (ombro, mao),
        "espada": (mao, ponta),
        "corte": corte,
        "pes": (px, pe),
    }


def _torii(escala: float = 1.0) -> Dict[str, List[Tuple[float, float]]]:
    x0, x1, base, alto = 600, 830, HORIZONTE + 8, 200
    return {
        "pilar_e": [(x0 + 22, base - alto + 30), (x0 + 40, base - alto + 30), (x0 + 44, base), (x0 + 18, base)],
        "pilar_d": [(x1 - 40, base - alto + 30), (x1 - 22, base - alto + 30), (x1 - 18, base), (x1 - 44, base)],
        "kasagi": [(x0 - 20, base - alto), (x1 + 20, base - alto), (x1 + 6, base - alto + 20), (x0 - 6, base - alto + 20)],
        "nuki": [(x0 + 4, base - alto + 52), (x1 - 4, base - alto + 52), (x1 - 4, base - alto + 66), (x0 + 4, base - alto + 66)],
    }


def _montanhas(seed: int, base: float, alto: float, n: int = 9) -> List[Tuple[float, float]]:
    rng = random.Random(seed)
    pts = [(0.0, float(ALTURA)), (0.0, base)]
    for i in range(n + 1):
        x = LARGURA * i / n
        pts.append((x, base - rng.uniform(0.3, 1.0) * alto))
    pts += [(float(LARGURA), base), (float(LARGURA), float(ALTURA))]
    return pts


def _arco(cx, cy, r, a0, a1, n=24):
    return [(cx + math.cos(a0 + (a1 - a0) * i / n) * r, cy + math.sin(a0 + (a1 - a0) * i / n) * r) for i in range(n + 1)]


def _crescente(corte, espessura):
    cx, cy, r, a0, a1, _ = corte
    if a1 - a0 < 0.05:
        return []
    fora = _arco(cx, cy, r, a0, a1)
    dentro = _arco(cx, cy, r - espessura, a1, a0)
    meio = len(dentro) // 2
    dentro = [(x + (cx - x) * 0.0, y) for x, y in dentro]
    dentro[meio] = (dentro[meio][0], dentro[meio][1])
    return fora + dentro


def _degrade(surf, topo, base, y0, y1):
    for y in range(int(y0), int(y1)):
        k = (y - y0) / max(1, y1 - y0)
        pygame.draw.line(surf, [int(a + (b - a) * k) for a, b in zip(topo, base)], (0, y), (surf.get_width(), y))


# ---------------------------------------------------------------- 1. cel-shading

CONTORNO = (22, 16, 28)


def _tons(base):
    sombra = tuple(int(c + (t - c) * 0.45) for c, t in zip(base, (40, 24, 70)))
    brilho = tuple(int(c + (t - c) * 0.4) for c, t in zip(base, (255, 246, 226)))
    return base, sombra, brilho


class _Pintor:
    """Peca a peca: contorno (silhueta carimbada em volta), base, sombra e brilho (a mesma
    mascara deslocada contra a luz). Pinta em `s`x e reduz suavizando no fim."""

    def __init__(self, s: int = 2) -> None:
        self.s = s
        self.tela = pygame.Surface((LARGURA * s, ALTURA * s), pygame.SRCALPHA)

    def parte(self, pts, base, *, contorno=3.0, tamanho=40, circulo=None):
        s = self.s
        tmp = pygame.Surface(self.tela.get_size(), pygame.SRCALPHA)
        if circulo:
            pygame.draw.circle(tmp, (255, 255, 255), (circulo[0] * s, circulo[1] * s), circulo[2] * s)
        else:
            pygame.draw.polygon(tmp, (255, 255, 255), [(x * s, y * s) for x, y in pts])
        m = pygame.mask.from_surface(tmp)
        cor, sombra, brilho = _tons(base)
        sil = m.to_surface(setcolor=(*CONTORNO, 255), unsetcolor=(0, 0, 0, 0))
        for i in range(10):
            a = 2 * math.pi * i / 10
            self.tela.blit(sil, (math.cos(a) * contorno * s, math.sin(a) * contorno * s))
        self.tela.blit(m.to_surface(setcolor=(*cor, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
        for tom, d in ((sombra, tamanho * 0.3), (brilho, -tamanho * 0.1)):
            f = m.copy()
            f.erase(m, (int(-0.6 * d * s), int(-0.8 * d * s)))
            self.tela.blit(f.to_surface(setcolor=(*tom, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))

    def linha(self, a, b, cor, larg):
        s = self.s
        pygame.draw.line(self.tela, cor, (a[0] * s, a[1] * s), (b[0] * s, b[1] * s), int(larg * s))

    def final(self):
        return pygame.transform.smoothscale(self.tela, (LARGURA, ALTURA))


def _cel_fundo() -> pygame.Surface:
    fundo = pygame.Surface((LARGURA, ALTURA))
    _degrade(fundo, (58, 40, 96), (236, 132, 98), 0, HORIZONTE)
    p = _Pintor(2)
    p.parte(None, (246, 232, 200), circulo=LUA, tamanho=60)
    p.parte(_montanhas(3, HORIZONTE, 130), (92, 70, 120), tamanho=60)
    p.parte(_montanhas(8, HORIZONTE + 6, 70, 6), (60, 46, 86), tamanho=50)
    pygame.draw.rect(p.tela, (88, 120, 84), (0, HORIZONTE * 2, LARGURA * 2, (ALTURA - HORIZONTE) * 2))
    pygame.draw.rect(p.tela, (70, 98, 70), (0, (HORIZONTE + 40) * 2, LARGURA * 2, (ALTURA - HORIZONTE) * 2))
    pygame.draw.line(p.tela, CONTORNO, (0, HORIZONTE * 2), (LARGURA * 2, HORIZONTE * 2), 6)
    for nome, pts in _torii().items():
        p.parte(pts, (206, 52, 44) if nome != "nuki" else (180, 40, 36), tamanho=24)
    fundo.blit(p.final(), (0, 0))
    return fundo


def _cel(q: int, fundo: pygame.Surface) -> pygame.Surface:
    f = pose(q)
    p = _Pintor(2)
    ombro, mao = f["braco"]
    p.parte(f["hakama"], (54, 58, 92), tamanho=40)
    p.parte(f["tronco"], (220, 214, 200), tamanho=40)
    p.parte(f["obi"], (150, 40, 50), tamanho=10)
    p.linha(f["espada"][0], f["espada"][1], CONTORNO, 9)
    p.linha(f["espada"][0], f["espada"][1], (220, 228, 236), 4)
    dx, dy = mao[0] - ombro[0], mao[1] - ombro[1]
    n = math.hypot(dx, dy) or 1
    nx, ny = -dy / n * 7, dx / n * 7
    p.parte([(ombro[0] + nx, ombro[1] + ny), (mao[0] + nx, mao[1] + ny), (mao[0] - nx, mao[1] - ny), (ombro[0] - nx, ombro[1] - ny)],
            (220, 214, 200), contorno=2.5, tamanho=14)
    p.parte(None, (238, 200, 170), circulo=(mao[0], mao[1], 7), contorno=2.0, tamanho=8)
    cx, cy, r = f["cabeca"]
    p.parte(None, (238, 200, 170), circulo=(cx, cy, r), tamanho=24)
    p.parte([(cx - r, cy - 2), (cx - r + 2, cy - r + 2), (cx + r - 2, cy - r), (cx + r, cy - 4), (cx, cy - 8)], (34, 30, 40), contorno=2.5, tamanho=16)
    p.parte(f["coque"], (34, 30, 40), contorno=2.5, tamanho=10)
    p.linha((cx + 8, cy + 1), (cx + 12, cy + 1), CONTORNO, 2.4)
    if f["corte"]:
        pts = _crescente(f["corte"], 22 * (1 - f["corte"][5] * 0.5))
        if len(pts) > 3:
            p.parte(pts, (236, 248, 255), contorno=3, tamanho=12)
    img = fundo.copy()
    img.blit(p.final(), (0, 0))
    return img


# ---------------------------------------------------------------- 2. pixel art

PALETA = [(20, 16, 36), (44, 30, 70), (82, 52, 110), (140, 80, 130), (214, 120, 110), (246, 186, 132),
          (250, 236, 196), (60, 96, 74), (36, 62, 52), (166, 42, 48), (220, 72, 58), (30, 34, 62),
          (64, 70, 120), (232, 220, 206), (212, 176, 150), (180, 210, 230)]
BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]


def _pixel(q: int) -> pygame.Surface:
    w, h, k = 160, 90, 6
    s = pygame.Surface((w, h))
    faixas = [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]
    hz = HORIZONTE // k
    for y in range(hz):  # o ceu em faixas, com pontilhado ordenado entre elas
        t = y / hz * (len(faixas))
        i = min(len(faixas) - 1, int(t))
        frac = t - i
        for x in range(w):
            c = faixas[i][1] if frac * 16 > BAYER[y % 4][x % 4] else faixas[i][0]
            s.set_at((x, y), PALETA[c])
    lx, ly, lr = LUA[0] // k, LUA[1] // k, LUA[2] // k
    pygame.draw.circle(s, PALETA[6], (lx, ly), lr)
    pygame.draw.circle(s, PALETA[5], (lx + 3, ly + 3), lr - 3)
    pygame.draw.circle(s, PALETA[6], (lx - 1, ly - 1), lr - 4)
    for seed, alto, cor in ((3, 130, 2), (8, 70, 1)):
        pygame.draw.polygon(s, PALETA[cor], [(x / k, y / k) for x, y in _montanhas(seed, HORIZONTE, alto)])
    pygame.draw.rect(s, PALETA[7], (0, hz, w, h - hz))
    for x in range(0, w, 2):  # o capim pontilhado
        if (x * 7) % 5 == 0:
            s.set_at((x, hz), PALETA[8])
    pygame.draw.rect(s, PALETA[8], (0, hz + 6, w, h - hz - 6))
    for nome, pts in _torii().items():
        pygame.draw.polygon(s, PALETA[10 if nome != "nuki" else 9], [(x / k, y / k) for x, y in pts])
        pygame.draw.polygon(s, PALETA[9], [(x / k, y / k) for x, y in pts], 1)
    f = pose(q)

    def pp(pts):
        return [(round(x / k), round(y / k)) for x, y in pts]

    pygame.draw.polygon(s, PALETA[12], pp(f["hakama"]))
    pygame.draw.polygon(s, PALETA[11], pp(f["hakama"]), 1)
    pygame.draw.polygon(s, PALETA[13], pp(f["tronco"]))
    pygame.draw.polygon(s, PALETA[14], pp(f["tronco"]), 1)
    pygame.draw.polygon(s, PALETA[9], pp(f["obi"]))
    a, b = pp(f["espada"])
    pygame.draw.line(s, PALETA[15], a, b)
    a, b = pp(f["braco"])
    pygame.draw.line(s, PALETA[13], a, b, 2)
    cx, cy, r = f["cabeca"]
    pygame.draw.circle(s, PALETA[14], (round(cx / k), round(cy / k)), round(r / k))
    pygame.draw.rect(s, PALETA[0], (round(cx / k) - 3, round(cy / k) - 3, 6, 2))
    s.set_at((round(cx / k) + 1, round(cy / k)), PALETA[0])
    if f["corte"]:
        cx, cy, r, a0, a1, _ = f["corte"]
        for x, y in _arco(cx, cy, r, a0, a1, 30):
            s.set_at((round(x / k), round(y / k)), PALETA[6])
            s.set_at((round(x / k) - 1, round(y / k) + 1), PALETA[15])
    return pygame.transform.scale(s, (LARGURA, ALTURA))  # vizinho mais proximo: pixels nitidos


# ---------------------------------------------------------------- 3. sumi-e

TINTA = (24, 20, 26)


def _pincel(alvo, pts, larg, rng, alfa=230, seco=0.25):
    """Um traco de pincel: carimbos de largura variavel (pressao que sobe e cai) numa
    camada propria, aplicada com uma transparencia so (a tinta nao sai em bolinhas); no fim
    do traco o pincel seca e as cerdas aparecem em riscos finos com falhas."""
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    m = larg + 4
    ox, oy = int(min(xs) - m), int(min(ys) - m)
    camada = pygame.Surface((int(max(xs) - ox + m) + 1, int(max(ys) - oy + m) + 1), pygame.SRCALPHA)
    total = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) or 1
    feito = 0.0
    cerdas = [rng.uniform(-0.45, 0.45) for _ in range(5)]
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        seg = math.dist(pts[i], pts[i + 1])
        nx, ny = (-(y1 - y0) / (seg or 1), (x1 - x0) / (seg or 1))
        passos = max(1, int(seg / 1.2))
        for j in range(passos):
            k = (feito + seg * j / passos) / total
            pressao = math.sin(math.pi * min(1.0, 0.12 + k * 0.95)) ** 0.5
            x = x0 + (x1 - x0) * j / passos - ox
            y = y0 + (y1 - y0) * j / passos - oy
            r = max(0.8, larg * pressao * 0.5)
            if k < 1 - seco:
                pygame.draw.circle(camada, (*TINTA, 255), (x, y), r)
            else:  # pincel seco: so as cerdas, com falhas
                for c in cerdas:
                    if rng.random() < 0.8 - (k - (1 - seco)) / seco * 0.5:
                        pygame.draw.circle(camada, (*TINTA, 255), (x + nx * c * r * 2, y + ny * c * r * 2),
                                           max(0.7, r * 0.18))
        feito += seg
    camada.fill((255, 255, 255, alfa), special_flags=pygame.BLEND_RGBA_MULT)
    alvo.blit(camada, (ox, oy))


def _aguada(alvo, pts, alfa, rng):
    camada = pygame.Surface(alvo.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(camada, (*TINTA, alfa), pts)
    pequena = pygame.transform.smoothscale(camada, (LARGURA // 6, ALTURA // 6))  # borda molhada
    alvo.blit(pygame.transform.smoothscale(pequena, alvo.get_size()), (0, 0))


def _sumie_fundo() -> pygame.Surface:
    rng = random.Random(5)
    papel = pygame.Surface((LARGURA, ALTURA))
    papel.fill((238, 228, 204))
    for _ in range(900):  # as fibras do papel
        x, y = rng.uniform(0, LARGURA), rng.uniform(0, ALTURA)
        a = rng.uniform(0, math.pi)
        c = rng.choice([(226, 214, 188), (244, 236, 216)])
        pygame.draw.line(papel, c, (x, y), (x + math.cos(a) * rng.uniform(3, 12), y + math.sin(a) * rng.uniform(3, 12)))
    tinta = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    pygame.draw.circle(tinta, (*TINTA, 26), LUA[:2], LUA[2] + 6)  # a lua: o papel em branco, cercado de aguada
    pygame.draw.circle(tinta, (0, 0, 0, 0), LUA[:2], LUA[2])
    for seed, alto, alfa in ((3, 130, 60), (8, 70, 110)):  # montanhas em aguada que somem no chao
        pts = _montanhas(seed, HORIZONTE + (6 if seed == 8 else 0), alto, 9 if seed == 3 else 6)
        pts = [(x, min(y, HORIZONTE + 24)) for x, y in pts]
        _aguada(tinta, pts, alfa, rng)
    for nome, pts in _torii().items():  # o torii em quatro pinceladas
        xs = [x for x, _ in pts]
        ys = [y for _, y in pts]
        if nome.startswith("pilar"):
            meio = sum(xs) / 4
            _pincel(tinta, [(meio, min(ys)), (meio + 2, (min(ys) + max(ys)) / 2), (meio + 1, max(ys))], 22, rng)
        else:
            meio = sum(ys) / 4
            _pincel(tinta, [(min(xs), meio + 2), ((min(xs) + max(xs)) / 2, meio - 3), (max(xs), meio + 1)],
                    20 if nome == "kasagi" else 12, rng)
    _pincel(tinta, [(0, HORIZONTE + 18), (300, HORIZONTE + 12), (620, HORIZONTE + 20), (960, HORIZONTE + 14)], 6, rng, 120, 0.5)
    papel.blit(tinta, (0, 0))
    selo = pygame.Rect(866, 446, 58, 58)  # o selo vermelho (hanko)
    pygame.draw.rect(papel, (190, 40, 40), selo)
    for i in range(3):
        pygame.draw.line(papel, (238, 228, 204), (selo.x + 12, selo.y + 14 + i * 14), (selo.right - 12, selo.y + 14 + i * 14), 4)
    pygame.draw.line(papel, (238, 228, 204), (selo.centerx, selo.y + 10), (selo.centerx, selo.bottom - 10), 4)
    return papel


def _sumie(q: int, fundo: pygame.Surface) -> pygame.Surface:
    rng = random.Random(q * 31 + 7)
    f = pose(q)
    tinta = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    hk = f["hakama"]
    _pincel(tinta, [hk[0], hk[6]], 26, rng)
    _pincel(tinta, [hk[1], hk[2]], 26, rng)
    _aguada(tinta, hk, 70, rng)
    tr = f["tronco"]
    _pincel(tinta, [tr[0], (tr[0][0] + 4, tr[0][1] + 30), tr[3]], 16, rng)
    _pincel(tinta, [tr[1], (tr[1][0] - 2, tr[1][1] + 30), tr[2]], 16, rng)
    _pincel(tinta, [f["obi"][0], f["obi"][1]], 12, rng)
    _pincel(tinta, list(f["braco"]), 12, rng)
    _pincel(tinta, list(f["espada"]), 5, rng, 255, 0.1)
    cx, cy, r = f["cabeca"]
    pygame.draw.circle(tinta, (*TINTA, 60), (cx, cy), r)
    _pincel(tinta, _arco(cx, cy, r, math.pi * 0.9, math.pi * 2.3, 10), 7, rng)
    _pincel(tinta, f["coque"], 10, rng)
    if f["corte"]:  # o corte: uma pincelada so, larga, com respingos
        cx, cy, r, a0, a1, _ = f["corte"]
        _pincel(tinta, _arco(cx, cy, r, a0, a1, 16), 26, rng, 200, 0.5)
        for _ in range(10):
            a = rng.uniform(a0, a1)
            d = r + rng.uniform(10, 40)
            pygame.draw.circle(tinta, (*TINTA, 200), (cx + math.cos(a) * d, cy + math.sin(a) * d), rng.uniform(1, 4))
    img = fundo.copy()
    img.blit(tinta, (0, 0))
    return img


# ---------------------------------------------------------------- 4. flat com luz

def _bloom(base: pygame.Surface, luz: pygame.Surface) -> pygame.Surface:
    """Soma a camada de luz nitida e duas versoes borradas dela (o bloom)."""
    out = base.copy()
    for div in (4, 12):
        b = pygame.transform.smoothscale(luz, (LARGURA // div, ALTURA // div))
        out.blit(pygame.transform.smoothscale(b, (LARGURA, ALTURA)), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    out.blit(luz, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return out


def _neon_fundo() -> Tuple[pygame.Surface, pygame.Surface]:
    base = pygame.Surface((LARGURA, ALTURA))
    _degrade(base, (8, 6, 22), (34, 12, 54), 0, HORIZONTE)
    base.fill((10, 8, 24), (0, HORIZONTE, LARGURA, ALTURA - HORIZONTE))
    luz = pygame.Surface((LARGURA, ALTURA))
    pygame.draw.circle(base, (60, 24, 70), LUA[:2], LUA[2])
    pygame.draw.circle(luz, (255, 90, 170), LUA[:2], LUA[2], 3)
    for i in range(6):  # o sol/lua de faixas, como num poster
        y = LUA[1] + 10 + i * 9
        pygame.draw.line(luz, (180, 60, 130), (LUA[0] - 50, y), (LUA[0] + 50, y), 2)
    pygame.draw.polygon(base, (16, 10, 34), _montanhas(3, HORIZONTE, 130))
    pygame.draw.lines(luz, (110, 60, 200), False, _montanhas(3, HORIZONTE, 130)[1:-1], 2)
    for i in range(14):  # o chao em grade, em perspectiva
        x = LARGURA / 2 + (i - 6.5) * 140
        pygame.draw.line(luz, (60, 30, 110), (LARGURA / 2 + (x - LARGURA / 2) * 0.15, HORIZONTE), (x, ALTURA), 1)
    for i in range(7):
        y = HORIZONTE + (ALTURA - HORIZONTE) * (i / 6) ** 1.8
        pygame.draw.line(luz, (60, 30, 110), (0, y), (LARGURA, y), 1)
    for nome, pts in _torii().items():
        pygame.draw.polygon(base, (22, 12, 40), pts)
        pygame.draw.polygon(luz, (255, 70, 90), pts, 3)
    return base, luz


def _neon(q: int, fundo: Tuple[pygame.Surface, pygame.Surface]) -> pygame.Surface:
    base, luz = fundo[0].copy(), fundo[1].copy()
    f = pose(q)
    for nome in ("hakama", "tronco"):
        pygame.draw.polygon(base, (14, 12, 30), f[nome])
        pygame.draw.polygon(luz, (40, 220, 255), f[nome], 2)
    pygame.draw.polygon(luz, (255, 70, 120), f["obi"], 2)
    a, b = f["braco"]
    pygame.draw.line(base, (14, 12, 30), a, b, 12)
    pygame.draw.line(luz, (40, 220, 255), a, b, 2)
    a, b = f["espada"]
    pygame.draw.line(luz, (220, 255, 255), a, b, 3)
    cx, cy, r = f["cabeca"]
    pygame.draw.circle(base, (14, 12, 30), (cx, cy), r)
    pygame.draw.circle(luz, (40, 220, 255), (cx, cy), r, 2)
    pygame.draw.line(luz, (255, 255, 255), (cx + 6, cy), (cx + 13, cy), 2)
    rng = random.Random(1)
    for i in range(30):  # as particulas subindo
        x = rng.uniform(0, LARGURA)
        y = (rng.uniform(0, ALTURA) - q * 6 * rng.uniform(0.5, 1.5)) % ALTURA
        pygame.draw.circle(luz, rng.choice([(40, 180, 230), (200, 60, 160)]), (x, y), 1.5)
    if f["corte"]:
        cx, cy, r, a0, a1, k = f["corte"]
        pts = _arco(cx, cy, r, a0, a1)
        if len(pts) > 1:
            pygame.draw.lines(luz, (180, 250, 255), False, pts, int(10 * (1 - k * 0.6)) + 2)
    return _bloom(base, luz)


# ---------------------------------------------------------------- tudo junto

def gerar(estilo: str) -> List[pygame.Surface]:
    """Os `QUADROS` quadros 960x540 de um estilo."""
    if estilo == "celshading":
        fundo = _cel_fundo()
        return [_cel(q, fundo) for q in range(QUADROS)]
    if estilo == "pixel":
        return [_pixel(q) for q in range(QUADROS)]
    if estilo == "sumie":
        fundo = _sumie_fundo()
        return [_sumie(q, fundo) for q in range(QUADROS)]
    if estilo == "neon":
        fundo = _neon_fundo()
        return [_neon(q, fundo) for q in range(QUADROS)]
    raise ValueError(f"estilo desconhecido: {estilo!r}")
