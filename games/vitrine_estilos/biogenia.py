# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
A segunda cena da vitrine: Biogenia (blueprint GAM-13), o fim do Cretaceo em corte lateral.
Na superficie, um tiranossauro anda; na boca da toca, um mamifero pequeno sai, olha para o
ponto que cresce no ceu e volta para baixo. Embaixo, em corte: o tunel, a camara com o
estoque de sementes e dois que dormem, a agua e o duto de ar.

A cena serve para escolher o TOM do jogo; cada estilo e um tom possivel:

    bio_leve         como o Spore: dia claro, cores vivas, contorno grosso (o cel-shading da
                     cena do espadachim, sem a luz de recorte); o humor tira o peso da extincao
    bio_silhueta     serio, no clima de Inside e Rain World: silhuetas pretas no ceu do
                     impacto, borda acesa pelo horizonte, a toca acesa por dentro, cinza caindo,
                     grao de filme e vinheta
    bio_pixel        serio em pixel art: 160x90, a paleta do crepusculo com pontilhado, uma
                     linha de luz so no topo das silhuetas
    bio_naturalista  o mais perto de paleoarte que da para pintar por codigo: luz e sombra em
                     faixas, listras, cores de terra, contornos suaves e textura de pincel

`trex(t)` e `rato(t)` dizem onde as coisas estao no instante `t` do laco (0..1); cada estilo
so decide como pintar. O laco fecha: `t = 0` e `t = 1` sao a mesma pose.
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Sequence, Tuple

import numpy as np
import pygame

from games.vitrine_estilos.arte import (
    ALTURA,
    BAYER,
    CEU,
    LARGURA,
    QUADROS,
    _borrar,
    _degrade,
    _faixa,
    _Pintor,
    _suave,
)

Pt = Tuple[float, float]
Cor = Tuple[int, int, int]

ESTILOS: Tuple[str, ...] = ("bio_leve", "bio_silhueta", "bio_pixel", "bio_naturalista", "bio_25d", "bio_3d")
NOMES: Dict[str, Tuple[str, str]] = {
    "bio_leve": ("Leve (como o Spore)", "dia claro, cores vivas, contorno grosso; o humor tira o peso"),
    "bio_silhueta": ("Serio: silhueta", "silhuetas no ceu do impacto, toca acesa, cinza caindo, grao"),
    "bio_pixel": ("Serio: pixel art", "160x90, paleta do crepusculo, pontilhado, luz so no topo"),
    "bio_25d": ("2.5D: serio + naturalista", "camera inclinada, recortes pintados, neblina, sombra no chao"),
    "bio_3d": ("3D com recortes", "chao 3D com z-buffer, recortes em pe; a camera gira 90 graus"),
    "bio_naturalista": ("Naturalista", "quase paleoarte: luz e sombra pintadas, terra, pincel"),
}

SOLO = 300  # a linha do chao; abaixo dela, o corte
METEORO: Pt = (800.0, 72.0)
RASTRO: Pt = (-0.86, -0.5)  # de onde ele vem


# --------------------------------------------------------------- a cena (geometria)

def _rot(p: Pt, piv: Pt, a: float) -> Pt:
    x, y = p[0] - piv[0], p[1] - piv[1]
    c, s = math.cos(a), math.sin(a)
    return piv[0] + x * c - y * s, piv[1] + x * s + y * c


def _elipse(cx: float, cy: float, rx: float, ry: float, n: int = 20) -> List[Pt]:
    return [(cx + rx * math.cos(2 * math.pi * i / n), cy + ry * math.sin(2 * math.pi * i / n)) for i in range(n)]


def _folha(base: Pt, ang: float, comp: float, larg: float, cai: float) -> List[Pt]:
    """Uma folha (ou fronde) como losango curvado para baixo na ponta."""
    dx, dy = math.cos(ang), math.sin(ang)
    nx, ny = -dy, dx
    ponta = (base[0] + dx * comp, base[1] + dy * comp + comp * cai)
    meio = (base[0] + dx * comp * 0.5, base[1] + dy * comp * 0.5 + comp * cai * 0.35)
    return [base, (meio[0] + nx * larg / 2, meio[1] + ny * larg / 2), ponta,
            (meio[0] - nx * larg / 2, meio[1] - ny * larg / 2)]


# o tiranossauro, virado para a direita: pontos relativos ao pe (0, 0); y negativo e para cima
TREX_CORPO: List[Pt] = [(-175, -118), (-120, -138), (-60, -158), (0, -170), (55, -165), (88, -176), (98, -198),
                        (160, -201), (181, -185), (178, -168), (132, -165), (121, -156), (100, -148), (92, -128),
                        (80, -112), (40, -98), (-30, -100), (-110, -116)]
TREX_PERNA: List[Pt] = [(-45, -140), (12, -132), (16, -96), (2, -52), (24, -10), (44, 0), (-6, 0), (-26, -46),
                        (-48, -96)]
TREX_BRACO: List[Pt] = [(78, -120), (98, -110), (95, -103), (76, -111)]
QUADRIL: Pt = (-15, -120)


def trex(t: float) -> Dict[str, object]:
    """O tiranossauro andando no lugar: o corpo balanca, as pernas alternam."""
    x0 = 250 + 6 * math.sin(2 * math.pi * t)
    y0 = SOLO + 2 - 3 * abs(math.sin(2 * math.pi * t))
    a = 0.2 * math.sin(2 * math.pi * t)

    def mover(pts: Sequence[Pt], ang: float = 0.0, dx: float = 0.0) -> List[Pt]:
        return [(x0 + x, y0 + y) for x, y in (_rot((px + dx, py), QUADRIL, ang) for px, py in pts)]

    return {"corpo": mover(TREX_CORPO), "perna": mover(TREX_PERNA, a), "perna_tras": mover(TREX_PERNA, -a, 18),
            "braco": mover(TREX_BRACO), "olho": (x0 + 150, y0 - 189), "pe": (x0, y0)}


# a toca, em corte
TUNEL: List[Pt] = [(608, 294), (628, 344), (608, 390), (660, 434), (712, 462)]
TUNEL_AGUA: List[Pt] = [(608, 390), (572, 442)]
DUTO: List[Pt] = [(778, 446), (792, 400), (784, 350), (796, 300)]
CAMARA = (728.0, 468.0, 78.0, 34.0)  # cx, cy, rx, ry
AGUA = (560.0, 452.0, 34.0, 15.0)
DORMINDO: List[Pt] = [(684, 482), (716, 486)]
CAMINHO_RATO: List[Pt] = [(612, 392), (628, 346), (606, 306), (622, 290)]  # do fundo do tunel ate a superficie


def _sementes() -> List[Tuple[float, float, float]]:
    rng = random.Random(7)
    cx, cy, rx, ry = CAMARA
    saida = []
    for _ in range(26):
        x = rng.uniform(744, 796)
        fundo = cy + ry * math.sqrt(max(0.0, 1 - ((x - cx) / rx) ** 2))
        saida.append((x, fundo - 5 - rng.uniform(0, 7), rng.choice((2.5, 3.0, 3.5))))
    return saida


SEMENTES = _sementes()


def _plantas() -> Tuple[List[List[Pt]], List[List[Pt]]]:
    """Troncos e folhas: uma cicadacea, uma samambaia arborea e tres samambaias baixas."""
    troncos = [[(465, SOLO), (475, SOLO), (474, 262), (466, 262)], [(896, SOLO), (905, SOLO), (903, 178), (897, 178)]]
    folhas = [_folha((470, 262), math.radians(-160 + i * 140 / 6), 46, 11, 0.25) for i in range(7)]
    folhas += [_folha((900, 178), math.radians(-172 + i * 164 / 7), 72, 13, 0.35) for i in range(8)]
    for bx in (95, 380, 540):
        folhas += [_folha((bx, SOLO), math.radians(-165 + i * 30), 34 + (i % 2) * 8, 8, 0.15) for i in range(6)]
    return troncos, folhas


