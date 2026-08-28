# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Dispara projeteis na direcao de mira do jogador, respeitando cooldown via ModifierStack."""
from __future__ import annotations

from typing import TYPE_CHECKING, Tuple

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.base_system import ISystem
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.roguelite.combat.schemas import EntityKind
from ouroboros.roguelite.modifiers.modifier_stack import ModifierStack

if TYPE_CHECKING:
    from ouroboros.core.world import World


class WeaponFireSystem(ISystem):
    """
    Ao pressionar `fire_action_name` (borda) com o cooldown expirado
    (temporizador REAL de `delta_time` -- este e um sistema comum de
    gameplay, nao Pilar 4/ritmico, entao nao ha regra de nunca usar
    `delta_time`), cria um projetil na posicao do jogador, com
    velocidade `facing * speed_attribute.final_value` (a pool `facing`,
    nao uma referencia direta a `PlayerMovementSystem` -- mesmo idioma
    de `NoteScrollSystem`/`JudgmentSystem` comunicando-se via pool).

    `range_attribute_index` do `WEAPON_DTYPE` (aqui chamado
    `speed_attribute_index`) na verdade guarda `projectile_speed` --
    peculiaridade de nomenclatura ja existente em `WeaponLoader`,
    consumida como esta, nao corrigida aqui.
    `ModifierStack.register_attribute` ja grava `final_value` clampado
    no MOMENTO do registro (antes de qualquer `recompute_all()`) --
    disparar no frame 1 le um valor correto, nunca lixo.

    Todo campo de `HEALTH_DTYPE`/`hitbox`/`sprite`/`transform`/
    `velocity` do projetil recem-criado e escrito aqui manualmente
    (`ArchetypeLoader` ignora `initial_values` -- gap pre-existente do
    motor, ja documentado no Jogo Musical).
    """

    def __init__(
        self,
        input_provider: IInputProvider,
        transform_pool_name: str,
        velocity_pool_name: str,
        facing_pool_name: str,
        health_pool_name: str,
        hitbox_pool_name: str,
        sprite_pool_name: str,
        player_entity_index: int,
        projectile_archetype_name: str,
        modifier_stack: ModifierStack,
        damage_attribute_index: int,
        cooldown_attribute_index: int,
        speed_attribute_index: int,
        projectile_half_extent: float,
        projectile_collision_layer: int,
        projectile_collision_mask: int,
        projectile_texture_id: int,
        projectile_tint_rgba: Tuple[int, int, int, int],
        fire_action_name: str = "fire",
    ) -> None:
        self._input_provider = input_provider
        self._transform_pool_name = transform_pool_name
        self._velocity_pool_name = velocity_pool_name
        self._facing_pool_name = facing_pool_name
        self._health_pool_name = health_pool_name
        self._hitbox_pool_name = hitbox_pool_name
        self._sprite_pool_name = sprite_pool_name
        self._player_entity_index = player_entity_index
        self._projectile_archetype_name = projectile_archetype_name
        self._modifier_stack = modifier_stack
        self._damage_attribute_index = damage_attribute_index
        self._cooldown_attribute_index = cooldown_attribute_index
        self._speed_attribute_index = speed_attribute_index
        self._projectile_half_extent = float(projectile_half_extent)
        self._projectile_collision_layer = projectile_collision_layer
        self._projectile_collision_mask = projectile_collision_mask
        self._projectile_texture_id = projectile_texture_id
        self._projectile_tint_rgba = projectile_tint_rgba
        self._fire_action_name = fire_action_name
        self._cooldown_remaining_seconds = 0.0

    def update(self, world: "World", delta_time: float) -> None:
        self._cooldown_remaining_seconds = max(0.0, self._cooldown_remaining_seconds - delta_time)
        if not self._input_provider.is_action_pressed(self._fire_action_name):
            return
        if self._cooldown_remaining_seconds > 0.0:
            return

        transform_pool = world.get_pool(self._transform_pool_name)
        facing_pool = world.get_pool(self._facing_pool_name)
        if not (transform_pool.is_attached(self._player_entity_index) and
                facing_pool.is_attached(self._player_entity_index)):
            return  # jogador morto -- nada a disparar

        t_row = transform_pool.dense_row_of(self._player_entity_index)
        t_view = transform_pool.active_view()
        player_x = float(t_view["position_x"][t_row])
        player_y = float(t_view["position_y"][t_row])

        f_row = facing_pool.dense_row_of(self._player_entity_index)
        f_view = facing_pool.active_view()
        facing_x = float(f_view["facing_x"][f_row])
        facing_y = float(f_view["facing_y"][f_row])

        attributes = self._modifier_stack.attributes
        damage = float(attributes[self._damage_attribute_index]["final_value"])
        cooldown_seconds = float(attributes[self._cooldown_attribute_index]["final_value"])
        speed = float(attributes[self._speed_attribute_index]["final_value"])

        self._spawn_projectile(world, player_x, player_y, facing_x * speed, facing_y * speed, damage)
        self._cooldown_remaining_seconds = cooldown_seconds

    def _spawn_projectile(
        self, world: "World", position_x: float, position_y: float,
        velocity_x: float, velocity_y: float, damage: float,
    ) -> None:
        packed_entity_id = world.create_entity(self._projectile_archetype_name)
        index = unpack_index(packed_entity_id)

        transform_pool = world.get_pool(self._transform_pool_name)
        t_row = transform_pool.dense_row_of(index)
        t_view = transform_pool.active_view()
        t_view["position_x"][t_row] = position_x
        t_view["position_y"][t_row] = position_y
        t_view["rotation_rad"][t_row] = 0.0
        t_view["scale_x"][t_row] = 1.0
        t_view["scale_y"][t_row] = 1.0

        velocity_pool = world.get_pool(self._velocity_pool_name)
        v_row = velocity_pool.dense_row_of(index)
        v_view = velocity_pool.active_view()
        v_view["linear_x"][v_row] = velocity_x
        v_view["linear_y"][v_row] = velocity_y
        v_view["angular"][v_row] = 0.0

        hitbox_pool = world.get_pool(self._hitbox_pool_name)
        h_row = hitbox_pool.dense_row_of(index)
        h_view = hitbox_pool.active_view()
        h_view["half_width"][h_row] = self._projectile_half_extent
        h_view["half_height"][h_row] = self._projectile_half_extent
        h_view["collision_layer"][h_row] = self._projectile_collision_layer
        h_view["collision_mask"][h_row] = self._projectile_collision_mask

        sprite_pool = world.get_pool(self._sprite_pool_name)
        s_row = sprite_pool.dense_row_of(index)
        s_view = sprite_pool.active_view()
        s_view["texture_id"][s_row] = self._projectile_texture_id
        s_view["tint_r"][s_row] = self._projectile_tint_rgba[0]
        s_view["tint_g"][s_row] = self._projectile_tint_rgba[1]
        s_view["tint_b"][s_row] = self._projectile_tint_rgba[2]
        s_view["tint_a"][s_row] = self._projectile_tint_rgba[3]
        s_view["layer_z"][s_row] = 5

        health_pool = world.get_pool(self._health_pool_name)
        hp_row = health_pool.dense_row_of(index)
        hp_view = health_pool.active_view()
        hp_view["entity_kind"][hp_row] = EntityKind.PROJECTILE
        hp_view["current_hp"][hp_row] = 1.0
        hp_view["max_hp"][hp_row] = 1.0
        hp_view["contact_damage"][hp_row] = damage
        hp_view["destroy_on_hit"][hp_row] = True
