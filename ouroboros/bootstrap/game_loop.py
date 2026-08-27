# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Laco principal do jogo: input -> simulacao -> renderizacao, sem logica de gameplay propria."""
from __future__ import annotations

import time
from typing import Callable, Optional

import numpy as np

from ouroboros.core.memory.component_pool import intersect_entity_indices
from ouroboros.core.world import World
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.renderer import IRenderer

_EMPTY_XY = np.zeros((0, 2), dtype=np.float32)
_EMPTY_F32 = np.zeros(0, dtype=np.float32)
_EMPTY_U32 = np.zeros(0, dtype=np.uint32)
_EMPTY_RGBA = np.zeros((0, 4), dtype=np.uint8)
_EMPTY_I16 = np.zeros(0, dtype=np.int16)
_EMPTY_KINDS = np.zeros(0, dtype=np.uint32)


class GameLoop:
    """
    Laco de frame que conecta `IInputProvider`, `World` e `IRenderer` --
    a unica classe que "conhece" os tres ao mesmo tempo fora de
    `CompositionRoot`. Nao contem regra de gameplay: isso vive nos
    `ISystem` registrados no `World`.
    """

    def __init__(
        self,
        world: World,
        renderer: IRenderer,
        input_provider: IInputProvider,
        audio_engine: IAudioEngine,
        target_fps: int = 60,
    ) -> None:
        """Guarda as dependencias ja construidas por `CompositionRoot`."""
        self._world = world
        self._renderer = renderer
        self._input_provider = input_provider
        self._audio_engine = audio_engine
        self._target_fps = target_fps
        self._running = False
        self._on_draw_ui: Optional[Callable[[IRenderer], None]] = None

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

    def set_on_draw_ui(self, callback: Optional[Callable[[IRenderer], None]]) -> None:
        """
        Registra (ou remove, passando `None`) um callback de HUD/UI chamado uma vez por
        frame, depois de `draw_batch(...)` e antes de `end_frame()`.

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
        chama `input_provider.poll()`, `world.step(delta_time)` e
        `renderer.begin_frame()/draw_batch(...)/end_frame()`, lendo os
        arrays SoA relevantes das pools do `World` para repassar a
        `draw_batch`. `delta_time` nunca e usado para decidir eventos
        sincronizados a audio -- isso e responsabilidade dos Systems
        que consultam `IAudioClock` diretamente (ver Pilar 4).

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

            self._world.step(delta_time)
            self._render_frame()

            elapsed = time.perf_counter() - now
            if min_frame_seconds > elapsed:
                time.sleep(min_frame_seconds - elapsed)

    def stop(self) -> None:
        """Sinaliza para `run()` encerrar o laco no inicio do proximo frame."""
        self._running = False

    def _render_frame(self) -> None:
        """Coleta as views SoA de `transform`+`sprite` e repassa a `IRenderer.draw_batch` em uma
        unica chamada, depois faz o mesmo para a pool `fx` (ROADMAP M1.3) via `draw_effects` --
        sempre existe (criada por `COMPONENT_SCHEMAS`), entao nunca precisa de `has_pool`; se
        nenhum produto a usa, `count` fica 0 pra sempre (custo desprezivel)."""
        transform_pool = self._world.get_pool("transform")
        sprite_pool = self._world.get_pool("sprite")
        entity_indices = intersect_entity_indices(transform_pool, sprite_pool)
        count = int(entity_indices.shape[0])

        self._renderer.begin_frame()
        if count == 0:
            self._renderer.draw_batch(_EMPTY_XY, _EMPTY_F32, _EMPTY_XY, _EMPTY_U32, _EMPTY_RGBA, _EMPTY_I16, 0)
        else:
            t_rows = transform_pool.dense_rows_of(entity_indices)
            s_rows = sprite_pool.dense_rows_of(entity_indices)
            t_view = transform_pool.active_view()
            s_view = sprite_pool.active_view()

            positions_xy = np.stack([t_view["position_x"][t_rows], t_view["position_y"][t_rows]], axis=1)
            rotations_rad = t_view["rotation_rad"][t_rows]
            scales_xy = np.stack([t_view["scale_x"][t_rows], t_view["scale_y"][t_rows]], axis=1)
            texture_ids = s_view["texture_id"][s_rows]
            tint_rgba = np.stack(
                [s_view["tint_r"][s_rows], s_view["tint_g"][s_rows], s_view["tint_b"][s_rows], s_view["tint_a"][s_rows]],
                axis=1,
            )
            layer_z = s_view["layer_z"][s_rows]

            self._renderer.draw_batch(positions_xy, rotations_rad, scales_xy, texture_ids, tint_rgba, layer_z, count)

        fx_pool = self._world.get_pool("fx")
        fx_count = fx_pool.count
        if fx_count == 0:
            self._renderer.draw_effects(_EMPTY_KINDS, _EMPTY_XY, _EMPTY_XY, _EMPTY_RGBA, 0)
        else:
            fx_view = fx_pool.active_view()
            fx_kinds = fx_view["kind"]
            fx_positions_xy = np.stack([fx_view["position_x"], fx_view["position_y"]], axis=1)
            fx_sizes_wh = np.stack([fx_view["width"], fx_view["height"]], axis=1)
            fx_tint_rgba = np.stack(
                [fx_view["tint_r"], fx_view["tint_g"], fx_view["tint_b"], fx_view["tint_a"]], axis=1
            )
            self._renderer.draw_effects(fx_kinds, fx_positions_xy, fx_sizes_wh, fx_tint_rgba, fx_count)

        if self._on_draw_ui is not None:
            self._on_draw_ui(self._renderer)
        self._renderer.end_frame()