PLANTAS = _plantas()
MORROS: List[Pt] = ([(x, 250 - 22 * math.sin(x / 95) - 12 * math.sin(x / 41 + 1.3)) for x in range(0, 961, 16)]
                    + [(960, SOLO), (0, SOLO)])
VULCAO: List[Pt] = [(470, SOLO), (590, 200), (612, 192), (636, 196), (650, 192), (760, SOLO)]
FUMACA = [(624 + 16 * i + 10 * math.sin(i * 1.7), 182 - 18 * i, 11 + 3.5 * i + 3 * math.sin(i * 2.3)) for i in range(7)]


def _ao_longo(pts: Sequence[Pt], u: float) -> Pt:
    segs = [math.dist(a, b) for a, b in zip(pts, pts[1:])]
    alvo = u * sum(segs)
    for (a, b), d in zip(zip(pts, pts[1:]), segs):
        if alvo <= d:
            k = alvo / d if d else 0.0
            return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
        alvo -= d
    return pts[-1]


def _subida(t: float) -> float:
    """Quanto o mamifero subiu (0: no fundo do tunel; 1: na superficie)."""
    if t < 0.2:
        return _suave(t / 0.2)
    if t < 0.6:
        return 1.0
    if t < 0.8:
        return 1.0 - _suave((t - 0.6) / 0.2)
    return 0.0


def rato(t: float) -> Dict[str, object]:
    """O mamifero: sobe pelo tunel, olha para o ceu, desce de volta e fica la embaixo."""
    u = _subida(t)
    x, y = _ao_longo(CAMINHO_RATO, u)
    olhando = 0.25 < t < 0.6
    return {"corpo": (x, y), "cabeca": (x + 13, y - (9 if olhando else 4)), "fora": u > 0.85}


def meteoro(t: float) -> Tuple[Pt, float]:
    """O ponto no ceu e o quanto ele pulsa agora (0..1)."""
    return METEORO, 0.5 + 0.5 * math.sin(4 * math.pi * t)


# --------------------------------------------------------------- pecas comuns

