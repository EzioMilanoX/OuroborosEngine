"""Laco principal do jogo: input -> simulacao -> renderizacao, sem logica de gameplay propria."""
from __future__ import annotations

import time

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
        """Coleta as views SoA de `transform`+`sprite` e repassa a `IRenderer.draw_batch` em uma unica chamada."""
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
        self._renderer.end_frame()
