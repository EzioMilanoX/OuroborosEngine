# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
A arte da vitrine de estilos (ROADMAP fase 8): a MESMA cena -- um espadachim sob a
lua, ao lado de um torii, respirando e dando um corte -- pintada em seis estilos.

`pose_t(t)` diz onde cada parte do personagem esta no instante `t` do laco (0..1, em
unidades de 960x540);
cada estilo so decide COMO pintar essas formas. E o que a fase 8 quer da engine:
o jogo descreve a cena, o estilo e uma escolha de apresentacao.

O que cada estilo usa (das tecnicas que estudios usam de verdade):

    celshading  sombra puxada para o frio (nao para o preto), luz de recorte do lado da lua,
                contorno externo mais grosso que o interno, sombra de contato nos pes,
                rastro no corte; pintado em 2x e reduzido com suavizacao
    pixel       160x90; rampas de cor com matiz deslocado (sombra para o azul, luz para o
                amarelo), contorno seletivo (o tom escuro da propria peca, nao preto),
                pontilhado ordenado no ceu e no halo da lua; ampliado sem suavizar
    sumie       pincel com pressao, falhas de pincel seco ao longo do traco, tinta que se
                espalha em volta (difusao), grao do papel aparecendo atraves da tinta
    neon        formas chapadas no escuro, contornos de luz, bloom em piramide (como o
                dual Kawase), reflexo no chao molhado, aberracao cromatica e varredura
    lowpoly     3D de verdade (tres_d.py): malhas de triangulos, camera em perspectiva, uma
                cor por face, luz de tres pontos, sombras projetadas, brilho
    terror      o mesmo 3D com as limitacoes do PS1 (tres_d.py): baixa resolucao, vertice
                tremido, z-buffer, neblina preta, so a lanterna ilumina