def _linha_grossa(s: pygame.Surface, pts: Sequence[Pt], cor: Cor, larg: int) -> None:
    pygame.draw.lines(s, cor, False, pts, larg)
    for p in pts:
        pygame.draw.circle(s, cor, (int(p[0]), int(p[1])), larg // 2)


def _toca(s: pygame.Surface, tunel: Cor, camara: Cor, agua: Cor) -> None:
    _linha_grossa(s, DUTO, tunel, 5)
    _linha_grossa(s, TUNEL, tunel, 22)
    _linha_grossa(s, TUNEL_AGUA, tunel, 16)
    cx, cy, rx, ry = CAMARA
    pygame.draw.ellipse(s, camara, (cx - rx, cy - ry, 2 * rx, 2 * ry))
    ax, ay, arx, ary = AGUA
    pygame.draw.ellipse(s, tunel, (ax - arx - 4, ay - ary - 4, 2 * arx + 8, 2 * ary + 8))
    pygame.draw.ellipse(s, agua, (ax - arx, ay - ary + 6, 2 * arx, 2 * ary - 6))


def _dormindo(s: pygame.Surface, cor: Cor, borda: Cor = None) -> None:
    for x, y in DORMINDO:
        for c, g in (((borda, 2),) if borda else ()) + ((cor, 0),):
            pygame.draw.ellipse(s, c, (x - 14 - g, y - 7 - g, 28 + 2 * g, 14 + 2 * g))
            pygame.draw.circle(s, c, (int(x + 12), int(y - 2)), 6 + g)


def _estratos(s: pygame.Surface, cores: Sequence[Cor], so_linha: bool = False) -> None:
    for k, y in enumerate(range(SOLO + 44, ALTURA, 48)):
        pts = [(x, y + 6 * math.sin(x / 70 + k)) for x in range(0, 961, 24)]
        if so_linha:
            pygame.draw.lines(s, cores[k % len(cores)], False, pts, 2)
        else:
            pygame.draw.polygon(s, cores[k % len(cores)], pts + [(960, y + 24), (0, y + 24)])


def _brilho(s: pygame.Surface, centro: Pt, raio: int, cor: Cor, n: int = 16) -> None:
    """Um halo somado a cena: mais forte no centro."""
    camada = pygame.Surface((raio * 2, raio * 2))
    for i in range(n):
        k = (i + 1) / n
        pygame.draw.circle(camada, tuple(int(c * k * k) for c in cor), (raio, raio), max(1, int(raio * (1 - i / n))))
    s.blit(camada, (int(centro[0]) - raio, int(centro[1]) - raio), special_flags=pygame.BLEND_RGB_ADD)


def _fumaca(s: pygame.Surface, cor: Tuple[int, int, int, int], borrar: int) -> None:
    """A fumaca do vulcao: bolas que se afinam e se apagam subindo, borradas."""
    camada = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for i, (cx, cy, r) in enumerate(FUMACA):
        a = int(cor[3] * (1 - i / (len(FUMACA) + 1)))
        pygame.draw.circle(camada, (*cor[:3], a), (int(cx), int(cy)), int(r))
    s.blit(_borrar(camada, borrar), (0, 0))


def _silhueta_trex(tr: Dict[str, object], cor: Tuple[int, int, int, int], tam: Tuple[int, int] = (LARGURA, ALTURA),
                   k: float = 1.0) -> pygame.Surface:
    camada = pygame.Surface(tam, pygame.SRCALPHA)
    for parte in ("perna_tras", "corpo", "perna", "braco"):
        pts = [(x / k, y / k) for x, y in tr[parte]]
        pygame.draw.polygon(camada, cor, pts)
        if k == 1.0:
            pygame.draw.aalines(camada, cor, True, pts)
    return camada


def _rato_simples(s: pygame.Surface, rt: Dict[str, object], cor: Cor) -> None:
    x, y = rt["corpo"]
    hx, hy = rt["cabeca"]
    pygame.draw.line(s, cor, (x - 14, y + 2), (x - 28, y + 6), 2)
    pygame.draw.ellipse(s, cor, (x - 16, y - 8, 32, 16))
    pygame.draw.circle(s, cor, (int(hx - 3), int(hy - 7)), 4)
    pygame.draw.circle(s, cor, (int(hx), int(hy)), 8)


def _no_tunel(rt: Dict[str, object]) -> bool:
    return rt["corpo"][1] > SOLO + 6


# ---------------------------------------------------------------- 1. leve (como o Spore)

REGIAO_TREX = (50, 86, 420, 236)
REGIAO_RATO = (560, 262, 110, 150)


def _leve_fundo() -> pygame.Surface:
    s = pygame.Surface((LARGURA, ALTURA))
    _degrade(s, (112, 196, 240), (214, 240, 250), 0, SOLO)
    for cx, cy, r in ((150, 70, 26), (190, 62, 32), (230, 72, 24)):  # uma nuvem
        pygame.draw.circle(s, (250, 252, 255), (cx, cy), r)
    pygame.draw.polygon(s, (150, 204, 172), MORROS)
    pygame.draw.polygon(s, (176, 128, 96), VULCAO)
    pygame.draw.lines(s, (120, 84, 64), False, VULCAO[:-1], 4)
    for cx, cy, r in FUMACA:
        pygame.draw.circle(s, (236, 236, 240), (int(cx), int(cy)), int(r))
    s.fill((182, 126, 78), (0, SOLO, LARGURA, ALTURA - SOLO))
    _estratos(s, ((164, 110, 66), (196, 140, 90)))
    pygame.draw.rect(s, (106, 188, 80), (0, SOLO - 6, LARGURA, 14))
    pygame.draw.line(s, (70, 140, 56), (0, SOLO + 8), (LARGURA, SOLO + 8), 3)
    _toca(s, (98, 62, 42), (138, 94, 62), (86, 164, 226))
    for x, y, r in SEMENTES:
        pygame.draw.circle(s, (120, 80, 30), (int(x), int(y)), int(r + 1))
        pygame.draw.circle(s, (244, 186, 66), (int(x), int(y)), int(r))
    _dormindo(s, (214, 146, 92), (90, 54, 36))
    p = _Pintor(2)
    troncos, folhas = PLANTAS
    for tronco in troncos:
        p.parte(tronco, (134, 98, 64), contorno=1.0, tamanho=8, recorte=False)
    for folha in folhas:
        p.parte(folha, (84, 178, 74), contorno=1.0, tamanho=10, recorte=False)
    p.silhueta(1.6)
    s.blit(p.final(), (0, 0))
    return s


def _pintar_rato(p: _Pintor, rt: Dict[str, object], cor: Cor, olho: Cor) -> None:
    x, y = rt["corpo"]
    hx, hy = rt["cabeca"]
    p.linha((x - 14, y + 2), (x - 28, y + 6), (90, 54, 36), 2.5)
    p.parte(_elipse(x, y, 16, 8), cor, tamanho=10, recorte=False)
    p.parte(None, cor, circulo=(hx - 3, hy - 7, 3.5), tamanho=4, recorte=False)
    p.parte(None, cor, circulo=(hx, hy, 8), tamanho=8, recorte=False)
    p.parte(None, olho, circulo=(hx + 3, hy - 1, 2), contorno=0, tamanho=2, recorte=False)


def _leve(q: int, fundo: pygame.Surface) -> pygame.Surface:
    t = q / QUADROS
    img = fundo.copy()
    (mx, my), p = meteoro(t)
    dx, dy = RASTRO
    for k, cor in enumerate(((255, 150, 60), (255, 206, 90), (255, 244, 200))):  # a bola de fogo de desenho
        larg = (16 - 5 * k) * (0.85 + 0.3 * p)
        comp = 110 - 30 * k
        nx, ny = -dy, dx
        pygame.draw.polygon(img, cor, [(mx + nx * larg, my + ny * larg), (mx + dx * comp, my + dy * comp),
                                       (mx - nx * larg, my - ny * larg)])
        pygame.draw.circle(img, cor, (int(mx), int(my)), int(larg))
    tr = trex(t)
    pt = _Pintor(2, REGIAO_TREX)
    pt.parte(tr["perna_tras"], (78, 146, 66), tamanho=30, recorte=False)
    pt.parte(tr["corpo"], (112, 186, 92), tamanho=80, recorte=False)
    pt.parte(tr["perna"], (112, 186, 92), tamanho=30, recorte=False)
    pt.parte(tr["braco"], (112, 186, 92), tamanho=8, recorte=False)
    ox, oy = tr["olho"]
    pt.parte(None, (255, 255, 255), circulo=(ox, oy, 7), tamanho=6, recorte=False)
    pt.parte(None, (24, 20, 26), circulo=(ox + 2, oy + 1, 3), contorno=0, tamanho=3, recorte=False)
    pt.silhueta(2.4)
    img.blit(pt.final(), REGIAO_TREX[:2])
    pr = _Pintor(2, REGIAO_RATO)
    _pintar_rato(pr, rato(t), (214, 146, 92), (24, 20, 26))
    pr.silhueta(1.6)
    img.blit(pr.final(), REGIAO_RATO[:2])
    return img


# ---------------------------------------------------------------- 2. serio: silhueta

PRETO = (12, 8, 12)


def _sil_fundo() -> pygame.Surface:
    s = pygame.Surface((LARGURA, ALTURA))
    _degrade(s, (16, 8, 26), (92, 24, 36), 0, 180)
    _degrade(s, (92, 24, 36), (232, 108, 50), 180, SOLO)
    pygame.draw.polygon(s, (70, 24, 30), MORROS)
    pygame.draw.polygon(s, (36, 12, 18), VULCAO)
    _brilho(s, (620, 196), 40, (170, 44, 20))
    _fumaca(s, (40, 16, 24, 150), 5)
    s.fill((30, 20, 22), (0, SOLO, LARGURA, ALTURA - SOLO))
    _estratos(s, ((40, 27, 29),), so_linha=True)
    _toca(s, (8, 5, 8), (54, 30, 16), (14, 20, 34))
    luz = pygame.Surface((LARGURA, ALTURA))  # a camara acesa por dentro: o unico lugar quente
    cx, cy, rx, ry = CAMARA
    for i in range(24):
        k = 1 - i / 24
        cor = (int(20 + 210 * (1 - k)), int(8 + 120 * (1 - k) ** 1.3), int(40 * (1 - k) ** 2))
        pygame.draw.ellipse(luz, cor, (cx - rx * k, cy + 10 - ry * k * 1.4, 2 * rx * k, 2 * ry * k * 1.4))
    so_camara = pygame.Surface((LARGURA, ALTURA))
    pygame.draw.ellipse(so_camara, (255, 255, 255), (cx - rx, cy - ry, 2 * rx, 2 * ry))
    luz.blit(so_camara, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    s.blit(luz, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    for x, y, r in SEMENTES:
        pygame.draw.circle(s, (110, 64, 26), (int(x), int(y)), int(r))
    _dormindo(s, (30, 16, 10))
    pygame.draw.rect(s, PRETO, (0, SOLO - 4, LARGURA, 9))
    _linha_grossa(s, TUNEL[:2], (8, 5, 8), 22)
    dobro = pygame.Surface((LARGURA * 2, ALTURA * 2), pygame.SRCALPHA)  # plantas em 2x, reduzidas: borda suave
    troncos, folhas = PLANTAS
    for pts in troncos + folhas:
        pygame.draw.polygon(dobro, (*PRETO, 255), [(x * 2, y * 2) for x, y in pts])
    s.blit(pygame.transform.smoothscale(dobro, (LARGURA, ALTURA)), (0, 0))
    return s


def _vinheta(forca: float = 0.55) -> pygame.Surface:
    xs = (np.arange(LARGURA) - LARGURA / 2) / (LARGURA / 2)
    ys = (np.arange(ALTURA) - ALTURA / 2) / (ALTURA / 2)
    d = xs[:, None] ** 2 * 0.8 + ys[None, :] ** 2
    v = (np.clip(1 - forca * d * 0.7, 0, 1) * 255).astype(np.uint8)
    return pygame.surfarray.make_surface(np.repeat(v[..., None], 3, axis=2))


def _cinzas() -> List[Tuple[float, float, float, float, float]]:
    rng = random.Random(11)
    return [(rng.uniform(0, LARGURA), rng.uniform(0, ALTURA), rng.uniform(4, 14), rng.uniform(0, 6.3),
             rng.choice((1.0, 1.5, 2.0))) for _ in range(70)]


_RUIDOS: Dict[int, List[np.ndarray]] = {}


def _grao(img: pygame.Surface, q: int, forca: int = 10) -> None:
    """Grao de filme: quatro ruidos sorteados uma vez e revezados (sortear um por quadro custa caro)."""
    if forca not in _RUIDOS:
        rng = np.random.default_rng(forca)
        _RUIDOS[forca] = [rng.integers(-forca, forca + 1, size=(LARGURA, ALTURA, 1), dtype=np.int16) for _ in range(4)]
    arr = pygame.surfarray.pixels3d(img)
    ruido = _RUIDOS[forca][q % 4]
    arr[...] = np.clip(arr.astype(np.int16) + ruido, 0, 255).astype(np.uint8)
    del arr


def _sil(q: int, fundo: pygame.Surface, vinheta: pygame.Surface, cinzas) -> pygame.Surface:
    t = q / QUADROS
    img = fundo.copy()
    (mx, my), p = meteoro(t)
    _brilho(img, (mx, my), int(70 + 20 * p), (120, 60, 30))
    dx, dy = RASTRO
    for k in range(12):
        f = 1 - k / 12
        pygame.draw.line(img, (int(255 * f), int(200 * f), int(140 * f)), (mx + dx * k * 10, my + dy * k * 10),
                         (mx + dx * (k + 1) * 10, my + dy * (k + 1) * 10), max(1, int(5 * f)))
    _brilho(img, (mx, my), 14, (255, 230, 190))
    tr = trex(t)
    camada = _silhueta_trex(tr, (*PRETO, 255))
    borda = _faixa(pygame.mask.from_surface(camada), (1.5, -2.5))  # a borda que o horizonte acende
    img.blit(camada, (0, 0))
    img.blit(borda.to_surface(setcolor=(170, 70, 44, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
    ox, oy = tr["olho"]
    pygame.draw.circle(img, (220, 120, 60), (int(ox), int(oy)), 2)
    rt = rato(t)
    _rato_simples(img, rt, (44, 24, 14) if _no_tunel(rt) else PRETO)
    if not _no_tunel(rt):
        hx, hy = rt["cabeca"]
        pygame.draw.circle(img, (230, 140, 70), (int(hx + 3), int(hy - 1)), 1)
    for x0, y0, amp, fase, r in cinzas:  # a cinza caindo (uma volta inteira por laco: fecha sem salto)
        y = (y0 + t * ALTURA) % ALTURA
        if y < SOLO - 4:
            x = x0 + amp * math.sin(2 * math.pi * t + fase)
            pygame.draw.circle(img, (255, 150, 70) if r > 1.5 else (150, 110, 100), (int(x), int(y)), int(r))
    img.blit(vinheta, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    _grao(img, q)
    return img


# ---------------------------------------------------------------- 3. serio: pixel art

K = 6
PW, PH = LARGURA // K, ALTURA // K  # 160x90


def _p(pts: Sequence[Pt]) -> List[Pt]:
    return [(x / K, y / K) for x, y in pts]


def _pixel_fundo() -> pygame.Surface:
    s = pygame.Surface((PW, PH))
    topo = SOLO // K
    for y in range(topo):  # o ceu do crepusculo em faixas, com pontilhado ordenado entre elas
        v = y / topo * (len(CEU) - 1)
        i, f = int(v), v - int(v)
        for x in range(PW):
            s.set_at((x, y), CEU[min(i + 1, len(CEU) - 1)] if f * 16 > BAYER[y % 4][x % 4] else CEU[i])
    pygame.draw.polygon(s, (66, 30, 56), _p(MORROS))
    pygame.draw.polygon(s, (42, 18, 38), _p(VULCAO))
    for cx, cy, r in FUMACA:
        pygame.draw.circle(s, (54, 26, 48), (round(cx / K), round(cy / K)), max(1, round(r / K) - 1))
    s.set_at((round(620 / K), round(194 / K)), (226, 120, 104))
    s.fill((46, 26, 36), (0, topo, PW, PH - topo))
    for k, y in enumerate(range(topo + 7, PH, 8)):
        for x in range(PW):
            if (x + k * 3) % 4:
                s.set_at((x, y), (56, 32, 42))
    pygame.draw.rect(s, (22, 12, 24), (0, topo - 1, PW, 2))
    for pts, larg in ((DUTO, 1), (TUNEL, 4), (TUNEL_AGUA, 3)):
        pygame.draw.lines(s, (14, 8, 16), False, _p(pts), larg)
    cx, cy, rx, ry = (v / K for v in CAMARA)
    pygame.draw.ellipse(s, (92, 50, 30), (cx - rx, cy - ry, 2 * rx, 2 * ry))
    pygame.draw.ellipse(s, (150, 84, 40), (cx - rx * 0.6, cy - ry * 0.3, 1.2 * rx, 1.1 * ry))
    ax, ay, arx, ary = (v / K for v in AGUA)
    pygame.draw.ellipse(s, (30, 40, 72), (ax - arx, ay - ary, 2 * arx, 2 * ary))
    for x, y, _ in SEMENTES[::2]:
        s.set_at((round(x / K), round(y / K)), (232, 172, 80))
    for x, y in DORMINDO:
        s.fill((40, 22, 16), (round(x / K) - 2, round(y / K) - 1, 5, 2))
    troncos, folhas = PLANTAS
    for pts in troncos + folhas:
        pygame.draw.polygon(s, (22, 12, 24), _p(pts))
    return s


def _pixel(q: int, fundo: pygame.Surface) -> pygame.Surface:
    t = q / QUADROS
    s = fundo.copy()
    (mx, my), p = meteoro(t)
    cx, cy = round(mx / K), round(my / K)
    for k in range(1, 12):
        cor = (250, 184, 128) if k < 5 else (158, 76, 120) if k < 9 else (92, 48, 110)
        s.set_at((round(cx + RASTRO[0] * k * 1.6), round(cy + RASTRO[1] * k * 1.6)), cor)
    s.fill((255, 244, 220), (cx - 1, cy - 1, 2, 2))
    if p > 0.5:
        for d in ((-2, 0), (1, 0), (0, -2), (0, 1), (1, 1), (-2, -2)):
            s.set_at((cx + d[0], cy + d[1]), (250, 184, 128))
    tr = trex(t)
    camada = _silhueta_trex(tr, (22, 12, 24, 255), (PW, PH), K)
    borda = _faixa(pygame.mask.from_surface(camada), (0, -1))  # 1 pixel de luz so no topo
    s.blit(camada, (0, 0))
    s.blit(borda.to_surface(setcolor=(120, 52, 72, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
    ox, oy = tr["olho"]
    s.set_at((round(ox / K), round(oy / K)), (226, 120, 104))
    rt = rato(t)
    x, y = rt["corpo"]
    hx, hy = rt["cabeca"]
    cor = (60, 34, 24) if _no_tunel(rt) else (22, 12, 24)
    s.fill(cor, (round(x / K) - 2, round(y / K) - 1, 4, 2))
    s.set_at((round(hx / K), round(hy / K)), cor)
    return pygame.transform.scale(s, (LARGURA, ALTURA))


# ---------------------------------------------------------------- 4. naturalista

def _textura_pincel() -> pygame.Surface:
    """Manchas largas e grao fino, para multiplicar por cima de tudo (a tela pintada)."""
    rng = np.random.default_rng(5)
    largo = np.clip(238 + 12 * rng.normal(0, 1, (LARGURA // 3, ALTURA // 3)), 200, 255).astype(np.uint8)
    peq = pygame.surfarray.make_surface(np.repeat(largo[..., None], 3, axis=2))
    grande = pygame.transform.smoothscale(peq, (LARGURA, ALTURA))
    arr = pygame.surfarray.pixels3d(grande)
    fino = np.clip(250 + 5 * rng.normal(0, 1, (LARGURA, ALTURA)), 0, 255)[..., None] / 255
    arr[...] = (arr * fino).astype(np.uint8)
    del arr
    return grande


def _sombreado(camada: pygame.Surface, luz: Cor, sombra: Cor, d_luz: Pt = (-3, -7), d_sombra: Pt = (2, 10)) -> None:
    """Faixa de sombra embaixo e de luz em cima, so dentro da silhueta."""
    m = pygame.mask.from_surface(camada)
    camada.blit(_faixa(m, d_sombra).to_surface(setcolor=(*sombra, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
    camada.blit(_faixa(m, d_luz).to_surface(setcolor=(*luz, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))


def _nat_fundo() -> pygame.Surface:
    s = pygame.Surface((LARGURA, ALTURA))
    _degrade(s, (58, 78, 108), (146, 138, 140), 0, 190)
    _degrade(s, (146, 138, 140), (214, 164, 124), 190, SOLO)
    pygame.draw.polygon(s, (124, 120, 134), MORROS)
    pygame.draw.polygon(s, (96, 78, 76), VULCAO)
    _fumaca(s, (104, 96, 100, 170), 6)
    _degrade(s, (112, 88, 62), (62, 46, 36), SOLO, ALTURA)
    _estratos(s, ((92, 72, 54), (80, 62, 48)), so_linha=True)
    pygame.draw.rect(s, (78, 92, 52), (0, SOLO - 5, LARGURA, 9))
    _toca(s, (42, 32, 26), (60, 46, 36), (48, 66, 82))
    _brilho(s, (728, 470), 70, (40, 26, 12))
    for x, y, r in SEMENTES:
        pygame.draw.circle(s, (168, 138, 84), (int(x), int(y)), int(r))
    _dormindo(s, (118, 88, 62))
    _linha_grossa(s, TUNEL[:2], (42, 32, 26), 22)
    plantas = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    troncos, folhas = PLANTAS
    for pts in troncos:
        pygame.draw.polygon(plantas, (84, 66, 48, 255), pts)
    for pts in folhas:
        pygame.draw.polygon(plantas, (56, 74, 42, 255), pts)
    _sombreado(plantas, (104, 124, 70), (40, 54, 32), (-1, -3), (1, 3))
    s.blit(_borrar(plantas, 2), (0, 0))
    return s


def _nat(q: int, fundo: pygame.Surface, textura: pygame.Surface) -> pygame.Surface:
    t = q / QUADROS
    img = fundo.copy()
    (mx, my), p = meteoro(t)
    _brilho(img, (mx, my), int(40 + 8 * p), (90, 70, 50))
    dx, dy = RASTRO
    pygame.draw.line(img, (200, 170, 140), (mx, my), (mx + dx * 60, my + dy * 60), 2)
    pygame.draw.circle(img, (255, 238, 210), (int(mx), int(my)), int(3 + p))
    tr = trex(t)
    sombra = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)  # a sombra no chao
    px, _ = tr["pe"]
    pygame.draw.ellipse(sombra, (0, 0, 0, 70), (px - 130, SOLO - 7, 270, 14))
    img.blit(sombra, (0, 0))
    bicho = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    pygame.draw.polygon(bicho, (78, 68, 48, 255), tr["perna_tras"])
    for parte in ("corpo", "perna", "braco"):
        pygame.draw.polygon(bicho, (104, 92, 64, 255), tr[parte])
    listras = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for k in range(6):  # listras no dorso, so onde ha corpo
        bx = px - 60 + k * 28
        pygame.draw.polygon(listras, (255, 255, 255, 255), [(bx, SOLO - 200), (bx + 10, SOLO - 200),
                                                             (bx - 6, SOLO - 120), (bx - 16, SOLO - 120)])
    m = pygame.mask.from_surface(bicho)
    listra = m.overlap_mask(pygame.mask.from_surface(listras), (0, 0))
    bicho.blit(listra.to_surface(setcolor=(84, 74, 52, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
    _sombreado(bicho, (150, 136, 98), (64, 56, 40))
    ox, oy = tr["olho"]
    pygame.draw.circle(bicho, (24, 20, 16, 255), (int(ox), int(oy)), 3)
    pygame.draw.circle(bicho, (220, 210, 190, 255), (int(ox + 1), int(oy - 1)), 1)
    rt = rato(t)
    _rato_simples(bicho, rt, (70, 54, 40) if _no_tunel(rt) else (126, 96, 66))
    img.blit(_borrar(bicho, 2), (0, 0))
    img.blit(textura, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    return img


# ---------------------------------------------------------------- 5. 2.5D (serio + naturalista)
#
# Camera inclinada sobre um chao com profundidade (o jeito de Don't Starve): cada coisa e um
# recorte pintado (cor de terra, faixa de luz em cima, sombra embaixo, borda quente do lado do
# por do sol, contorno de tinta), posto no chao em (x, z) e reduzido com a distancia; a neblina
# puxa o que esta longe para a cor do horizonte; sombra redonda no chao embaixo de cada um. A
# camera desliza de lado: o que esta perto anda mais que o que esta longe (a profundidade).
# Aqui nao se ve debaixo da terra: no jogo, a toca seria um interior (entra no buraco, troca a tela).

HORIZONTE_25 = 168
FOCO_25 = 900.0
ALTURA_CAM = 1.5
NEVOA_25: Cor = (176, 124, 108)
TINTA_25: Cor = (30, 22, 20)
BURACO = (1.4, 4.6)  # x, z da toca
TREX_25 = (-2.6, 13.0)
F25 = 3  # os recortes sao pintados em 3x e so reduzidos (ampliar serrilha)


def _proj(x: float, z: float, cx: float) -> Tuple[float, float, float]:
    """Um ponto do chao na tela, e quantos pixels vale uma unidade naquela distancia."""
    k = FOCO_25 / z
    return LARGURA / 2 + (x - cx) * k, HORIZONTE_25 + ALTURA_CAM * k, k


def _nevoa_de(z: float) -> float:
    return min(0.75, max(0.0, (z - 5) / 45))


def _nevoa(s: pygame.Surface, f: float, cor: Cor = NEVOA_25) -> pygame.Surface:
    if f <= 0:
        return s
    s = s.copy()
    g = int(255 * (1 - f))
    s.fill((g, g, g), special_flags=pygame.BLEND_RGB_MULT)
    s.fill(tuple(int(c * f) for c in cor), special_flags=pygame.BLEND_RGB_ADD)
    return s


def _recorte(pecas: Sequence[Tuple[Sequence[Pt], Cor]], luz: Cor, borda: Cor = (222, 130, 78),
             contorno: int = 2) -> Tuple[pygame.Surface, Pt]:
    """Pinta as pecas (pontos relativos ao pe, em pixels) como um recorte: base, sombra embaixo,
    luz em cima, borda quente a direita e contorno de tinta. Devolve a imagem e onde fica o pe.
    Tudo e pintado em `F25`x."""
    f = F25
    pecas = [([(x * f, y * f) for x, y in pts], cor) for pts, cor in pecas]
    xs = [x for pts, _ in pecas for x, _ in pts]
    ys = [y for pts, _ in pecas for _, y in pts]
    x0, y0 = min(xs) - 6 * f, min(ys) - 6 * f
    w, h = int(max(xs) - x0) + 6 * f + 1, int(max(ys) - y0) + 6 * f + 1
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    for pts, cor in pecas:
        pygame.draw.polygon(s, (*cor, 255), [(x - x0, y - y0) for x, y in pts])
    m = pygame.mask.from_surface(s)
    s.blit(_faixa(m, (2 * f, 8 * f)).to_surface(setcolor=(0, 0, 0, 80), unsetcolor=(0, 0, 0, 0)), (0, 0))
    s.blit(_faixa(m, (-2 * f, -5 * f)).to_surface(setcolor=(*luz, 120), unsetcolor=(0, 0, 0, 0)), (0, 0))
    s.blit(_faixa(m, (3 * f, -2 * f)).to_surface(setcolor=(*borda, 210), unsetcolor=(0, 0, 0, 0)), (0, 0))
    final = pygame.Surface((w, h), pygame.SRCALPHA)
    tinta = m.to_surface(setcolor=(*TINTA_25, 255), unsetcolor=(0, 0, 0, 0))
    for i in range(8):
        a = 2 * math.pi * i / 8
        final.blit(tinta, (round(math.cos(a) * contorno * f), round(math.sin(a) * contorno * f)))
    final.blit(s, (0, 0))
    return final, (-x0, -y0)


def _planta_25(tipo: str) -> Tuple[pygame.Surface, Pt, float]:
    """O recorte de uma planta (ou pedra) e a altura dela no mundo, em unidades."""
    folha, tronco_cor = (58, 78, 44), (84, 66, 48)
    if tipo == "cicadacea":
        pecas = [([(-5, 0), (5, 0), (4, -38), (-4, -38)], tronco_cor)]
        pecas += [(_folha((0, -38), math.radians(-160 + i * 140 / 6), 46, 11, 0.25), folha) for i in range(7)]
        altura = 1.5
    elif tipo == "arborea":
        pecas = [([(-5, 0), (5, 0), (3, -122), (-3, -122)], tronco_cor)]
        pecas += [(_folha((0, -122), math.radians(-172 + i * 164 / 7), 72, 13, 0.35), folha) for i in range(8)]
        altura = 4.2
    elif tipo == "samambaia":
        pecas = [(_folha((0, 0), math.radians(-165 + i * 30), 34 + (i % 2) * 8, 8, 0.15), folha) for i in range(6)]
        altura = 0.5
    else:  # pedra
        pecas = [(_elipse(0, -10, 22, 12), (98, 90, 86))]
        altura = 0.45
    surf, pe = _recorte(pecas, (122, 140, 84))
    return surf, pe, altura


def _rato_25(olhando: bool) -> Tuple[pygame.Surface, Pt]:
    cor = (128, 98, 68)
    hy = -18 if olhando else -13
    pecas = [([(-14, -6), (-28, -2), (-28, 0), (-14, -3)], cor), (_elipse(0, -8, 16, 8), cor),
             (_elipse(10, hy - 7, 3.5, 3.5, 10), cor), (_elipse(13, hy, 8, 8, 14), cor)]
    surf, pe = _recorte(pecas, (176, 146, 106), contorno=1)
    pygame.draw.circle(surf, TINTA_25, (int(pe[0] + 16 * F25), int(pe[1] + (hy - 1) * F25)), 2 * F25)
    return surf, pe


def _recorte_trex(t: float) -> Tuple[pygame.Surface, Pt]:
    """O tiranossauro do instante `t` como recorte (em `F25`x; a altura dele e 201 * F25)."""
    tr = trex(t)
    px, py = tr["pe"]
    rel = {n: [(x - px, y - py) for x, y in tr[n]] for n in ("perna_tras", "corpo", "perna", "braco")}
    surf, pe = _recorte([(rel["perna_tras"], (80, 70, 50)), (rel["corpo"], (106, 94, 66)),
                         (rel["perna"], (106, 94, 66)), (rel["braco"], (106, 94, 66))], (156, 142, 104))
    ox, oy = tr["olho"]
    ex, ey = pe[0] + (ox - px) * F25, pe[1] + (oy - py) * F25
    pygame.draw.circle(surf, TINTA_25, (int(ex), int(ey)), 3 * F25)
    pygame.draw.circle(surf, (230, 170, 120), (int(ex + F25), int(ey - F25)), F25)
    return surf, pe


def _escalar(surf: pygame.Surface, pe: Pt, k: float) -> Tuple[pygame.Surface, Pt]:
    w, h = max(1, round(surf.get_width() * k)), max(1, round(surf.get_height() * k))
    return pygame.transform.smoothscale(surf, (w, h)), (pe[0] * k, pe[1] * k)


def _sombra_chao(img: pygame.Surface, sx: float, sy: float, largura: float) -> None:
    w, h = max(2, int(largura)), max(2, int(largura * 0.24))
    sombra = pygame.Surface((w, h), pygame.SRCALPHA)
    pygame.draw.ellipse(sombra, (0, 0, 0, 90), (0, 0, w, h))
    img.blit(sombra, (sx - w / 2, sy - h / 2))


def _prep_25d() -> Dict[str, object]:
    fundo = pygame.Surface((LARGURA, ALTURA))
    _degrade(fundo, (38, 34, 62), (120, 70, 84), 0, 110)
    _degrade(fundo, (120, 70, 84), (228, 136, 88), 110, HORIZONTE_25)
    morros = [(x, HORIZONTE_25 - 14 - 10 * math.sin(x / 80) - 6 * math.sin(x / 33 + 2)) for x in range(0, 961, 16)]
    pygame.draw.polygon(fundo, (132, 92, 96), morros + [(960, HORIZONTE_25 + 2), (0, HORIZONTE_25 + 2)])
    pygame.draw.polygon(fundo, (98, 66, 72), [(560, HORIZONTE_25 + 2), (650, 96), (668, 92), (684, 96),
                                              (790, HORIZONTE_25 + 2)])
    _brilho(fundo, (668, 96), 22, (150, 50, 24))
    camada = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for i in range(6):
        pygame.draw.circle(camada, (88, 70, 76, int(150 * (1 - i / 7))),
                           (int(672 + 12 * i + 6 * math.sin(i * 1.7)), int(88 - 13 * i)), int(7 + 3 * i))
    fundo.blit(_borrar(camada, 4), (0, 0))
    perto = (74, 60, 42)
    for y in range(HORIZONTE_25 + 1, ALTURA):  # o chao: escuro perto, a cor do horizonte longe
        f = _nevoa_de(ALTURA_CAM * FOCO_25 / (y - HORIZONTE_25)) / 0.75
        cor = tuple(int(a + (b - a) * f) for a, b in zip(perto, (168, 120, 100)))
        pygame.draw.line(fundo, cor, (0, y), (LARGURA, y))
    rng = random.Random(21)
    objetos = [("arborea", 6.5, 20.0), ("arborea", -8.0, 24.0), ("arborea", 1.5, 31.0), ("arborea", -9.5, 17.0),
               ("cicadacea", 3.8, 9.5), ("cicadacea", -6.0, 7.8), ("cicadacea", 7.5, 13.0)]
    objetos += [("samambaia", rng.uniform(-9, 9), rng.uniform(5, 28)) for _ in range(16)]
    objetos += [("pedra", rng.uniform(-8, 8), rng.uniform(5, 22)) for _ in range(6)]
    estaticos = []
    for tipo, x, z in objetos:
        surf, pe, altura = _planta_25(tipo)
        k = FOCO_25 / z * altura / pe[1]
        surf, pe = _escalar(surf, pe, k)
        estaticos.append((z, x, _nevoa(surf, _nevoa_de(z)), pe, surf.get_width() * 0.6))
    ratos = {}
    for olhando in (False, True):
        surf, pe = _rato_25(olhando)
        ratos[olhando] = _escalar(surf, pe, FOCO_25 / BURACO[1] * 0.34 / (26 * F25))
    tufos = [(rng.uniform(-12, 12), rng.uniform(4.2, 40)) for _ in range(220)]
    return {"fundo": fundo, "estaticos": estaticos, "ratos": ratos, "tufos": tufos, "vinheta": _vinheta(0.45),
            "textura": _textura_pincel(), "cinzas": _cinzas()[:36]}


def _d25(q: int, prep: Dict[str, object]) -> pygame.Surface:
    t = q / QUADROS
    cx = 0.6 * math.sin(2 * math.pi * t)  # a camera desliza de lado e volta
    img = prep["fundo"].copy()
    (mx, my), p = meteoro(t)
    mx, my = mx - 30, my - 20
    _brilho(img, (mx, my), int(44 + 10 * p), (110, 70, 44))
    dx, dy = RASTRO
    pygame.draw.line(img, (220, 180, 140), (mx, my), (mx + dx * 70, my + dy * 70), 2)
    pygame.draw.circle(img, (255, 240, 214), (int(mx), int(my)), int(3 + p))
    for x, z in prep["tufos"]:  # capim: tracinhos no chao, mais apagados longe
        sx, sy, k = _proj(x, z, cx)
        if 0 <= sx < LARGURA:
            f = _nevoa_de(z)
            cor = tuple(int(a + (b - a) * f) for a, b in zip((60, 76, 40), NEVOA_25))
            alto = max(1.0, 0.12 * k)
            pygame.draw.line(img, cor, (sx, sy), (sx - alto * 0.3, sy - alto), 1)
            pygame.draw.line(img, cor, (sx + 2, sy), (sx + 2 + alto * 0.2, sy - alto * 0.8), 1)
    desenhos = [(z, "planta", (x, surf, pe, larg)) for z, x, surf, pe, larg in prep["estaticos"]]
    desenhos.append((TREX_25[1], "trex", None))
    desenhos.append((BURACO[1], "toca", None))
    for z, tipo, dados in sorted(desenhos, key=lambda d: -d[0]):  # de longe para perto
        if tipo == "planta":
            x, surf, pe, larg = dados
            sx, sy, _ = _proj(x, z, cx)
            if -200 < sx < LARGURA + 200:
                _sombra_chao(img, sx, sy, larg)
                img.blit(surf, (sx - pe[0], sy - pe[1]))
        elif tipo == "trex":
            surf, pe = _recorte_trex(t)
            sx, sy, k = _proj(TREX_25[0], z, cx)
            surf, pe = _escalar(surf, pe, k * 3.6 / (201 * F25))
            _sombra_chao(img, sx, sy, surf.get_width() * 0.7)
            img.blit(_nevoa(surf, _nevoa_de(z)), (sx - pe[0], sy - pe[1]))
        else:  # a toca: o buraco no chao e o mamifero que sai dele
            sx, sy, k = _proj(BURACO[0], z, cx)
            w, h = 0.75 * k, 0.75 * k * 0.3
            pygame.draw.ellipse(img, (96, 76, 54), (sx - w / 2 - 4, sy - h / 2 - 2, w + 8, h + 6))
            pygame.draw.ellipse(img, (22, 15, 12), (sx - w / 2, sy - h / 2, w, h))
            surf, pe = prep["ratos"][0.25 < t < 0.6]
            visivel = int(surf.get_height() * _subida(t))
            if visivel > 0:
                img.blit(surf, (sx - pe[0] + 6, sy - visivel), area=pygame.Rect(0, 0, surf.get_width(), visivel))
    for x0, y0, amp, fase, r in prep["cinzas"]:
        y = (y0 + t * ALTURA) % ALTURA
        x = x0 + amp * math.sin(2 * math.pi * t + fase)
        pygame.draw.circle(img, (238, 150, 90) if r > 1.5 else (150, 120, 112), (int(x), int(y)), 1)
    img.blit(prep["textura"], (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    img.blit(prep["vinheta"], (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    _grao(img, q, 6)
    return img


# ---------------------------------------------------------------- 6. 3D com recortes
#
# O mesmo tom do 2.5D, mas num mundo 3D de verdade: o chao, os morros e o vulcao sao malhas
# (rasterizadas com z-buffer pelo `tres_d`, a luz calculada uma vez nos vertices), e os recortes
# ficam em pe no mundo, sempre de frente para a camera (billboards, como em Don't Starve), cada um
# testado contra a profundidade do chao: um morro na frente esconde quem esta atras. No meio do
# laco a camera gira 90 graus e volta -- os recortes giram junto, sempre mostrando o mesmo lado.

R3 = 3  # o chao 3D sai em 1/3 da resolucao (o rasterizador e de CPU); os recortes, na cheia
W3, H3 = LARGURA // R3, ALTURA // R3
NEVOA_3D = np.array([196.0, 134.0, 110.0])
RAIO_CAM, ALTO_CAM, FOV_3D = 12.5, 4.2, 32.0


def _altura_3d(x: float, z: float) -> float:
    morro = 1.6 * math.exp(-((x + 5.5) ** 2 + (z + 5.0) ** 2) / 6.0)  # um morro, para esconder alguem
    return 0.25 * math.sin(x * 0.55) * math.cos(z * 0.45) + morro


def _giro_3d(t: float) -> float:
    """O angulo da camera em graus: parada, gira 90, parada, volta."""
    if t < 0.3:
        return 0.0
    if t < 0.45:
        return 90 * _suave((t - 0.3) / 0.15)
    if t < 0.8:
        return 90.0
    if t < 0.95:
        return 90 * (1 - _suave((t - 0.8) / 0.15))
    return 0.0


def _virar_xz(tris):
    """Troca x e z (o mesmo relevo do outro lado) mantendo as faces para fora."""
    return [((c[2], c[1], c[0]), (b[2], b[1], b[0]), (a[2], a[1], a[0]), cor, em, cam)
            for a, b, c, cor, em, cam in tris]


def _prep_3d() -> Dict[str, object]:
    from games.vitrine_estilos import tres_d  # aqui dentro: so este tom usa o 3D

    rng = random.Random(9)

    def terra(x: float, z: float) -> Cor:
        verde = 0.5 + 0.5 * math.sin(x * 0.35 + 1.0) * math.cos(z * 0.3)
        tom = rng.uniform(-6, 6)
        return (int(92 - 22 * verde + tom), int(76 + 6 * verde + tom), int(52 - 6 * verde + tom))

    tris = tres_d.chao(-14, 14, -14, 14, 2.0, terra, _altura_3d)
    longe = tres_d.montanhas(-34, -18, -40, 40, 8, 5.0, 3, (110, 82, 88))
    tris += longe + _virar_xz(longe)
    tris += tres_d.cone((-24.0, 0.0, -24.0), 9.0, 8.0, (98, 74, 70), lados=9)
    V, base, emiss, _, n = tres_d._arrays(tris)
    luzes = [("dir", tres_d._unit((-0.5, 0.45, -0.7)), np.array([1.3, 0.92, 0.66])),
             ("dir", tres_d._unit((0.6, 0.5, 0.6)), np.array([0.30, 0.32, 0.50]))]
    cv = tres_d.iluminar(V, n, base, emiss, np.array([0.50, 0.42, 0.58]), np.array([0.24, 0.20, 0.16]), luzes)
    ceu = pygame.Surface((W3, H3))
    _degrade(ceu, (38, 34, 62), (228, 136, 88), 0, int(H3 * 0.62))
    ceu.fill((228, 136, 88), (0, int(H3 * 0.62), W3, H3))
    objetos = [("arborea", 6.0, -6.5), ("arborea", -8.5, 3.0), ("arborea", 3.0, -10.0), ("arborea", -6.0, -9.0),
               ("cicadacea", 4.5, 4.0), ("cicadacea", -4.0, 6.0), ("cicadacea", 8.0, 1.0)]
    objetos += [("samambaia", rng.uniform(-10, 10), rng.uniform(-10, 10)) for _ in range(14)]
    objetos += [("pedra", rng.uniform(-9, 9), rng.uniform(-9, 9)) for _ in range(6)]
    recortes = []
    for tipo, x, z in objetos:
        if math.hypot(x - 2.2, z - 2.5) > 1.5 and math.hypot(x + 2.5, z + 1.5) > 2.5:  # longe da toca e do trex
            surf, pe, altura = _planta_25(tipo)
            recortes.append((x, z, surf, pe, altura))
    return {"V": V, "cv": cv, "ceu": pygame.surfarray.array3d(ceu).swapaxes(0, 1).astype(np.float64),
            "recortes": recortes, "ratos": {o: _rato_25(o) for o in (False, True)}, "vinheta": _vinheta(0.45),
            "textura": _textura_pincel(), "tres_d": tres_d}


def _carimbar(arr: np.ndarray, zbuf: np.ndarray, surf: pygame.Surface, x0: int, y0: int, z: float) -> None:
    """Compoe um recorte na imagem (W, H, 3) so onde o chao nao esta na frente dele."""
    w, h = surf.get_size()
    xa, ya, xb, yb = max(0, x0), max(0, y0), min(LARGURA, x0 + w), min(ALTURA, y0 + h)
    if xa >= xb or ya >= yb:
        return
    rgb = pygame.surfarray.array3d(surf)[xa - x0:xb - x0, ya - y0:yb - y0].astype(np.float64)
    a = pygame.surfarray.array_alpha(surf)[xa - x0:xb - x0, ya - y0:yb - y0] / 255.0
    a = a * (zbuf[xa:xb, ya:yb] > z - 0.4)
    arr[xa:xb, ya:yb] = arr[xa:xb, ya:yb] * (1 - a[..., None]) + rgb * a[..., None]


def _d3(q: int, prep: Dict[str, object]) -> pygame.Surface:
    tres_d = prep["tres_d"]
    t = q / QUADROS
    giro = math.radians(_giro_3d(t))
    cam = tres_d._camera((RAIO_CAM * math.sin(giro), ALTO_CAM, RAIO_CAM * math.cos(giro)), (0.0, 1.0, 0.0))
    foco = (W3 / 2) / math.tan(math.radians(FOV_3D))
    sx, sy, zv = tres_d._projetar(prep["V"], cam, foco, W3, H3)
    vis = zv.min(axis=1) > 0.3
    img, zb = tres_d.rasterizar(sx[vis], sy[vis], zv[vis], prep["cv"][vis], prep["ceu"])
    f = np.where(np.isinf(zb), 0.0, np.clip((zb - 10) / 28, 0, 0.7))[..., None]
    img = img * (1 - f) + NEVOA_3D * f
    tela = pygame.transform.smoothscale(pygame.surfarray.make_surface(np.clip(img, 0, 255).astype(np.uint8)
                                                                      .swapaxes(0, 1)), (LARGURA, ALTURA))
    zcheio = np.repeat(np.repeat(zb, R3, axis=0), R3, axis=1).T  # (W, H), como o surfarray
    foco2 = foco * R3

    def proj(x: float, y: float, z: float) -> Tuple[float, float, float]:
        px, py, pz = tres_d._projetar(np.array([[x, y, z]]), cam, foco2, LARGURA, ALTURA)
        return float(px[0]), float(py[0]), float(pz[0])

    mx, my, mz = proj(-8.0, 20.0, -60.0)  # o meteoro: um ponto longe no ceu (gira com a camera)
    if mz > 0:
        (_, _), p = meteoro(t)
        _brilho(tela, (mx, my), int(40 + 10 * p), (110, 70, 44))
        pygame.draw.circle(tela, (255, 240, 214), (int(mx), int(my)), int(3 + p))
    bx, bz = 2.2, 2.5  # a toca: o buraco e a borda de terra, deitados no chao
    for raio, cor in ((0.5, (100, 80, 56)), (0.38, (22, 15, 12))):
        pts = [proj(bx + raio * math.cos(a), _altura_3d(bx, bz) + 0.02, bz + raio * math.sin(a))
               for a in np.linspace(0, 2 * math.pi, 16, endpoint=False)]
        pygame.draw.polygon(tela, cor, [(x, y) for x, y, _ in pts])
    desenhos = []
    for x, z, surf, pe, altura in prep["recortes"]:
        desenhos.append((x, z, surf, pe, altura))
    surf_t, pe_t = _recorte_trex(t)
    desenhos.append((-2.5, -1.5, surf_t, pe_t, 3.6))
    projetados = []
    for x, z, surf, pe, altura in desenhos:
        px, py, pz = proj(x, _altura_3d(x, z), z)
        if pz > 0.5:
            projetados.append((pz, px, py, surf, pe, foco2 * altura / pz / pe[1]))
    sombra = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for pz, px, py, surf, pe, k in projetados:  # sombras redondas no chao
        w = surf.get_width() * k * 0.6
        pygame.draw.ellipse(sombra, (0, 0, 0, 80), (px - w / 2, py - w * 0.14, w, w * 0.28))
    tela.blit(sombra, (0, 0))
    arr = pygame.surfarray.array3d(tela).astype(np.float64)
    rato_surf, rato_pe = prep["ratos"][0.25 < t < 0.6]
    rx, ry, rz = proj(bx, _altura_3d(bx, bz), bz)
    projetados.append((rz, rx, ry, rato_surf, rato_pe, foco2 * 0.34 / rz / (26 * F25)))
    for pz, px, py, surf, pe, k in sorted(projetados, key=lambda d: -d[0]):  # de longe para perto
        s, (ax, ay) = _escalar(surf, pe, k)
        if surf is rato_surf:  # o mamifero sai do buraco: so a parte de cima aparece
            visivel = int(s.get_height() * _subida(t))
            if visivel <= 0:
                continue
            s = s.subsurface((0, 0, s.get_width(), visivel)).copy()
            ay = visivel
        s = _nevoa(s, min(0.6, max(0.0, (pz - 10) / 30)))
        _carimbar(arr, zcheio, s, int(px - ax), int(py - ay), pz)
    img = pygame.surfarray.make_surface(np.clip(arr, 0, 255).astype(np.uint8))
    img.blit(prep["textura"], (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    img.blit(prep["vinheta"], (0, 0), special_flags=pygame.BLEND_RGB_MULT)
    _grao(img, q, 6)
    return img


# ---------------------------------------------------------------- tudo junto

def gerar(estilo: str) -> List[pygame.Surface]:
    """Os `QUADROS` quadros 960x540 de um tom."""
    if estilo == "bio_leve":
        fundo = _leve_fundo()
        return [_leve(q, fundo) for q in range(QUADROS)]
    if estilo == "bio_silhueta":
        fundo, vinheta, cinzas = _sil_fundo(), _vinheta(), _cinzas()
        return [_sil(q, fundo, vinheta, cinzas) for q in range(QUADROS)]
    if estilo == "bio_pixel":
        fundo = _pixel_fundo()
        return [_pixel(q, fundo) for q in range(QUADROS)]
    if estilo == "bio_naturalista":
        fundo, textura = _nat_fundo(), _textura_pincel()
        return [_nat(q, fundo, textura) for q in range(QUADROS)]
    if estilo == "bio_25d":
        prep = _prep_25d()
        return [_d25(q, prep) for q in range(QUADROS)]
    if estilo == "bio_3d":
        prep = _prep_3d()
        return [_d3(q, prep) for q in range(QUADROS)]
    raise ValueError(f"estilo desconhecido: {estilo!r}")
