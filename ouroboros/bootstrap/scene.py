# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contrato de cena (IScene) e a cena padrao que embrulha o World.step atual (GameplayScene)."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ouroboros.core.memory.component_pool import intersect_entity_indices
from ouroboros.core.world import World
from ouroboros.interfaces.renderer import IRenderer

import numpy as np

_EMPTY_XY = np.zeros((0, 2), dtype=np.float32)
_EMPTY_F32 = np.zeros(0, dtype=np.float32)
_EMPTY_U32 = np.zeros(0, dtype=np.uint32)
_EMPTY_RGBA = np.zeros((0, 4), dtype=np.uint8)
_EMPTY_I16 = np.zeros(0, dtype=np.int16)
_EMPTY_KINDS = np.zeros(0, dtype=np.uint32)


class IScene(ABC):
    """
    Contrato de uma cena empilhavel em `GameLoop` (ROADMAP M2). Vive em
    `ouroboros.bootstrap` -- nao em `ouroboros.core`, que nunca importa
    `ouroboros.interfaces` (regra de camadas verificada pelo
    import-linter), e nao em `ouroboros.interfaces`, que nao conhece
    `World`/ECS -- mesma camada de `GameLoop`/`CompositionRoot`, que ja
    importam os dois.

    `on_enter`/`on_exit` sao chamados SIMETRICAMENTE nos dois lados de
    uma transicao: `GameLoop.push_scene` chama `on_exit` da cena que
    perde o topo (nao removida da pilha, so encoberta) e `on_enter` da
    nova cena no topo; `GameLoop.pop_scene` chama `on_exit` da cena
    removida e `on_enter` da cena revelada por baixo. Uma cena pode
    legitimamente ter `on_enter`/`on_exit` chamados MAIS DE UMA VEZ ao
    longo de sua vida (empilhada, encoberta, revelada de novo) -- nunca
    assuma "chamado exatamente uma vez". Podem rodar de forma SINCRONA,
    dentro da propria chamada de `update()` que disparou a transicao
    (mesmo padrao ja usado por `QuitOnActionSystem.stop()`, que chama
    `GameLoop.stop()` de dentro do proprio `update()` de um `ISystem`).
    """

    def on_enter(self, world: World, renderer: IRenderer) -> None:
        """Chamado quando esta cena assume o topo da pilha (empilhada ou revelada por um pop). Default: no-op."""

    def on_exit(self, world: World, renderer: IRenderer) -> None:
        """Chamado quando esta cena perde o topo da pilha (encoberta por um push ou removida por um pop). Default: no-op."""

    @abstractmethod
    def update(self, world: World, delta_time: float) -> None:
        """Logica por frame desta cena, chamada apenas enquanto ela estiver no topo da pilha."""
        ...

    @abstractmethod
    def render(self, world: World, renderer: IRenderer) -> None:
        """Desenho por frame desta cena, chamado apenas enquanto ela estiver no topo da pilha.
        `renderer.begin_frame()`/`end_frame()` sao responsabilidade de `GameLoop`, nao da cena."""
        ...


class GameplayScene(IScene):
    """
    Cena padrao, auto-criada por `GameLoop.__init__` como a base
    (nunca removivel) da pilha -- `update` chama `world.step(delta_time)`;
    `render` e o corpo que `GameLoop._render_frame()` executava inline
    antes do SceneStack existir (gather `transform`+`sprite` ->
    `draw_batch`, gather `fx` -> `draw_effects`), MOVIDO pra ca, nao
    duplicado.

    Stateless (nao guarda `world`/`renderer` -- recebe como parametro em
    cada chamada), entao uma UNICA instancia e reutilizavel: uma cena
    que cubra o jogo (ex.: uma tela de pausa) pode chamar
    `gameplay_scene.render(world, renderer)` pra redesenhar o ultimo
    frame congelado por baixo do proprio overlay, sem duplicar a logica
    de gather+draw.
    """

    def update(self, world: World, delta_time: float) -> None:
        world.step(delta_time)

    def render(self, world: World, renderer: IRenderer) -> None:
        transform_pool = world.get_pool("transform")
        sprite_pool = world.get_pool("sprite")
        entity_indices = intersect_entity_indices(transform_pool, sprite_pool)
        count = int(entity_indices.shape[0])

        if count == 0:
            renderer.draw_batch(_EMPTY_XY, _EMPTY_F32, _EMPTY_XY, _EMPTY_U32, _EMPTY_RGBA, _EMPTY_I16, 0)
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

            renderer.draw_batch(positions_xy, rotations_rad, scales_xy, texture_ids, tint_rgba, layer_z, count)

        fx_pool = world.get_pool("fx")
        fx_count = fx_pool.count
        if fx_count == 0:
            renderer.draw_effects(_EMPTY_KINDS, _EMPTY_XY, _EMPTY_XY, _EMPTY_RGBA, 0)
        else:
            fx_view = fx_pool.active_view()
            fx_kinds = fx_view["kind"]
            fx_positions_xy = np.stack([fx_view["position_x"], fx_view["position_y"]], axis=1)
            fx_sizes_wh = np.stack([fx_view["width"], fx_view["height"]], axis=1)
            fx_tint_rgba = np.stack(
                [fx_view["tint_r"], fx_view["tint_g"], fx_view["tint_b"], fx_view["tint_a"]], axis=1
            )
            renderer.draw_effects(fx_kinds, fx_positions_xy, fx_sizes_wh, fx_tint_rgba, fx_count)
