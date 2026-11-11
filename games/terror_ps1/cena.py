# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""A cena da demo: a noite do torii em primeira pessoa, desenhada pelo `IRenderer3D`
(ROADMAP M21) com o estilo PS1, o HUD por cima com as primitivas 2D de sempre, e o som:
passos, o clique da lanterna, o zumbido do lugar, o galho que o vulto quebra (do lado em
que ele esta) e o coracao, que acelera quando ele chega perto."""
from __future__ import annotations

import dataclasses
import math
import random
import tempfile
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from ouroboros.bootstrap.scene import IScene
from ouroboros.core.world import World
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer
from ouroboros.interfaces.renderer3d import (
    COR_AFIM,
    Estilo3D,
    Iluminacao3D,
    Luz3D,
    translacao_e_giro_y,
    triangulos_para_arrays,
)

from games.terror_ps1 import regras, sons
from games.vitrine_estilos import arte, tres_d

NEVOA = (5 / 255, 5 / 255, 8 / 255)
ESTILO_PS1 = Estilo3D(resolucao=(320, 180), tremor=True, modo_cor=COR_AFIM, fundo=NEVOA, neblina_cor=NEVOA,
                      neblina=(6.0, 20.0), bits_cor=5, pontilhado=True, grao=0.035, vinheta=0.8)
VELA = Luz3D("ponto", (1.1, 1.0, -1.0), (1.5, 0.3, 0.15), 2.6)
LUA = Luz3D("dir", (0.3, 0.8, -0.5), (0.07, 0.08, 0.13))
BRANCO = (230, 226, 218, 255)
AJUDA = "mouse olha   WASD anda   F lanterna   F11 tela cheia   ESC sai"
POEIRA = 220  # graos de poeira no ar: so aparecem dentro do feixe
CAIXA_POEIRA = np.array([7.0, 3.0, 7.0])


class TerrorScene(IScene):
    def __init__(self, entrada: IInputProvider, renderer: IRenderer, audio: Optional[IAudioEngine] = None,
                 ao_sair: Optional[Callable[[], None]] = None, pasta_sons: Optional[Path] = None) -> None:
        self.entrada = entrada
        self.renderer = renderer
        self.audio = audio
        self.ao_sair = ao_sair
        self.estado = regras.Estado()
        self.obstaculos = tres_d.obstaculos_terror()
        self.r3d = renderer.renderer_3d()
        if self.r3d is None:
            raise RuntimeError('a demo de terror precisa do renderer "gl" (placa de video, ROADMAP M21)')
        self.cenario = self.r3d.criar_malha(*triangulos_para_arrays(tres_d.cena_terror_estatica(passo=0.5)))
        self.vulto = self.r3d.criar_malha(*triangulos_para_arrays(tres_d.vulto(0.0, 0.0)))
        self.espadachim = self.r3d.criar_malha(*self._espadachim(), dinamica=True)
        rng = np.random.default_rng(5)
        self._poeira_base = rng.uniform(0, 1, (POEIRA, 3)) * CAIXA_POEIRA
        self._poeira_vel = rng.uniform(-0.12, 0.12, (POEIRA, 3)) + (0.0, -0.04, 0.0)
        self._poeira_cores = np.full((POEIRA * 3, 3), (210.0, 204.0, 190.0))
        self.poeira = self.r3d.criar_malha(*self._poeira(), dinamica=True)
        self._fps, self._ultimo = 0.0, time.perf_counter()
        self._coracao = 0.0
        self._rng = random.Random(3)
        self._tela_cheia = False
        entrada.set_mouse_captured(True)
        if audio is not None:
            self._sons = sons.gerar(pasta_sons or Path(tempfile.gettempdir()) / "ouroboros_terror_ps1")
            for nome, caminho in self._sons.items():
                audio.load_sound(nome, str(caminho))
            audio.load_track("zumbido", str(self._sons["zumbido"]))
            audio.set_track_volume(0.55)
            audio.play_track("zumbido", loop=True)

    def _espadachim(self):
        f = arte.pose_t(self.estado.tempo / 2.0)  # o mesmo laco de 2 s da vitrine
        return triangulos_para_arrays(tres_d.espadachim(f, 2.7, -1.2, tres_d.PALETA_TERROR))

    def _poeira(self):
        s = self.estado
        centro = np.array([s.x, regras.ALTURA_OLHOS, s.z])
        p = (self._poeira_base + self._poeira_vel * s.tempo - centro + CAIXA_POEIRA / 2) % CAIXA_POEIRA
        p = p + centro - CAIXA_POEIRA / 2  # a caixa de poeira anda com o jogador
        tri = np.repeat(p, 3, axis=0) + np.tile([[0, 0.03, 0], [-0.025, -0.02, 0], [0.025, -0.02, 0]], (POEIRA, 1))
        return tri.astype(np.float32), self._poeira_cores

    # ------------------------------------------------------------ logica
    def update(self, world: World, delta_time: float) -> None:
        e = self.entrada
        if e.is_action_pressed("sair") and self.ao_sair is not None:
            e.set_mouse_captured(False)
            self.ao_sair()
            return
        if e.is_action_pressed("tela_cheia"):
            self._tela_cheia = not self._tela_cheia
            self.renderer.set_fullscreen(self._tela_cheia)

        def eixo(mais, menos):
            return float(e.is_action_held(mais)) - float(e.is_action_held(menos))

        regras.atualizar(self.estado, delta_time, eixo("frente", "tras"), eixo("direita", "esquerda"),
                         eixo("girar_dir", "girar_esq"), e.is_action_pressed("lanterna"),
                         olhar=e.get_mouse_delta(), obstaculos=self.obstaculos)
        self._sons_do_passo(delta_time)

    def _sons_do_passo(self, dt: float) -> None:
        a, s = self.audio, self.estado
        if a is None:
            return
        dist = math.hypot(s.x - s.vulto[0], s.z - s.vulto[1])
        for ev in s.eventos:
            if ev == "passo":
                a.play_one_shot("passo", 0.28 + 0.1 * self._rng.random())
            elif ev == "clique":
                a.play_one_shot("clique", 0.5)
            elif ev == "vulto":  # a pista justa: o som vem do lado em que ele esta
                a.play_spatial("galho", min(1.0, 2.5 / max(dist, 1.0)), regras.lado_do_vulto(s))
            elif ev == "pegou":
                a.play_one_shot("pegou", 0.9)
        intervalo = regras.batimento(s)
        self._coracao -= dt
        if intervalo and self._coracao <= 0 and s.pego <= 0:
            self._coracao = intervalo
            a.play_one_shot("batida", min(1.0, 0.25 + (9.0 - dist) / 9.0))

    # ------------------------------------------------------------ desenho
    def render(self, world: World, renderer: IRenderer) -> None:
        agora = time.perf_counter()
        self._fps += ((1 / max(agora - self._ultimo, 1e-6)) - self._fps) * 0.1
        self._ultimo = agora
        s, r = self.estado, self.r3d
        dist = math.hypot(s.x - s.vulto[0], s.z - s.vulto[1])
        perto = max(0.0, 1.0 - dist / 8.0)  # a imagem fica mais suja com ele perto
        r.definir_estilo(dataclasses.replace(ESTILO_PS1, grao=0.035 + 0.16 * perto ** 2))
        olhos = s.olhos()
        olhar = regras.direcao(s.giro, s.inclina)
        r.definir_camera(olhos, tuple(o + d for o, d in zip(olhos, olhar, strict=True)), 64.0, 0.05, 60.0)
        direita = (math.cos(s.giro), 0.0, math.sin(s.giro))
        origem = (olhos[0] + direita[0] * 0.25, olhos[1] - 0.2, olhos[2] + direita[2] * 0.25)  # na mao direita
        luzes = [LUA, VELA]
        forca = regras.forca_da_luz(s)
        if forca > 0:
            luzes.append(Luz3D("foco", origem, (3.9 * forca, 3.6 * forca, 3.1 * forca), 30.0, direcao=s.feixe,
                               cone=(math.cos(math.radians(23)), math.cos(math.radians(9)))))
        r.definir_iluminacao(Iluminacao3D(ceu=(0.06, 0.065, 0.09), solo=(0.015, 0.015, 0.018), luzes=tuple(luzes)))
        r.atualizar_malha(self.espadachim, *self._espadachim())
        r.atualizar_malha(self.poeira, *self._poeira())
        r.desenhar(self.cenario)
        r.desenhar(self.espadachim)
        vx, vz = s.vulto
        r.desenhar(self.vulto, translacao_e_giro_y(vx, 0.0, vz, math.atan2(s.x - vx, s.z - vz)))
        r.desenhar(self.poeira)
        self._hud(renderer)

    def _hud(self, r: IRenderer) -> None:
        s = self.estado
        w, h = r.get_viewport_size()
        r.draw_ui_rect(20, h - 30, 124, 12, (20, 20, 24, 200))
        cor = (220, 210, 150, 230) if s.pilha > 0.25 else (220, 80, 60, 230)
        r.draw_ui_rect(22, h - 28, 120 * s.pilha, 8, cor)
        r.draw_text(152, h - 33, "pilha" + ("" if s.acesa else "  (apagada: recarregando)"), 13, BRANCO)
        r.draw_text(w - 16, 12, f"{self._fps:4.0f} qps", 13, (120, 120, 120, 255), anchor="topright")
        if s.tempo < 9:
            alfa = int(255 * min(1.0, (9 - s.tempo) / 2))
            r.draw_text(w / 2, 14, AJUDA, 14, BRANCO[:3] + (alfa,), anchor="midtop")
            r.draw_text(w / 2, 34, "ele so anda quando voce nao esta olhando", 13, (190, 170, 160, alfa),
                        anchor="midtop")
        if s.pego > 0:
            r.draw_ui_rect(0, 0, w, h, (90, 0, 0, int(160 * min(1.0, s.pego))))
            r.draw_text(w / 2, h / 2 - 12, "ele chegou", 28, BRANCO, anchor="midtop")