"""
from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np
import pygame

LARGURA, ALTURA = 960, 540
QUADROS = 48  # 2 s a 24 quadros por segundo (o laco inteiro)
FPS = 24
ESTILOS: Tuple[str, ...] = ("celshading", "pixel", "sumie", "neon", "lowpoly", "terror")
NOMES: Dict[str, Tuple[str, str]] = {
    "celshading": ("Ilustracao cel-shading", "sombra fria, luz de recorte, contorno externo grosso"),
    "pixel": ("Pixel art", "160x90, rampas com matiz deslocado, contorno seletivo, pontilhado"),
    "sumie": ("Tinta / sumi-e", "pincel seco, tinta que se espalha, grao do papel, selo"),
    "neon": ("Flat com luz", "bloom em piramide, reflexo molhado, aberracao cromatica"),
    "lowpoly": ("Low poly (3D)", "uma cor por face, luz de tres pontos, sombras projetadas"),
    "terror": ("Terror PS1 (3D)", "320x180, vertice tremido, z-buffer, neblina preta, lanterna"),
}
HORIZONTE = 400
LUA = (740, 120, 58)


# --------------------------------------------------------------- a cena (geometria)

def _suave(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _sai_rapido(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


GUARDA, ALTO, FIM = math.radians(-28), math.radians(-135), math.radians(38)


def pose(q: int) -> Dict[str, object]:
    return pose_t(q / QUADROS)


def pose_t(t: float) -> Dict[str, object]:
    """O laco de 2 s, com os principios de animacao: respira em guarda; ANTECIPA (a espada
    recua acima da cabeca e o corpo abaixa); CORTA rapido, desacelerando no fim; SEGURA o
    golpe enquanto o rastro se desfaz; e VOLTA suave para a guarda."""
    t %= 1.0
    respira, agacha, avanco = 0.0, 0.0, 0.0
    engaja = 0.0  # 0: braco baixo em guarda; 1: braco acompanha a espada
    corte = None
    if t < 0.55:
        respira = math.sin(t / 0.55 * 2 * math.pi) * 3
        ang = GUARDA + math.radians(2) * math.sin(t / 0.55 * 4 * math.pi)
    elif t < 0.70:
        k = _suave((t - 0.55) / 0.15)
        ang, agacha, engaja = GUARDA + (ALTO - GUARDA) * k, 7 * k, k
    elif t < 0.78:
        k = _sai_rapido((t - 0.70) / 0.08)
        ang, agacha, avanco, engaja = ALTO + (FIM - ALTO) * k, 7 * (1 - k), 12 * k, 1.0
        corte = (ALTO - math.radians(8), ang, k)
    elif t < 0.88:
        k = (t - 0.78) / 0.10
        ang, avanco, engaja = FIM, 12.0, 1.0
        corte = (ALTO + (FIM - ALTO) * _suave(k), FIM, 1.0)  # o rastro se desfaz do comeco ao fim
    else:
        k = _suave((t - 0.88) / 0.12)
        ang, avanco, engaja = FIM + (GUARDA - FIM) * k, 12 * (1 - k), 1 - k
    px, pe = 330.0 + avanco, 425.0
    topo = pe - 150 + respira + agacha
    ombro = (px + 14, topo + 44)
    mao_guarda = (px + 46, topo + 92)
    mao_alta = (ombro[0] + math.cos(ang) * 44, ombro[1] + math.sin(ang) * 44)
    mao = (mao_guarda[0] + (mao_alta[0] - mao_guarda[0]) * engaja, mao_guarda[1] + (mao_alta[1] - mao_guarda[1]) * engaja)
    ponta = (mao[0] + math.cos(ang) * 92, mao[1] + math.sin(ang) * 92)
    if corte is not None:
        a0, a1, prog = corte
        corte = (ombro[0] + 10, ombro[1] + 6, 120, a0, a1, prog) if a1 - a0 > 0.05 else None
    return {
        "respira": respira - agacha,
        "ang_espada": ang,
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


def _torii() -> Dict[str, List[Tuple[float, float]]]:
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
        pts.append((LARGURA * i / n, base - rng.uniform(0.3, 1.0) * alto))
    pts += [(float(LARGURA), base), (float(LARGURA), float(ALTURA))]
    return pts


def _arco(cx, cy, r, a0, a1, n=24):
    return [(cx + math.cos(a0 + (a1 - a0) * i / n) * r, cy + math.sin(a0 + (a1 - a0) * i / n) * r) for i in range(n + 1)]


def _crescente(corte, espessura):
    cx, cy, r, a0, a1, _ = corte
    if a1 - a0 < 0.05:
        return []
    return _arco(cx, cy, r, a0, a1) + _arco(cx, cy, r - espessura, a1, a0)


def _degrade(surf, topo, base, y0, y1):
    for y in range(int(y0), int(y1)):
        k = (y - y0) / max(1, y1 - y0)
        pygame.draw.line(surf, [int(a + (b - a) * k) for a, b in zip(topo, base)], (0, y), (surf.get_width(), y))


def _borrar(surf: pygame.Surface, div: int) -> pygame.Surface:
    w, h = surf.get_size()
    pequena = pygame.transform.smoothscale(surf, (max(1, w // div), max(1, h // div)))
    return pygame.transform.smoothscale(pequena, (w, h))


# ---------------------------------------------------------------- 1. cel-shading

CONTORNO = (22, 16, 28)
LUZ = (-0.6, -0.8)  # a luz principal: o ceu, de cima a esquerda
RECORTE = (1.0, -0.7)  # a lua, atras e a direita: a luz de recorte
COR_RECORTE = (255, 236, 214)


def _tons(base):
    """Base, sombra (puxada para o roxo frio, nao para o preto) e brilho (para o creme)."""
    sombra = tuple(int(c + (t - c) * 0.45) for c, t in zip(base, (40, 24, 80)))
    brilho = tuple(int(c + (t - c) * 0.4) for c, t in zip(base, (255, 246, 226)))
    return base, sombra, brilho


def _faixa(m: pygame.mask.Mask, v: Tuple[float, float]) -> pygame.mask.Mask:
    """Os pixels da mascara perto da borda que aponta na direcao `v`."""
    f = m.copy()
    f.erase(m, (int(-v[0]), int(-v[1])))
    return f


class _Pintor:
    """Peca a peca: contorno fino, base, sombra, brilho e luz de recorte (mascaras
    deslocadas); no fim, um contorno externo grosso em volta de tudo. Pinta em `s`x."""

    def __init__(self, s: int = 2, regiao: Tuple[int, int, int, int] = (0, 0, LARGURA, ALTURA)) -> None:
        self.s = s
        self.x0, self.y0, self.w, self.h = regiao  # so esta parte da tela (em 1x) e pintada
        self.tela = pygame.Surface((self.w * s, self.h * s), pygame.SRCALPHA)

    def _mascara(self, pts, circulo) -> pygame.mask.Mask:
        s = self.s
        tmp = pygame.Surface(self.tela.get_size(), pygame.SRCALPHA)
        if circulo:
            pygame.draw.circle(tmp, (255, 255, 255), ((circulo[0] - self.x0) * s, (circulo[1] - self.y0) * s), circulo[2] * s)
        else:
            pygame.draw.polygon(tmp, (255, 255, 255), [((x - self.x0) * s, (y - self.y0) * s) for x, y in pts])
        return pygame.mask.from_surface(tmp)

    def _carimbar(self, m, cor, raio):
        sil = m.to_surface(setcolor=(*cor, 255), unsetcolor=(0, 0, 0, 0))
        for i in range(12):
            a = 2 * math.pi * i / 12
            self.tela.blit(sil, (math.cos(a) * raio, math.sin(a) * raio))

    def parte(self, pts, base, *, contorno=1.4, tamanho=40, circulo=None, recorte=True):
        s = self.s
        m = self._mascara(pts, circulo)
        cor, sombra, brilho = _tons(base)
        self._carimbar(m, CONTORNO, contorno * s)
        self.tela.blit(m.to_surface(setcolor=(*cor, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
        d = tamanho * 0.3 * s
        self.tela.blit(_faixa(m, (-LUZ[0] * d, -LUZ[1] * d)).to_surface(setcolor=(*sombra, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
        d = tamanho * 0.1 * s
        self.tela.blit(_faixa(m, (LUZ[0] * d, LUZ[1] * d)).to_surface(setcolor=(*brilho, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
        if recorte:
            d = 2.2 * s
            rim = _faixa(m, (RECORTE[0] * d, RECORTE[1] * d))
            self.tela.blit(rim.to_surface(setcolor=(*COR_RECORTE, 255), unsetcolor=(0, 0, 0, 0)), (0, 0))

    def silhueta(self, larg: float) -> None:
        """O contorno externo, mais grosso que os internos (o peso de linha que le de longe)."""
        m = pygame.mask.from_surface(self.tela)
        novo = pygame.Surface(self.tela.get_size(), pygame.SRCALPHA)
        sil = m.to_surface(setcolor=(*CONTORNO, 255), unsetcolor=(0, 0, 0, 0))
        for i in range(16):
            a = 2 * math.pi * i / 16
            novo.blit(sil, (math.cos(a) * larg * self.s, math.sin(a) * larg * self.s))
        novo.blit(self.tela, (0, 0))
        self.tela = novo

    def linha(self, a, b, cor, larg):
        s = self.s
        pygame.draw.line(self.tela, cor, ((a[0] - self.x0) * s, (a[1] - self.y0) * s),
                         ((b[0] - self.x0) * s, (b[1] - self.y0) * s), int(larg * s))

    def final(self):
        return pygame.transform.smoothscale(self.tela, (self.w, self.h))


def _cel_fundo() -> pygame.Surface:
    fundo = pygame.Surface((LARGURA, ALTURA))
    _degrade(fundo, (52, 36, 92), (240, 140, 104), 0, HORIZONTE)
    halo = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)  # o halo da lua
    for i in range(8):
        pygame.draw.circle(halo, (255, 236, 200, 18), LUA[:2], LUA[2] + 70 - i * 8)
    fundo.blit(_borrar(halo, 4), (0, 0))
    p = _Pintor(2)
    p.parte(None, (248, 234, 204), circulo=LUA, tamanho=60, recorte=False)
    p.parte(_montanhas(3, HORIZONTE, 130), (150, 110, 150), tamanho=60, contorno=1.0)  # longe: perto do ceu
    p.parte(_montanhas(8, HORIZONTE + 6, 70, 6), (92, 66, 112), tamanho=50, contorno=1.2)
    pygame.draw.rect(p.tela, (88, 120, 84), (0, HORIZONTE * 2, LARGURA * 2, (ALTURA - HORIZONTE) * 2))
    pygame.draw.rect(p.tela, (70, 98, 74), (0, (HORIZONTE + 40) * 2, LARGURA * 2, (ALTURA - HORIZONTE) * 2))
    pygame.draw.line(p.tela, CONTORNO, (0, HORIZONTE * 2), (LARGURA * 2, HORIZONTE * 2), 6)
    rng = random.Random(4)
    for _ in range(60):  # tufos de capim na linha do chao
        x = rng.uniform(0, LARGURA)
        y = HORIZONTE + rng.uniform(4, 120)
        for k in (-1, 0, 1):
            p.linha((x, y), (x + k * 4, y - rng.uniform(5, 10)), (60, 88, 64), 1.6)
    for nome, pts in _torii().items():
        p.parte(pts, (210, 54, 46) if nome != "nuki" else (176, 40, 38), tamanho=24)
    fundo.blit(p.final(), (0, 0))
    return fundo


REGIAO_PERSONAGEM = (150, 140, 440, 330)  # onde o espadachim, a espada e o corte cabem


def _cel(q: int, fundo: pygame.Surface) -> pygame.Surface:
    f = pose(q)
    p = _Pintor(2, REGIAO_PERSONAGEM)
    ombro, mao = f["braco"]
    p.parte(f["hakama"], (54, 58, 96), tamanho=40)
    p.parte(f["tronco"], (224, 218, 204), tamanho=40)
    p.parte(f["obi"], (156, 40, 52), tamanho=10, recorte=False)
    p.linha(f["espada"][0], f["espada"][1], CONTORNO, 8)
    p.linha(f["espada"][0], f["espada"][1], (226, 232, 240), 3.4)
    p.linha(f["espada"][0], f["espada"][1], (255, 255, 255), 1.2)
    dx, dy = mao[0] - ombro[0], mao[1] - ombro[1]
    n = math.hypot(dx, dy) or 1
    nx, ny = -dy / n * 7, dx / n * 7
    p.parte([(ombro[0] + nx, ombro[1] + ny), (mao[0] + nx, mao[1] + ny), (mao[0] - nx, mao[1] - ny), (ombro[0] - nx, ombro[1] - ny)],
            (224, 218, 204), tamanho=14)
    p.parte(None, (240, 202, 172), circulo=(mao[0], mao[1], 7), tamanho=8)
    cx, cy, r = f["cabeca"]
    p.parte(None, (240, 202, 172), circulo=(cx, cy, r), tamanho=24)
    p.parte([(cx - r, cy - 2), (cx - r + 2, cy - r + 2), (cx + r - 2, cy - r), (cx + r, cy - 4), (cx, cy - 8)], (34, 30, 44), tamanho=16)
    p.parte(f["coque"], (34, 30, 44), tamanho=10)
    p.linha((cx + 8, cy + 1), (cx + 12, cy + 1), CONTORNO, 2.4)
    p.silhueta(2.4)  # o contorno externo grosso
    if f["corte"]:
        cx2, cy2, r2, a0, a1, k = f["corte"]
        for i, alfa in enumerate((50, 90, 140)):  # o rastro do corte, sumindo para tras
            pts = _crescente((cx2, cy2, r2 - 6 * (3 - i), a0, a1 - 0.25 * (3 - i), k), 10)
            if len(pts) > 3:
                pygame.draw.polygon(p.tela, (210, 236, 255, alfa), [((x - p.x0) * 2, (y - p.y0) * 2) for x, y in pts])
        pts = _crescente(f["corte"], 22 * (1 - k * 0.5))
        if len(pts) > 3:
            p.parte(pts, (238, 250, 255), contorno=2.2, tamanho=12, recorte=False)
    img = fundo.copy()
    contato = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)  # a sombra de contato nos pes
    px, pe = f["pes"]
    pygame.draw.ellipse(contato, (20, 30, 24, 150), (px - 52, pe - 10, 110, 20))
    img.blit(_borrar(contato, 4), (0, 0))
    img.blit(p.final(), (p.x0, p.y0))
    return img


# ---------------------------------------------------------------- 2. pixel art

BAYER = [[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]
CEU = [(22, 14, 40), (48, 28, 76), (92, 48, 110), (158, 76, 120), (226, 120, 104), (250, 184, 128)]
K_PIXEL = 6


def _girar_matiz(cor, alvo_h: float, quanto: float, v: float, s: float):
    c = pygame.Color(*cor)
    h, sat, val, _ = c.hsva
    d = ((alvo_h - h + 540) % 360) - 180
    c.hsva = ((h + d * quanto) % 360, max(0, min(100, sat * s)), max(0, min(100, val * v)), 100)
    return (c.r, c.g, c.b)


def _rampa(base):
    """[contorno, sombra, base, luz]: a sombra gira para o azul/roxo e ganha saturacao, a
    luz gira para o amarelo; o contorno e o tom mais escuro da propria rampa."""
    return [
        _girar_matiz(base, 250, 0.35, 0.42, 1.25),
        _girar_matiz(base, 250, 0.18, 0.72, 1.12),
        tuple(base),
        _girar_matiz(base, 55, 0.2, 1.18, 0.82),
    ]


def _pp_parte(s, pts=None, base=(200, 200, 200), circulo=None):
    """Uma peca em pixel art: contorno seletivo (4 vizinhos, no tom escuro da peca), base,
    sombra no lado de baixo/direita e luz no de cima/esquerda, sem nenhuma suavizacao."""
    rampa = _rampa(base)
    tmp = pygame.Surface(s.get_size(), pygame.SRCALPHA)
    if circulo:
        pygame.draw.circle(tmp, (255, 255, 255), circulo[:2], circulo[2])
    else:
        pygame.draw.polygon(tmp, (255, 255, 255), pts)
    m = pygame.mask.from_surface(tmp)
    sil = m.to_surface(setcolor=(*rampa[0], 255), unsetcolor=(0, 0, 0, 0))
    for d in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        s.blit(sil, d)
    s.blit(m.to_surface(setcolor=(*rampa[2], 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
    s.blit(_faixa(m, (2, 2)).to_surface(setcolor=(*rampa[1], 255), unsetcolor=(0, 0, 0, 0)), (0, 0))
    s.blit(_faixa(m, (-1, -1)).to_surface(setcolor=(*rampa[3], 255), unsetcolor=(0, 0, 0, 0)), (0, 0))


_PIXEL_FUNDO: Optional[pygame.Surface] = None


def _pixel(q: int) -> pygame.Surface:
    global _PIXEL_FUNDO
    k = K_PIXEL
    w, h = LARGURA // k, ALTURA // k
    if _PIXEL_FUNDO is None:
        _PIXEL_FUNDO = _pixel_fundo()
    s = _PIXEL_FUNDO.copy()
    rng = random.Random(2)
    for _ in range(18):  # estrelas, piscando devagar (cada uma no seu ritmo)
        x, y = rng.randrange(w), rng.randrange(HORIZONTE // k // 2)
        if math.sin(q / QUADROS * 2 * math.pi * 3 + x) > -0.3:
            s.set_at((x, y), (236, 220, 240))
    _pixel_personagem(s, q)
    return pygame.transform.scale(s, (LARGURA, ALTURA))  # vizinho mais proximo: pixels nitidos


def _pixel_fundo() -> pygame.Surface:
    k = K_PIXEL
    w, h = LARGURA // k, ALTURA // k
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    hz = HORIZONTE // k
    faixas = len(CEU) - 1
    for y in range(hz):  # o ceu em faixas, com pontilhado ordenado entre elas
        t = y / hz * faixas
        i = min(faixas - 1, int(t))
        frac = t - i
        for x in range(w):
            s.set_at((x, y), CEU[i + 1] if frac * 16 > BAYER[y % 4][x % 4] else CEU[i])
    lx, ly, lr = LUA[0] // k, LUA[1] // k, LUA[2] // k
    for y in range(ly - lr - 5, ly + lr + 6):  # o halo da lua, pontilhado
        for x in range(lx - lr - 5, lx + lr + 6):
            d = math.hypot(x - lx, y - ly)
            if lr < d < lr + 5 and (x + y) % 2 == 0 and 0 <= x < w and 0 <= y < hz:
                s.set_at((x, y), CEU[-1] if d < lr + 3 else CEU[-2])
    _pp_parte(s, base=(250, 232, 196), circulo=(lx, ly, lr))
    for seed, alto, cor in ((3, 130, (110, 62, 120)), (8, 70, (62, 38, 88))):
        _pp_parte(s, [(x / k, y / k) for x, y in _montanhas(seed, HORIZONTE, alto)], base=cor)
    pygame.draw.rect(s, (66, 108, 78), (0, hz, w, h - hz))
    pygame.draw.rect(s, (44, 76, 62), (0, hz + 6, w, h - hz - 6))
    for x in range(0, w, 3):  # o capim
        s.set_at((x, hz - 1), (66, 108, 78))
        s.set_at((x + 1, hz + 1 + x % 4), (90, 140, 90))
    for nome, pts in _torii().items():
        _pp_parte(s, [(x / k, y / k) for x, y in pts], base=(222, 70, 56) if nome != "nuki" else (184, 46, 44))
    return s


def _pixel_personagem(s: pygame.Surface, q: int) -> None:
    k = K_PIXEL
    f = pose(q)

    def pp(pts):
        return [(round(x / k), round(y / k)) for x, y in pts]

    px, pe = f["pes"]
    pygame.draw.line(s, (36, 62, 52), (round(px / k) - 6, round(pe / k)), (round(px / k) + 7, round(pe / k)))
    _pp_parte(s, pp(f["hakama"]), base=(72, 80, 140))
    _pp_parte(s, pp(f["tronco"]), base=(232, 222, 208))
    _pp_parte(s, pp(f["obi"]), base=(190, 52, 60))
    a, b = pp(f["espada"])
    pygame.draw.line(s, (40, 40, 60), (a[0] + 1, a[1] + 1), (b[0] + 1, b[1] + 1))
    pygame.draw.line(s, (214, 232, 244), a, b)
    a, b = pp(f["braco"])
    pygame.draw.line(s, (120, 100, 110), a, b, 3)
    pygame.draw.line(s, (232, 222, 208), a, b, 1)
    cx, cy, r = f["cabeca"]
    hx, hy = round(cx / k), round(cy / k)
    _pp_parte(s, base=(236, 190, 156), circulo=(hx, hy, round(r / k)))
    pygame.draw.rect(s, (40, 30, 52), (hx - 3, hy - 3, 6, 2))
    s.set_at((hx - 1, hy - 4), (40, 30, 52))
    s.set_at((hx + 1, hy), (40, 30, 52))
    if f["corte"]:
        cx2, cy2, r2, a0, a1, _ = f["corte"]
        for x, y in _arco(cx2, cy2, r2, a0, a1, 30):
            s.set_at((round(x / k), round(y / k)), (255, 255, 255))
            s.set_at((round(x / k) - 1, round(y / k) + 1), (170, 214, 240))
        for x, y in _arco(cx2, cy2, r2 - 9, a0, max(a0, a1 - 0.4), 20):  # o rastro
            if round(x) % 2:
                s.set_at((round(x / k), round(y / k)), (120, 160, 210))


# ---------------------------------------------------------------- 3. sumi-e

TINTA = (24, 20, 26)
_GRAO: Optional[np.ndarray] = None


def _pincel(alvo, pts, larg, rng, alfa=230, seco=0.25):
    """Um traco de pincel: carimbos de largura variavel (pressao que sobe e cai) numa
    camada propria; riscos vazios ao longo do traco (as cerdas secando), cerdas soltas no
    fim e uma aureola de tinta que se espalhou no papel, antes de aplicar a transparencia."""
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    m = larg + 8
    ox, oy = int(min(xs) - m), int(min(ys) - m)
    camada = pygame.Surface((int(max(xs) - ox + m) + 1, int(max(ys) - oy + m) + 1), pygame.SRCALPHA)
    total = sum(math.dist(pts[i], pts[i + 1]) for i in range(len(pts) - 1)) or 1
    feito = 0.0
    cerdas = [rng.uniform(-0.45, 0.45) for _ in range(5)]
    falhas = [(rng.uniform(-0.4, 0.4), rng.uniform(0.25, 0.6)) for _ in range(3)]
    caminho = []
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
            caminho.append((x, y, nx, ny, r, k))
            if k < 1 - seco:
                pygame.draw.circle(camada, (*TINTA, 255), (x, y), r)
            else:  # pincel seco: so as cerdas, com falhas
                for c in cerdas:
                    if rng.random() < 0.8 - (k - (1 - seco)) / seco * 0.5:
                        pygame.draw.circle(camada, (*TINTA, 255), (x + nx * c * r * 2, y + ny * c * r * 2), max(0.7, r * 0.18))
        feito += seg
    for c, inicio in falhas:  # riscos vazios: a cerda que ficou sem tinta
        anterior = None
        for x, y, nx, ny, r, k in caminho:
            p = (x + nx * c * r * 2, y + ny * c * r * 2)
            if k > inicio and anterior is not None and rng.random() < 0.85:
                pygame.draw.line(camada, (0, 0, 0, 0), anterior, p, 1)
            anterior = p
    aureola = _borrar(camada, 3)  # a tinta que se espalhou nas fibras
    aureola.fill((255, 255, 255, int(alfa * 0.22)), special_flags=pygame.BLEND_RGBA_MULT)
    alvo.blit(aureola, (ox, oy))
    camada.fill((255, 255, 255, alfa), special_flags=pygame.BLEND_RGBA_MULT)
    alvo.blit(camada, (ox, oy))


def _aguada(alvo, pts, alfa):
    camada = pygame.Surface(alvo.get_size(), pygame.SRCALPHA)
    pygame.draw.polygon(camada, (*TINTA, alfa), pts)
    alvo.blit(_borrar(camada, 6), (0, 0))  # borda molhada


def _sumie_fundo() -> pygame.Surface:
    global _GRAO
    rng = random.Random(5)
    papel = pygame.Surface((LARGURA, ALTURA))
    papel.fill((238, 228, 204))
    fibras = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    for _ in range(1400):  # as fibras do papel
        x, y = rng.uniform(0, LARGURA), rng.uniform(0, ALTURA)
        a = rng.uniform(0, math.pi)
        c = rng.choice([(214, 200, 172, 120), (250, 244, 228, 160)])
        pygame.draw.line(fibras, c, (x, y), (x + math.cos(a) * rng.uniform(3, 14), y + math.sin(a) * rng.uniform(3, 14)))
    papel.blit(fibras, (0, 0))
    ruido = np.random.default_rng(9).random((LARGURA // 3, ALTURA // 3))
    grao = pygame.surfarray.make_surface((ruido * 255).astype(np.uint8)[..., None].repeat(3, axis=2))
    grao = pygame.transform.smoothscale(grao, (LARGURA, ALTURA))
    _GRAO = 0.72 + 0.28 * (pygame.surfarray.array3d(grao)[..., 0] / 255.0)  # o papel atravessa a tinta
    tinta = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    pygame.draw.circle(tinta, (*TINTA, 26), LUA[:2], LUA[2] + 8)  # a lua: o papel em branco, cercado de aguada
    pygame.draw.circle(tinta, (0, 0, 0, 0), LUA[:2], LUA[2])
    for seed, alto, alfa in ((3, 130, 60), (8, 70, 110)):  # montanhas em aguada que somem no chao
        pts = _montanhas(seed, HORIZONTE + (6 if seed == 8 else 0), alto, 9 if seed == 3 else 6)
        _aguada(tinta, [(x, min(y, HORIZONTE + 24)) for x, y in pts], alfa)
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
    _aplicar_grao(tinta)
    papel.blit(tinta, (0, 0))
    selo = pygame.Rect(866, 446, 58, 58)  # o selo vermelho (hanko), com a borda gasta
    pygame.draw.rect(papel, (190, 40, 40), selo, border_radius=4)
    for i in range(3):
        pygame.draw.line(papel, (238, 228, 204), (selo.x + 12, selo.y + 14 + i * 14), (selo.right - 12, selo.y + 14 + i * 14), 4)
    pygame.draw.line(papel, (238, 228, 204), (selo.centerx, selo.y + 10), (selo.centerx, selo.bottom - 10), 4)
    for _ in range(40):
        papel.set_at((rng.randrange(selo.x, selo.right), rng.randrange(selo.y, selo.bottom)), (238, 228, 204))
    return papel


def _aplicar_grao(camada: pygame.Surface) -> None:
    if _GRAO is None:
        return
    alfa = pygame.surfarray.pixels_alpha(camada)
    alfa[:] = (alfa * _GRAO).astype(np.uint8)
    del alfa


def _sumie(q: int, fundo: pygame.Surface) -> pygame.Surface:
    rng = random.Random((q // 4) * 31 + 7)  # o traco 'treme' de 4 em 4 quadros, como a mao
    f = pose(q)
    tinta = pygame.Surface((LARGURA, ALTURA), pygame.SRCALPHA)
    hk = f["hakama"]
    _aguada(tinta, hk, 80)
    _pincel(tinta, [hk[0], hk[6]], 26, rng)
    _pincel(tinta, [hk[1], hk[2]], 26, rng)
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
        for _ in range(12):
            a = rng.uniform(a0, a1)
            d = r + rng.uniform(10, 46)
            pygame.draw.circle(tinta, (*TINTA, 210), (cx + math.cos(a) * d, cy + math.sin(a) * d), rng.uniform(1, 4))
    _aplicar_grao(tinta)
    img = fundo.copy()
    img.blit(tinta, (0, 0))
    return img


# ---------------------------------------------------------------- 4. flat com luz

_VINHETA: Optional[np.ndarray] = None


def _bloom(base: pygame.Surface, luz: pygame.Surface) -> pygame.Surface:
    """Bloom em piramide: a camada de luz reduzida a 1/2, 1/4 ... 1/32 (cada reducao suaviza)
    e somada de volta com pesos que caem -- o mesmo espirito do dual Kawase, barato."""
    out = base.copy()
    for div, peso in ((2, 0.9), (4, 0.75), (8, 0.6), (16, 0.45), (32, 0.35)):
        b = _borrar(luz, div)
        b.fill((int(255 * peso),) * 3, special_flags=pygame.BLEND_RGB_MULT)
        out.blit(b, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    out.blit(luz, (0, 0), special_flags=pygame.BLEND_RGB_ADD)
    return out


def _acabamento_neon(img: pygame.Surface) -> pygame.Surface:
    """Aberracao cromatica (vermelho e azul separados nas bordas), varredura e vinheta."""
    global _VINHETA
    if _VINHETA is None:
        xs = np.linspace(-1, 1, LARGURA)[:, None]
        ys = np.linspace(-1, 1, ALTURA)[None, :]
        _VINHETA = np.clip(1.15 - 0.45 * (xs ** 2 + ys ** 2), 0.4, 1.0)
    px = pygame.surfarray.array3d(img).astype(np.float32)
    r, b = px[..., 0].copy(), px[..., 2].copy()
    px[3:, :, 0] = r[:-3, :]
    px[:-3, :, 2] = b[3:, :]
    px[:, ::3, :] *= 0.8
    px *= _VINHETA[..., None]
    return pygame.surfarray.make_surface(np.clip(px, 0, 255).astype(np.uint8))


def _sol(base: pygame.Surface, luz: pygame.Surface) -> None:
    """O sol/lua de poster: degrade rosa para laranja, cortado por faixas que engrossam."""
    cx, cy, r = LUA
    for y in range(cy - r, cy + r):
        k = (y - (cy - r)) / (2 * r)
        meia = math.sqrt(max(0, r * r - (y - cy) ** 2))
        faixa = k > 0.5 and int((y - cy) / 3) % (2 + int((1 - k) * 6)) == 0
        if faixa:
            continue
        cor = (int(240 - 20 * k), int(50 + 120 * k), int(150 - 110 * k))
        pygame.draw.line(base, cor, (cx - meia, y), (cx + meia, y))
        pygame.draw.line(luz, tuple(int(c * 0.16) for c in cor), (cx - meia, y), (cx + meia, y))


def _neon_fundo() -> Tuple[pygame.Surface, pygame.Surface]:
    base = pygame.Surface((LARGURA, ALTURA))
    _degrade(base, (6, 4, 20), (40, 12, 60), 0, HORIZONTE)
    base.fill((8, 6, 20), (0, HORIZONTE, LARGURA, ALTURA - HORIZONTE))
    luz = pygame.Surface((LARGURA, ALTURA))
    _sol(base, luz)
    pygame.draw.polygon(base, (14, 8, 32), _montanhas(3, HORIZONTE, 130))
    pygame.draw.lines(luz, (120, 60, 220), False, _montanhas(3, HORIZONTE, 130)[1:-1], 2)
    for nome, pts in _torii().items():
        pygame.draw.polygon(base, (20, 10, 38), pts)
        pygame.draw.polygon(luz, (255, 70, 100), pts, 3)
    return base, luz


def _chao_neon(luz: pygame.Surface, q: int) -> None:
    for i in range(16):  # o chao em grade, em perspectiva, andando para a frente
        x = LARGURA / 2 + (i - 7.5) * 140
        pygame.draw.line(luz, (70, 34, 130), (LARGURA / 2 + (x - LARGURA / 2) * 0.12, HORIZONTE), (x, ALTURA), 1)
    for i in range(8):
        t = ((i + q / QUADROS) / 8) ** 1.9
        y = HORIZONTE + (ALTURA - HORIZONTE) * t
        pygame.draw.line(luz, (70, 34, 130), (0, y), (LARGURA, y), 1)


def _neon(q: int, fundo: Tuple[pygame.Surface, pygame.Surface]) -> pygame.Surface:
    base, luz = fundo[0].copy(), fundo[1].copy()
    f = pose(q)
    for nome in ("hakama", "tronco"):
        pygame.draw.polygon(base, (12, 10, 28), f[nome])
        pygame.draw.polygon(luz, (40, 220, 255), f[nome], 2)
    pygame.draw.polygon(luz, (255, 70, 140), f["obi"], 2)
    a, b = f["braco"]
    pygame.draw.line(base, (12, 10, 28), a, b, 12)
    pygame.draw.line(luz, (40, 220, 255), a, b, 2)
    a, b = f["espada"]
    pygame.draw.line(luz, (230, 255, 255), a, b, 3)
    cx, cy, r = f["cabeca"]
    pygame.draw.circle(base, (12, 10, 28), (cx, cy), r)
    pygame.draw.circle(luz, (40, 220, 255), (cx, cy), r, 2)
    pygame.draw.line(luz, (255, 255, 255), (cx + 6, cy), (cx + 13, cy), 2)
    rng = random.Random(1)
    for i in range(36):  # as particulas subindo
        x = rng.uniform(0, LARGURA)
        y = (rng.uniform(0, HORIZONTE) - q / QUADROS * HORIZONTE * rng.choice((1, 2))) % HORIZONTE
        pygame.draw.circle(luz, rng.choice([(40, 180, 230), (210, 60, 170)]), (x, y), 1.5)
    if f["corte"]:
        cx2, cy2, r2, a0, a1, k = f["corte"]
        pts = _arco(cx2, cy2, r2, a0, a1)
        if len(pts) > 1:
            pygame.draw.lines(luz, (190, 250, 255), False, pts, int(10 * (1 - k * 0.6)) + 2)
            pygame.draw.lines(luz, (255, 255, 255), False, pts, 2)
    reflexo = luz.subsurface((0, HORIZONTE - (ALTURA - HORIZONTE), LARGURA, ALTURA - HORIZONTE)).copy()
    reflexo = pygame.transform.flip(reflexo, False, True)  # o chao molhado espelha o que brilha
    reflexo.fill((90, 90, 110), special_flags=pygame.BLEND_RGB_MULT)
    luz.blit(reflexo, (0, HORIZONTE), special_flags=pygame.BLEND_RGB_ADD)
    _chao_neon(luz, q)
    return _acabamento_neon(_bloom(base, luz))



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
    if estilo in ("lowpoly", "terror"):
        from games.vitrine_estilos import tres_d  # aqui dentro: tres_d usa a pose deste modulo

        pintar = tres_d.lowpoly if estilo == "lowpoly" else tres_d.terror
        return [pintar(q) for q in range(QUADROS)]
    raise ValueError(f"estilo desconhecido: {estilo!r}")
