# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Empilha a EndScene de derrota/vitoria quando DamageOnCollisionSystem sinaliza fim de jogo."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ouroboros.bootstrap.game_loop import GameLoop
from ouroboros.core.systems.base_system import ISystem
from ouroboros.roguelite.systems.damage_system import DamageOnCollisionSystem

if TYPE_CHECKING:
    from ouroboros.core.world import World


class GameOverOnDeathSystem(ISystem):
    """
    Mesmo molde de `QuitOnActionSystem`/`PauseOnActionSystem` (Jogo
    Musical): segura `game_loop` + a instancia de
    `DamageOnCollisionSystem` que observa. A cada `update()`, se
    `damage_system.player_is_dead` ou `damage_system.enemies_remaining
    == 0`, empilha a cena de fim de jogo correspondente.

    SEM guarda de "ja disparou": o proprio ato de empilhar uma cena ja
    impede `world.step()` (logo este sistema) de rodar de novo -- mesma
    garantia que `PauseOnActionSystem` ja documenta e usa.
    """

    def __init__(
        self,
        game_loop: GameLoop,
        damage_system: DamageOnCollisionSystem,
        defeat_scene_factory,
        victory_scene_factory,
    ) -> None:
        self._game_loop = game_loop
        self._damage_system = damage_system
        self._defeat_scene_factory = defeat_scene_factory
        self._victory_scene_factory = victory_scene_factory

    def update(self, world: "World", delta_time: float) -> None:
        del world, delta_time
        if self._damage_system.player_is_dead:
            self._game_loop.push_scene(self._defeat_scene_factory())
        elif self._damage_system.enemies_remaining == 0:
            self._game_loop.push_scene(self._victory_scene_factory())
