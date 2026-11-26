# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A cena do ASCII Knight: um cavaleiro numa arena com pilares e arvores, duas gosmas e um
morcego. Mostra a `Projecao` (de cima / 3/4 / isometrica, tecla P), a `FilaProfundidade`
(passar atras e na frente do pilar), a sombra eliptica no chao, o pulo (altura z) e os tres
jeitos de desenhar (tecla F): ASCII nativo (`TelaAscii` + `draw_ascii`), o filtro ASCII sobre
o render normal (`set_ascii_filter`) e o render normal sem filtro.

A logica do mundo (andar, pular, golpe, inimigos) vive em `update`; `render` so desenha.
"""
from __future__ import annotations

import math
import random
from typing import Callable, List, Optional, Tuple

import numpy as np

from games.ascii_knight import arte
from ouroboros.bootstrap.scene import IScene
from ouroboros.core.ascii import FiltroAscii, SpriteAscii, TelaAscii
from ouroboros.core.projecao import DE_CIMA, MODOS, TRES_QUARTOS, FilaProfundidade, Projecao
from ouroboros.core.world import World
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

ARENA = (960.0, 640.0)  # o chao, em unidades do mundo
FONTE = 14  # o tamanho da fonte do ASCII nativo
FONTE_FILTRO = 12
HUD_PX = 30  # a faixa de baixo com o texto de ajuda (fora do filtro)
CELULA_PADRAO = (8, 14)  # se o renderer nao tem ASCII (backend nulo)

VELOCIDADE = 230.0
GRAVIDADE = 980.0
PULO = 360.0
ALTURA_PILAR = 120.0
ALTURA_ARVORE = 110.0

MODOS_RENDER = ("ascii", "filtro", "normal")
NOMES_RENDER = {"ascii": "ASCII nativo", "filtro": "filtro ASCII", "normal": "render normal"}
NOMES_PROJECAO = {"de_cima": "de cima", "3/4": "3/4", "isometrica": "isometrica"}

FUNDO = (6, 8, 12)
CHAO_A = (14, 26, 16)
CHAO_B = (18, 33, 20)
BORDA = (120, 150, 110)
BRANCO = (240, 240, 240)


class Ator:
    """Qualquer coisa que se mexe ou fica em pe na arena."""

    __slots__ = ("tipo", "x", "y", "z", "vx", "vy", "vz", "raio", "hp", "hp_max", "olhando",
                 "estado", "t", "piscar", "invencivel", "vivo", "t_volta", "fase", "acertou",
                 "espera")

    def __init__(self, tipo: str, x: float, y: float, raio: float, hp: int = 1) -> None:
        self.tipo = tipo
        self.x, self.y, self.z = x, y, 0.0
        self.vx = self.vy = self.vz = 0.0
        self.raio = raio
        self.hp = self.hp_max = hp
        self.olhando = 1  # 1 direita, -1 esquerda (na tela)
        self.estado = "parado"
        self.t = 0.0
        self.piscar = 0.0
        self.invencivel = 0.0
        self.vivo = True
        self.t_volta = 0.0
        self.fase = 0.0
        self.acertou = False
        self.espera = 0.8


class Efeito:
    __slots__ = ("x", "y", "z", "t")

    def __init__(self, x: float, y: float, z: float) -> None:
        self.x, self.y, self.z, self.t = x, y, z, 0.0


class AsciiKnightScene(IScene):
    def __init__(self, entrada: IInputProvider, renderer: IRenderer,
                 ao_sair: Optional[Callable[[], None]] = None, seed: int = 7) -> None:
        self.entrada = entrada
        self.ao_sair = ao_sair
        self.rng = random.Random(seed)
        self.largura, self.altura = renderer.get_viewport_size()
        self.altura_jogo = self.altura - HUD_PX
        self.modo_render = "ascii"
        self.proj = Projecao(TRES_QUARTOS, tela=(self.largura, self.altura_jogo))
        self.relogio = 0.0
        self.abates = 0
        self.quedas = 0

        self.cavaleiro = Ator("cavaleiro", ARENA[0] * 0.5, ARENA[1] * 0.62, 16.0, hp=5)
        self.inimigos: List[Ator] = [
            Ator("gosma", 220.0, 180.0, 18.0, hp=2),
            Ator("gosma", 760.0, 470.0, 18.0, hp=2),
            Ator("morcego", 700.0, 160.0, 14.0, hp=1),
        ]
        for i, e in enumerate(self.inimigos):
            e.espera = 0.7 + 0.25 * i
            e.fase = i * 2.1
        # cenario fixo: (tipo, x, y, raio)
        self.cenario: List[Tuple[str, float, float, float]] = [
            ("pilar", 320.0, 200.0, 24.0), ("pilar", 640.0, 200.0, 24.0),
            ("pilar", 320.0, 470.0, 24.0), ("pilar", 640.0, 470.0, 24.0),
            ("arvore", 110.0, 110.0, 22.0), ("arvore", 860.0, 120.0, 22.0),
            ("arvore", 130.0, 540.0, 22.0), ("arvore", 850.0, 560.0, 22.0),
        ]
        self.efeitos: List[Efeito] = []

        # marcas no chao: projetadas em lote a cada quadro (Projecao.tela_de_lote)
        n = 170
        self._gx = np.array([self.rng.uniform(12, ARENA[0] - 12) for _ in range(n)])
        self._gy = np.array([self.rng.uniform(12, ARENA[1] - 12) for _ in range(n)])
        self._gsx = np.zeros(n)
        self._gsy = np.zeros(n)
        self._gch = [self.rng.choice(",.'`\"") for _ in range(n)]
        self._gcor = [(40 + self.rng.randint(0, 40), 90 + self.rng.randint(0, 60), 50) for _ in range(n)]
        self.proj.reservar(n)

        # a ordem de desenho: ids 0..k-1 = cenario, depois atores, depois efeitos especiais
        self.fila = FilaProfundidade(64)
        self._elipse = np.zeros((20, 2))  # vertices de sombra reaproveitados (render normal)

        self._celula = CELULA_PADRAO
        self._tela: Optional[TelaAscii] = None
        self._fundo_chao: Optional[np.ndarray] = None
        self._filtro_ligado = False
        self.filtro = FiltroAscii(tamanho_fonte=FONTE_FILTRO, area=(0, 0, self.largura, self.altura_jogo))
        cel = renderer.ascii_cell_size(FONTE)
        if cel is not None:
            self._celula = cel
        self._ajustar_camera()

    # ================================================================ camera

    def _ajustar_camera(self) -> None:
        """Cabe a arena inteira na tela no modo atual, com folga em cima para os pilares."""
        p = self.proj
        p.zoom = 1.0
        p.centralizar(ARENA[0] * 0.5, ARENA[1] * 0.5)
        cantos = [p.tela_de(x, y) for x, y in ((0, 0), (ARENA[0], 0), (0, ARENA[1]), ARENA)]
        bw = max(c[0] for c in cantos) - min(c[0] for c in cantos)
        bh = max(c[1] for c in cantos) - min(c[1] for c in cantos)
        folga = 150.0 if p.achatamento < 1.0 else 90.0
        p.zoom = min(self.largura * 0.94 / bw, (self.altura_jogo - folga) / bh)
        desce = folga * 0.42
        p.centralizar(*p.mundo_de(self.largura * 0.5, self.altura_jogo * 0.5 - desce))
        self._fundo_chao = None  # o xadrez do chao muda com a projecao

    def trocar_projecao(self) -> None:
        i = MODOS.index(self.proj.modo)
        self.proj.modo = MODOS[(i + 1) % len(MODOS)]
        self._ajustar_camera()

    def trocar_render(self) -> None:
        i = MODOS_RENDER.index(self.modo_render)
        self.modo_render = MODOS_RENDER[(i + 1) % len(MODOS_RENDER)]

    # ================================================================ logica

    def _direcao(self) -> Tuple[float, float]:
        """A entrada (setas/WASD) e na tela; vira uma direcao no chao pela projecao."""
        e = self.entrada
        ix = float(e.is_action_held("direita")) - float(e.is_action_held("esquerda"))
        iy = float(e.is_action_held("baixo")) - float(e.is_action_held("cima"))
        if not ix and not iy:
            return 0.0, 0.0
        p = self.proj
        ax, ay = p.mundo_de(p.largura * 0.5, p.altura * 0.5)
        bx, by = p.mundo_de(p.largura * 0.5 + ix * 10.0, p.altura * 0.5 + iy * 10.0)
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy) or 1.0
        return dx / n, dy / n

    def _lado_na_tela(self, x: float, y: float, vx: float, vy: float) -> float:
        return self.proj.tela_x(x + vx, y + vy) - self.proj.tela_x(x, y)

    def update(self, world: World, delta_time: float) -> None:
        dt = min(delta_time, 1 / 20)
        self.relogio += dt
        e = self.entrada
        if e.is_action_pressed("sair") and self.ao_sair is not None:
            self.ao_sair()
            return
        if e.is_action_pressed("modo"):
            self.trocar_render()
        if e.is_action_pressed("projecao"):
            self.trocar_projecao()
        self._atualizar_cavaleiro(dt)
        for inimigo in self.inimigos:
            self._atualizar_inimigo(inimigo, dt)
        for ef in self.efeitos:
            ef.t += dt
        self.efeitos = [ef for ef in self.efeitos if not arte.PUF.acabou(ef.t)]

    def _atualizar_cavaleiro(self, dt: float) -> None:
        k, e = self.cavaleiro, self.entrada
        k.t += dt
        k.piscar = max(0.0, k.piscar - dt)
        k.invencivel = max(0.0, k.invencivel - dt)
        if e.is_action_pressed("atacar") and k.estado != "ataque":
            k.estado, k.t, k.acertou = "ataque", 0.0, False
        if e.is_action_pressed("pular") and k.z <= 0.0:
            k.vz = PULO
        dx, dy = self._direcao()
        vel = VELOCIDADE * (0.35 if k.estado == "ataque" else 1.0)
        # empurrao (dano) decai; o andar soma por cima
        k.vx *= math.exp(-8.0 * dt)
        k.vy *= math.exp(-8.0 * dt)
        k.x += (k.vx + dx * vel) * dt
        k.y += (k.vy + dy * vel) * dt
        if dx or dy:
            lado = self._lado_na_tela(k.x, k.y, dx, dy)
            if abs(lado) > 1e-6 and k.estado != "ataque":
                k.olhando = 1 if lado > 0 else -1
        if k.estado == "ataque":
            if not k.acertou and arte.ATAQUE.indice(k.t) >= arte.QUADRO_DO_CORTE:
                k.acertou = True
                self._golpe()
            if arte.ATAQUE.acabou(k.t):
                k.estado, k.t = "parado", 0.0
        else:
            novo = "andando" if (dx or dy) else "parado"
            if novo != k.estado:
                k.estado, k.t = novo, 0.0
        self._gravidade(k, dt)
        self._colidir(k)

    def _gravidade(self, a: Ator, dt: float) -> bool:
        """Aplica o pulo/queda; True no quadro em que encosta no chao."""
        if a.z <= 0.0 and a.vz <= 0.0:
            a.z, a.vz = 0.0, 0.0
            return False
        a.vz -= GRAVIDADE * dt
        a.z += a.vz * dt
        if a.z <= 0.0:
            a.z, a.vz = 0.0, 0.0
            return True
        return False

    def _colidir(self, a: Ator) -> None:
        for _, x, y, r in self.cenario:
            dx, dy = a.x - x, a.y - y
            d = math.hypot(dx, dy)
            minimo = r + a.raio
            if d < minimo:
                if d < 1e-6:
                    dx, dy, d = 1.0, 0.0, 1.0
                a.x = x + dx / d * minimo
                a.y = y + dy / d * minimo
        a.x = min(max(a.x, a.raio), ARENA[0] - a.raio)
        a.y = min(max(a.y, a.raio), ARENA[1] - a.raio)

    def _golpe(self) -> None:
        """O corte acerta quem esta perto, na frente (na tela) e mais ou menos na mesma altura."""
        k = self.cavaleiro
        kx = self.proj.tela_x(k.x, k.y)
        for e in self.inimigos:
            if not e.vivo:
                continue
            d = math.hypot(e.x - k.x, e.y - k.y)
            frente = (self.proj.tela_x(e.x, e.y) - kx) * k.olhando
            if d < k.raio + e.raio + 62.0 and frente > -12.0 and abs(e.z - k.z) < 70.0:
                e.hp -= 1
                e.piscar = 0.18
                n = d or 1.0
                e.vx += (e.x - k.x) / n * 420.0
                e.vy += (e.y - k.y) / n * 420.0
                if e.hp <= 0:
                    e.vivo = False
                    e.t_volta = 2.2
                    self.abates += 1
                    self.efeitos.append(Efeito(e.x, e.y, e.z))

    def _renascer(self, e: Ator) -> None:
        lado = self.rng.randint(0, 3)
        if lado == 0:
            e.x, e.y = self.rng.uniform(40, ARENA[0] - 40), 30.0
        elif lado == 1:
            e.x, e.y = self.rng.uniform(40, ARENA[0] - 40), ARENA[1] - 30.0
        elif lado == 2:
            e.x, e.y = 30.0, self.rng.uniform(40, ARENA[1] - 40)
        else:
            e.x, e.y = ARENA[0] - 30.0, self.rng.uniform(40, ARENA[1] - 40)
        e.vx = e.vy = e.vz = e.z = 0.0
        e.hp, e.vivo, e.t = e.hp_max, True, 0.0
        self.efeitos.append(Efeito(e.x, e.y, 0.0))

    def _atualizar_inimigo(self, e: Ator, dt: float) -> None:
        if not e.vivo:
            e.t_volta -= dt
            if e.t_volta <= 0.0:
                self._renascer(e)
            return
        k = self.cavaleiro
        e.t += dt
        e.piscar = max(0.0, e.piscar - dt)
        e.vx *= math.exp(-6.0 * dt)
        e.vy *= math.exp(-6.0 * dt)
        dx, dy = k.x - e.x, k.y - e.y
        d = math.hypot(dx, dy) or 1.0
        if e.tipo == "gosma":
            # pula em direcao ao cavaleiro de tempos em tempos
            if e.z <= 0.0 and e.t >= e.espera:
                e.vz, e.t = 250.0, 0.0
            andar = 110.0 if e.z > 0.0 else 0.0
            e.x += (e.vx + dx / d * andar) * dt
            e.y += (e.vy + dy / d * andar) * dt
            self._gravidade(e, dt)
            self._colidir(e)
        else:
            # o morcego voa em volta do cavaleiro, subindo e descendo
            e.fase += dt
            alvo_x = k.x + math.cos(e.fase * 1.3) * 90.0
            alvo_y = k.y + math.sin(e.fase * 1.3) * 60.0
            ax, ay = alvo_x - e.x, alvo_y - e.y
            n = math.hypot(ax, ay) or 1.0
            rapido = min(150.0, n * 3.0)
            e.x += (e.vx + ax / n * rapido) * dt
            e.y += (e.vy + ay / n * rapido) * dt
            e.z = 52.0 + 14.0 * math.sin(e.fase * 3.0)
            e.x = min(max(e.x, e.raio), ARENA[0] - e.raio)
            e.y = min(max(e.y, e.raio), ARENA[1] - e.raio)
        lado = self.proj.tela_x(k.x, k.y) - self.proj.tela_x(e.x, e.y)
        if abs(lado) > 2.0:
            e.olhando = 1 if lado > 0 else -1
        # encostou no cavaleiro: dano e empurrao
        if d < k.raio + e.raio and abs(k.z - e.z) < 34.0 and k.invencivel <= 0.0:
            k.hp -= 1
            k.invencivel, k.piscar = 1.0, 0.25
            k.vx -= dx / d * 320.0
            k.vy -= dy / d * 320.0
            if k.hp <= 0:
                k.hp = k.hp_max
                self.quedas += 1

    # ================================================================ ordem de desenho

    def montar_fila(self) -> np.ndarray:
        """Os ids de tras para a frente: 0..n-1 cenario, 100+i inimigos, 200 cavaleiro, 201
        o arco do corte (camada 1: na frente do cavaleiro), 300+i efeitos."""
        f, p = self.fila, self.proj
        f.limpar()
        for i, (_, x, y, _) in enumerate(self.cenario):
            f.adicionar(i, p.profundidade(x, y), 0.0, 0)
        for i, e in enumerate(self.inimigos):
            if e.vivo:
                f.adicionar(100 + i, p.profundidade(e.x, e.y), e.z, 0)
        k = self.cavaleiro
        prof = p.profundidade(k.x, k.y)
        f.adicionar(200, prof, k.z, 0)
        if k.estado == "ataque" and arte.ATAQUE.indice(k.t) >= arte.QUADRO_DO_CORTE:
            f.adicionar(201, prof, k.z, 1)
        for i, ef in enumerate(self.efeitos):
            f.adicionar(300 + i, p.profundidade(ef.x, ef.y), ef.z, 2)
        return f.ordenar()

    def _sprite_cavaleiro(self) -> SpriteAscii:
        k = self.cavaleiro
        if k.estado == "ataque":
            return arte.ATAQUE.quadro(k.t)
        if k.z > 0.0:
            return arte.PULO
        if k.estado == "andando":
            return arte.ANDANDO.quadro(k.t)
        return arte.PARADO.quadro(self.relogio)

    def _sprite_inimigo(self, e: Ator) -> SpriteAscii:
        if e.tipo == "morcego":
            return arte.MORCEGO.quadro(self.relogio + e.fase)
        if e.z > 0.0:
            return arte.GOSMA_NO_AR
        return arte.GOSMA.quadro(self.relogio + e.espera)

    # ================================================================ render

    def render(self, world: World, renderer: IRenderer) -> None:
        querer_filtro = self.modo_render == "filtro"
        if querer_filtro != self._filtro_ligado:
            renderer.set_ascii_filter(self.filtro if querer_filtro else None)
            self._filtro_ligado = querer_filtro
        ordem = self.montar_fila()
        if self.modo_render == "ascii":
            self._render_ascii(renderer, ordem)
        else:
            self._render_normal(renderer, ordem)
        self._hud(renderer)

    def on_exit(self, world: World, renderer: IRenderer) -> None:
        if self._filtro_ligado:
            renderer.set_ascii_filter(None)
            self._filtro_ligado = False

    # ---------------------------------------------------------------- ASCII nativo

    def _preparar_tela(self) -> TelaAscii:
        cw, ch = self._celula
        if self._tela is None:
            self._tela = TelaAscii(max(1, self.largura // cw), max(1, self.altura_jogo // ch), fundo=FUNDO)
        t = self._tela
        if self._fundo_chao is None:
            # o xadrez do chao: o centro de cada celula volta para o mundo (mundo_de_lote)
            cols, rows = t.colunas, t.linhas
            sx = (np.tile(np.arange(cols), rows) + 0.5) * cw
            sy = (np.repeat(np.arange(rows), cols) + 0.5) * ch
            wx, wy = np.zeros(sx.shape), np.zeros(sy.shape)
            self.proj.mundo_de_lote(sx, sy, wx, wy)
            dentro = (wx >= 0) & (wx <= ARENA[0]) & (wy >= 0) & (wy <= ARENA[1])
            xadrez = ((np.floor(wx / 80.0) + np.floor(wy / 80.0)) % 2) == 0
            fundo = np.empty((rows * cols, 3), np.uint8)
            fundo[:] = FUNDO
            fundo[dentro & xadrez] = CHAO_A
            fundo[dentro & ~xadrez] = CHAO_B
            self._fundo_chao = fundo.reshape(rows, cols, 3)
        return t

    def _render_ascii(self, r: IRenderer, ordem: np.ndarray) -> None:
        t = self._preparar_tela()
        cw, ch = self._celula
        p = self.proj
        t.limpar()
        np.copyto(t.fundos, self._fundo_chao)
        # marcas do chao
        p.tela_de_lote(self._gx, self._gy, None, self._gsx, self._gsy)
        for i in range(self._gx.shape[0]):
            t.por(int(self._gsx[i] // cw), int(self._gsy[i] // ch), self._gch[i], self._gcor[i])
        # borda da arena
        cantos = [p.tela_de(x, y) for x, y in ((0, 0), (ARENA[0], 0), ARENA, (0, ARENA[1]))]
        for a, b in zip(cantos, cantos[1:] + cantos[:1]):
            t.linha(int(a[0] // cw), int(a[1] // ch), int(b[0] // cw), int(b[1] // ch), None, BORDA)
        # sombras no chao (antes de tudo que fica em pe)
        for a in self._atores_vivos():
            sx, sy, rx, ry, forca = p.sombra(a.x, a.y, a.z, a.raio * 1.2)
            ch_sombra = ":" if forca > 0.7 else "."
            t.elipse(int(sx // cw), int(sy // ch), max(rx / cw, 1.0), ry / ch, ch_sombra, (34, 50, 36),
                     fundo=(8, 15, 10))
        # tudo em pe, de tras para a frente
        for ident in ordem.tolist():
            spr, x, y, z, esp, cor = self._o_que_desenhar(int(ident))
            if spr is None:
                continue
            sx, sy = p.tela_de(x, y, z)
            t.sprite(spr, int(sx // cw), int(sy // ch), espelhado=esp, cor=cor)
        r.draw_ascii(t, 0, 0, FONTE)

    def _atores_vivos(self):
        yield self.cavaleiro
        for e in self.inimigos:
            if e.vivo:
                yield e

    def _o_que_desenhar(self, ident: int):
        """(sprite, x, y, z, espelhado, cor) do id da fila."""
        if ident < 100:
            tipo, x, y, _ = self.cenario[ident]
            return (arte.PILAR if tipo == "pilar" else arte.ARVORE), x, y, 0.0, False, None
        if ident < 200:
            e = self.inimigos[ident - 100]
            cor = BRANCO if e.piscar > 0.0 else None
            return self._sprite_inimigo(e), e.x, e.y, e.z, e.olhando < 0, cor
        k = self.cavaleiro
        if ident == 200:
            cor = BRANCO if k.piscar > 0.0 else None
            if k.invencivel > 0.0 and int(self.relogio * 16) % 2 == 0 and k.piscar <= 0.0:
                return None, 0, 0, 0, False, None  # pisca enquanto invencivel
            return self._sprite_cavaleiro(), k.x, k.y, k.z, k.olhando < 0, cor
        if ident == 201:
            return arte.CORTE, k.x, k.y, k.z, k.olhando < 0, None
        ef = self.efeitos[ident - 300]
        return arte.PUF.quadro(ef.t), ef.x, ef.y, ef.z, False, None

    # ---------------------------------------------------------------- render normal

    def _render_normal(self, r: IRenderer, ordem: np.ndarray) -> None:
        p = self.proj
        r.draw_ui_rect(0, 0, self.largura, self.altura_jogo, (*FUNDO, 255))
        # o chao: os ladrilhos do xadrez como poligonos projetados
        passo = 80.0
        nx, ny = int(ARENA[0] // passo), int(ARENA[1] // passo)
        for j in range(ny):
            for i in range(nx):
                x0, y0 = i * passo, j * passo
                cor = (38, 70, 42, 255) if (i + j) % 2 == 0 else (46, 84, 50, 255)
                r.draw_ui_polygon([p.tela_de(x0, y0), p.tela_de(x0 + passo, y0),
                                   p.tela_de(x0 + passo, y0 + passo), p.tela_de(x0, y0 + passo)], cor)
        p.tela_de_lote(self._gx, self._gy, None, self._gsx, self._gsy)
        for i in range(self._gx.shape[0]):
            sx, sy = float(self._gsx[i]), float(self._gsy[i])
            c = self._gcor[i]
            r.draw_ui_line(sx, sy, sx + 1, sy - 5, (c[0] + 30, c[1] + 40, c[2] + 20, 255), 1)
        cantos = [p.tela_de(x, y) for x, y in ((0, 0), (ARENA[0], 0), ARENA, (0, ARENA[1]))]
        r.draw_ui_polygon(cantos, (*BORDA, 255), 2)
        for a in self._atores_vivos():
            _, _, _, _, forca = p.sombra(a.x, a.y, a.z, a.raio * 1.2)
            p.pontos_elipse_chao(a.x, a.y, a.raio * 1.2 * forca, out=self._elipse)
            r.draw_ui_polygon(self._elipse, (0, 0, 0, int(140 * forca)))
        for ident in ordem.tolist():
            self._desenhar_vetor(r, int(ident))

    def _desenhar_vetor(self, r: IRenderer, ident: int) -> None:
        p = self.proj
        z = p.zoom
        if ident < 100:
            tipo, x, y, raio = self.cenario[ident]
            bx, by = p.tela_de(x, y)
            if p.modo == DE_CIMA:  # de cima a altura some: o pilar e a copa vistos do alto
                if tipo == "pilar":
                    r.draw_ui_circle(bx, by, raio * 1.3 * z, (130, 126, 116, 255))
                    r.draw_ui_circle(bx - 3 * z, by - 3 * z, raio * z, (182, 178, 164, 255))
                else:
                    for ox, oy, rr, cor in ((0, 0, 46, (40, 110, 46)), (-10, -8, 30, (64, 150, 64)),
                                            (8, -14, 18, (84, 172, 80))):
                        r.draw_ui_circle(bx + ox * z, by + oy * z, rr * z, (*cor, 255))
                return
            if tipo == "pilar":
                tx, ty = p.tela_de(x, y, ALTURA_PILAR)
                w = raio * z
                r.draw_ui_rect(bx - w, ty, w * 2, by - ty, (150, 146, 134, 255))
                r.draw_ui_rect(bx - w, ty, w * 0.6, by - ty, (182, 178, 164, 255))
                r.draw_ui_rect(bx + w * 0.55, ty, w * 0.45, by - ty, (112, 108, 98, 255))
                r.draw_ui_rect(bx - w * 1.3, ty - 10 * z, w * 2.6, 12 * z, (190, 186, 172, 255))
                r.draw_ui_rect(bx - w * 1.3, by - 10 * z, w * 2.6, 12 * z, (130, 126, 116, 255))
            else:
                tx, ty = p.tela_de(x, y, ALTURA_ARVORE * 0.55)
                r.draw_ui_rect(bx - 6 * z, ty, 12 * z, by - ty, (120, 82, 48, 255))
                cx, cy = p.tela_de(x, y, ALTURA_ARVORE)
                for ox, oy, rr, cor in ((0, 10, 46, (40, 110, 46)), (-20, 0, 32, (52, 132, 56)),
                                        (18, -6, 30, (64, 150, 64)), (0, -24, 26, (84, 172, 80))):
                    r.draw_ui_circle(cx + ox * z, cy + oy * z, rr * z, (*cor, 255))
            return
        if ident < 200:
            e = self.inimigos[ident - 100]
            sx, sy = p.tela_de(e.x, e.y, e.z)
            branco = e.piscar > 0.0
            if e.tipo == "gosma":
                estica = 1.25 if e.z > 0 else (0.85 + 0.1 * math.sin(self.relogio * 6 + e.espera))
                rx, ry = 24.0 / estica, 20.0 * estica
                cor = (240, 240, 240, 255) if branco else (90, 200, 90, 255)
                pts = [(sx + math.cos(a) * rx, sy - ry + math.sin(a) * ry) for a in
                       (i * math.pi / 9 for i in range(18))]
                r.draw_ui_polygon(pts, cor)
                for lado in (-1, 1):
                    r.draw_ui_circle(sx + lado * 7 + e.olhando * 4, sy - ry * 1.1, 4, (250, 250, 240, 255))
                    r.draw_ui_circle(sx + lado * 7 + e.olhando * 5, sy - ry * 1.1, 2, (20, 30, 20, 255))
            else:
                cor = (240, 240, 240, 255) if branco else (170, 110, 220, 255)
                bate = math.sin(self.relogio * 18 + e.fase) * 12
                for lado in (-1, 1):
                    r.draw_ui_polygon([(sx, sy - 8), (sx + lado * 30, sy - 18 - bate),
                                       (sx + lado * 22, sy - 2), (sx + lado * 10, sy - 4)], cor)
                r.draw_ui_circle(sx, sy - 8, 9, cor)
                r.draw_ui_circle(sx + e.olhando * 3, sy - 10, 2.5, (255, 80, 80, 255))
            return
        k = self.cavaleiro
        if ident == 200:
            if k.invencivel > 0.0 and int(self.relogio * 16) % 2 == 0 and k.piscar <= 0.0:
                return
            self._cavaleiro_vetor(r, k)
            return
        if ident == 201:
            sx, sy = p.tela_de(k.x, k.y, k.z)
            ini = -0.9 if k.olhando > 0 else math.pi - 0.9
            r.draw_ui_arc(sx + k.olhando * 34, sy - 40, 46, ini, ini + 1.8, (170, 230, 255, 255), 4)
            return
        ef = self.efeitos[ident - 300]
        sx, sy = p.tela_de(ef.x, ef.y, ef.z)
        rr = 8 + ef.t * 120
        alfa = max(0, int(255 * (1 - ef.t / arte.PUF.duracao)))
        r.draw_ui_circle(sx, sy - 20, rr, (255, 236, 160, alfa), 3)

    def _cavaleiro_vetor(self, r: IRenderer, k: Ator) -> None:
        sx, sy = self.proj.tela_de(k.x, k.y, k.z)
        o = k.olhando
        branco = k.piscar > 0.0
        aco = (240, 240, 240, 255) if branco else (196, 204, 220, 255)
        escuro = (120, 126, 142, 255)
        passo = math.sin(k.t * 18) * 6 if k.estado == "andando" and k.z <= 0 else 0.0
        if k.z > 0:
            r.draw_ui_line(sx - 6, sy - 26, sx - 10, sy - 10, escuro, 5)
            r.draw_ui_line(sx + 6, sy - 26, sx + 10, sy - 10, escuro, 5)
        else:
            r.draw_ui_line(sx - 5, sy - 26, sx - 6 + passo, sy, escuro, 5)
            r.draw_ui_line(sx + 5, sy - 26, sx + 6 - passo, sy, escuro, 5)
        r.draw_ui_rect(sx - 12, sy - 58, 24, 34, aco)
        r.draw_ui_rect(sx - 6, sy - 54, 12, 28, (200, 50, 60, 255))
        r.draw_ui_circle(sx, sy - 68, 11, aco)
        r.draw_ui_rect(sx + o * 2 - 1, sy - 71, 8 * o if o > 0 else 8, 3, (120, 220, 255, 255))
        r.draw_ui_line(sx, sy - 79, sx - o * 6, sy - 92, (238, 196, 70, 255), 4)
        r.draw_ui_circle(sx - o * 15, sy - 42, 11, (160, 104, 52, 255))
        # a espada pela fase do golpe
        mao_x, mao_y = sx + o * 14, sy - 42
        if k.estado == "ataque":
            q = arte.ATAQUE.indice(k.t)
            ang = (-1.45, -0.05, 0.75)[q]
        else:
            ang = 1.25
        dx, dy = math.cos(ang) * 40 * o, math.sin(ang) * 40
        r.draw_ui_line(mao_x, mao_y, mao_x + dx, mao_y + dy, (240, 246, 255, 255), 3)
        r.draw_ui_line(mao_x - dy * 0.2 * o, mao_y + dx * 0.2 * o, mao_x + dy * 0.2 * o, mao_y - dx * 0.2 * o,
                       (210, 170, 90, 255), 3)

    # ---------------------------------------------------------------- HUD

    def _hud(self, r: IRenderer) -> None:
        y = self.altura_jogo
        r.draw_ui_rect(0, y, self.largura, HUD_PX, (0, 0, 0, 255))
        vida = "<3 " * self.cavaleiro.hp
        texto = (f"F: {NOMES_RENDER[self.modo_render]}   P: {NOMES_PROJECAO[self.proj.modo]}   "
                 f"setas/WASD andar  espaco atacar  J pular  ESC sai   abates {self.abates}")
        r.draw_text(10, y + 8, texto, 13, (200, 200, 190, 255))
        r.draw_text(self.largura - 10, y + 8, vida, 13, (230, 70, 80, 255), anchor="topright")
