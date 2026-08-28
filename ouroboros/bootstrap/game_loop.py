# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Laco principal do jogo: input -> simulacao -> renderizacao, sem logica de gameplay propria."""
from __future__ import annotations

import time
from typing import Callable, List, Optional

from ouroboros.bootstrap.scene import GameplayScene, IScene
from ouroboros.core.world import World
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer


class GameLoop:
    """
    Laco de frame que conecta `IInputProvider`, `World` e `IRenderer` --
    a unica classe que "conhece" os tres ao mesmo tempo fora de
    `CompositionRoot`. Nao contem regra de gameplay: isso vive nos
    `ISystem` registrados no `World` (via a `GameplayScene` padrao) ou
    em `IScene`s adicionais empilhadas por um produto (ROADMAP M2).
    """

    def __init__(
        self,
        world: World,
        renderer: IRenderer,
        input_provider: IInputProvider,
        audio_engine: IAudioEngine,
        target_fps: int = 60,
    ) -> None:
        """Guarda as dependencias ja construidas por `CompositionRoot` e empilha
        uma `GameplayScene` como base da pilha de cenas -- a pilha nunca fica vazia."""
        self._world = world
        self._renderer = renderer
        self._input_provider = input_provider
        self._audio_engine = audio_engine
        self._target_fps = target_fps
        self._running = False
        self._on_draw_ui: Optional[Callable[[IRenderer], None]] = None
        self._scenes: List[IScene] = [GameplayScene()]

    @property
    def world(self) -> World:
        """Acesso somente-leitura ao `World` montado por `CompositionRoot`, para um script de
        composicao de produto registrar arquetipos/sistemas por cima antes de `run()`."""
        return self._world

    @property
    def renderer(self) -> IRenderer:
        """Acesso somente-leitura ao `IRenderer` montado por `CompositionRoot`."""
        return self._renderer

    @property
    def input_provider(self) -> IInputProvider:
        """Acesso somente-leitura ao `IInputProvider` montado por `CompositionRoot`."""
        return self._input_provider

    @property
    def audio_engine(self) -> IAudioEngine:
        """Acesso somente-leitura ao `IAudioEngine` montado por `CompositionRoot`."""
        return self._audio_engine

    @property
    def current_scene(self) -> IScene:
        """Cena atualmente no topo da pilha (a `GameplayScene` padrao, se nada mais foi empilhado)."""
        return self._scenes[-1]

    def push_scene(self, scene: IScene) -> None:
        """
        Empilha `scene` como a nova cena ativa (ROADMAP M2): chama
        `on_exit` da cena que estava no topo (encoberta, nao removida)
        e `on_enter` da nova cena. A partir daqui, `run()` chama
        `update()`/`render()` de `scene`, nao mais da anterior.
        """
        if self._scenes:
            self._scenes[-1].on_exit(self._world, self._renderer)
        self._scenes.append(scene)
        scene.on_enter(self._world, self._renderer)

    def pop_scene(self) -> IScene:
        """
        Remove a cena no topo da pilha e revela a anterior: chama
        `on_exit` da cena removida e `on_enter` da cena revelada.
        Levanta `RuntimeError` se so restar a `GameplayScene` base --
        ela nunca pode ser removida (a pilha nao pode ficar vazia).
        """
        if len(self._scenes) <= 1:
            raise RuntimeError("GameLoop.pop_scene: nao e possivel remover a cena base (pilha ficaria vazia)")
        popped = self._scenes.pop()
        popped.on_exit(self._world, self._renderer)
        self._scenes[-1].on_enter(self._world, self._renderer)
        return popped

    def set_on_draw_ui(self, callback: Optional[Callable[[IRenderer], None]]) -> None:
        """
        Registra (ou remove, passando `None`) um callback de HUD/UI chamado uma vez por
        frame, depois do `render()` da cena ativa e antes de `end_frame()`. GLOBAL --
        roda independente de qual cena esta no topo (decisao consciente do SceneStack:
        um HUD de score continuar visivel sob uma cena de pausa, por exemplo, e aceitavel
        e evita a superficie nova de callbacks por-cena).

        Mutacao pos-construcao via metodo explicito (mesmo idioma de `stop()`), nao um
        parametro de construtor: o callback tipicamente fecha sobre objetos (ex.: um
        sistema de julgamento) que so existem depois que o script de composicao do
        produto registra seus proprios sistemas em cima do `GameLoop` ja construido por
        `CompositionRoot.build()` -- construir o callback ANTES disso nao seria possivel.

        `GameLoop` continua sem saber nada sobre o conteudo do callback (nenhuma logica
        de gameplay aqui) -- so invoca o que foi passado.
        """
        self._on_draw_ui = callback

    def run(self) -> None:
        """
        Laco principal: enquanto nao `input_provider.wants_quit()`,
        chama `input_provider.poll()`, `update()` da cena no topo da
        pilha (ROADMAP M2 -- a `GameplayScene` padrao so chama
        `world.step(delta_time)`, mesmo comportamento de antes do
        SceneStack existir) e `_render_frame()`. `delta_time` nunca e
        usado para decidir eventos sincronizados a audio -- isso e
        responsabilidade dos Systems que consultam `IAudioClock`
        diretamente (ver Pilar 4).

        Timing via `time.perf_counter()` (stdlib) -- nunca
        `pygame.time.Clock`, para que `ouroboros.bootstrap` continue sem
        importar `pygame` diretamente (Regra 2 da Constituicao).
        """
        self._running = True
        min_frame_seconds = 1.0 / self._target_fps if self._target_fps > 0 else 0.0
        last_time = time.perf_counter()

        while self._running and not self._input_provider.wants_quit():
            self._input_provider.poll()

            now = time.perf_counter()
            delta_time = now - last_time
            last_time = now

            self._scenes[-1].update(self._world, delta_time)
            self._render_frame()

            elapsed = time.perf_counter() - now
            if min_frame_seconds > elapsed:
                time.sleep(min_frame_seconds - elapsed)

    def stop(self) -> None:
        """Sinaliza para `run()` encerrar o laco no inicio do proximo frame."""
        self._running = False

    def _render_frame(self) -> None:
        """`begin_frame()` -> `render()` da cena no topo da pilha -> callback global de
        UI (se registrado) -> `end_frame()`. A logica de desenho em si (gather de pools,
        `draw_batch`/`draw_effects`) vive em `GameplayScene.render` (ou em qualquer outra
        `IScene` empilhada), nao aqui."""
        self._renderer.begin_frame()
        self._scenes[-1].render(self._world, self._renderer)
        if self._on_draw_ui is not None:
            self._on_draw_ui(self._renderer)
        self._renderer.end_frame()
