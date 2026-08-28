# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Testa DamageOnCollisionSystem: dano simetrico via CollisionSystem.get_collision_pairs(),
destroy_on_hit, e a correcao real do plano contra reuso de entity_index entre frames
(player_is_dead trava permanentemente; enemies_remaining nunca conta um indice
reciclado por outra entidade como "ainda inimigo").
"""
from __future__ import annotations

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.systems.collision_system import CollisionSystem
from ouroboros.roguelite.combat.schemas import EntityKind, HEALTH_DTYPE
from ouroboros.roguelite.systems.damage_system import DamageOnCollisionSystem

HEALTH_POOL_NAME = "health"
ARCHETYPE_NAME = "combatant"

LAYER_A = 1
LAYER_B = 2


def _register(memory_manager, world):
    memory_manager.create_pool(HEALTH_POOL_NAME, HEALTH_DTYPE)
    world.register_archetype(ARCHETYPE_NAME, ("transform", "hitbox", HEALTH_POOL_NAME))


def _spawn(world, entity_kind, current_hp, contact_damage, destroy_on_hit, layer, mask, x=0.0, y=0.0):
    packed = world.create_entity(ARCHETYPE_NAME)
    index = unpack_index(packed)

    transform_pool = world.get_pool("transform")
    t_row = transform_pool.dense_row_of(index)
    t_view = transform_pool.active_view()
    t_view["position_x"][t_row] = x
    t_view["position_y"][t_row] = y

    hitbox_pool = world.get_pool("hitbox")
    h_row = hitbox_pool.dense_row_of(index)
    h_view = hitbox_pool.active_view()
    h_view["half_width"][h_row] = 5.0
    h_view["half_height"][h_row] = 5.0
    h_view["collision_layer"][h_row] = layer
    h_view["collision_mask"][h_row] = mask

    health_pool = world.get_pool(HEALTH_POOL_NAME)
    hp_row = health_pool.dense_row_of(index)
    hp_view = health_pool.active_view()
    hp_view["entity_kind"][hp_row] = entity_kind
    hp_view["current_hp"][hp_row] = current_hp
    hp_view["max_hp"][hp_row] = current_hp
    hp_view["contact_damage"][hp_row] = contact_damage
    hp_view["destroy_on_hit"][hp_row] = destroy_on_hit

    return packed, index


def _make_system(memory_manager, world, player_entity_index=-1):
    collision_system = CollisionSystem(memory_manager, "transform", "hitbox", max_pairs=64)
    world.register_system(collision_system)
    damage_system = DamageOnCollisionSystem(collision_system, HEALTH_POOL_NAME, player_entity_index)
    world.register_system(damage_system)
    return damage_system


def test_symmetric_damage_is_applied_both_ways_on_collision(memory_manager, world):
    _register(memory_manager, world)
    _spawn(world, EntityKind.PLAYER, current_hp=100.0, contact_damage=5.0, destroy_on_hit=False,
           layer=LAYER_A, mask=LAYER_B, x=0.0, y=0.0)
    _spawn(world, EntityKind.ENEMY, current_hp=30.0, contact_damage=8.0, destroy_on_hit=False,
           layer=LAYER_B, mask=LAYER_A, x=1.0, y=0.0)
    _make_system(memory_manager, world)

    world.step(0.016)

    health_pool = world.get_pool(HEALTH_POOL_NAME)
    view = health_pool.active_view()
    hp_values = sorted(float(v) for v in view["current_hp"])
    assert hp_values == [25.0, 92.0]  # inimigo (30) recebe o contact_damage do player (5) -> 25;
    # player (100) recebe o contact_damage do inimigo (8) -> 92 -- dano e sempre do OUTRO lado.


def test_destroy_on_hit_removes_projectile_even_without_its_own_hp_dropping(memory_manager, world):
    _register(memory_manager, world)
    _spawn(world, EntityKind.ENEMY, current_hp=30.0, contact_damage=0.0, destroy_on_hit=False,
           layer=LAYER_A, mask=LAYER_B, x=0.0, y=0.0)
    _, projectile_index = _spawn(world, EntityKind.PROJECTILE, current_hp=1.0, contact_damage=10.0,
                                  destroy_on_hit=True, layer=LAYER_B, mask=LAYER_A, x=1.0, y=0.0)
    _make_system(memory_manager, world)

    world.step(0.016)

    health_pool = world.get_pool(HEALTH_POOL_NAME)
    assert not health_pool.is_attached(projectile_index)
    assert health_pool.count == 1  # so o inimigo (com hp reduzido) sobrevive


def test_current_hp_at_or_below_zero_destroys_the_entity(memory_manager, world):
    _register(memory_manager, world)
    _spawn(world, EntityKind.ENEMY, current_hp=5.0, contact_damage=0.0, destroy_on_hit=False,
           layer=LAYER_A, mask=LAYER_B, x=0.0, y=0.0)
    _spawn(world, EntityKind.PROJECTILE, current_hp=1.0, contact_damage=10.0, destroy_on_hit=True,
           layer=LAYER_B, mask=LAYER_A, x=1.0, y=0.0)
    _make_system(memory_manager, world)

    world.step(0.016)

    health_pool = world.get_pool(HEALTH_POOL_NAME)
    assert health_pool.count == 0  # inimigo morreu (5-10<=0) e o projetil foi consumido


def test_no_collision_means_no_damage(memory_manager, world):
    _register(memory_manager, world)
    _spawn(world, EntityKind.PLAYER, current_hp=100.0, contact_damage=5.0, destroy_on_hit=False,
           layer=LAYER_A, mask=LAYER_B, x=0.0, y=0.0)
    _spawn(world, EntityKind.ENEMY, current_hp=30.0, contact_damage=8.0, destroy_on_hit=False,
           layer=LAYER_B, mask=LAYER_A, x=500.0, y=500.0)  # longe -- nunca colide
    _make_system(memory_manager, world)

    world.step(0.016)

    health_pool = world.get_pool(HEALTH_POOL_NAME)
    view = health_pool.active_view()
    assert sorted(float(v) for v in view["current_hp"]) == [30.0, 100.0]


def test_player_is_dead_latches_and_never_flips_back_even_if_the_freed_index_is_reused(memory_manager, world):
    """Prova direta do achado do plano: MemoryManager recicla `entity_index` entre
    arquetipos -- uma vez que o jogador morre, `player_is_dead` deve continuar True
    PARA SEMPRE, mesmo que uma entidade NOVA reaproveite o mesmo indice liberado."""
    _register(memory_manager, world)
    _, player_index = _spawn(world, EntityKind.PLAYER, current_hp=5.0, contact_damage=0.0,
                              destroy_on_hit=False, layer=LAYER_A, mask=LAYER_B, x=0.0, y=0.0)
    # dano fatal ao jogador, mas o proprio inimigo NAO morre (destroy_on_hit=False, hp alto e
    # contact_damage do player e 0) -- so UM indice e liberado neste frame, tornando o proximo
    # reuso deterministico.
    _spawn(world, EntityKind.ENEMY, current_hp=999.0, contact_damage=10.0, destroy_on_hit=False,
           layer=LAYER_B, mask=LAYER_A, x=1.0, y=0.0)
    damage_system = _make_system(memory_manager, world, player_entity_index=player_index)

    world.step(0.016)  # jogador morre (5-10<=0), indice e liberado no flush() deste mesmo step

    assert damage_system.player_is_dead is True

    # uma NOVA entidade (bem longe, nunca colide com nada) reaproveita o mesmo entity_index
    # liberado (free-list e LIFO) -- player_is_dead nao pode voltar a False por causa disso.
    _, recycled_index = _spawn(world, EntityKind.ENEMY, current_hp=30.0, contact_damage=0.0,
                                destroy_on_hit=False, layer=LAYER_A, mask=LAYER_B, x=999.0, y=999.0)
    assert recycled_index == player_index  # confirma que o indice foi de fato reciclado

    world.step(0.016)

    assert damage_system.player_is_dead is True


def test_enemies_remaining_never_counts_a_recycled_index_as_still_an_enemy(memory_manager, world):
    """Mesmo cenario de reuso de indice, do lado de enemies_remaining: um projetil que
    reaproveita o entity_index de um inimigo morto nao pode ser contado como inimigo."""
    _register(memory_manager, world)
    _spawn(world, EntityKind.ENEMY, current_hp=5.0, contact_damage=0.0, destroy_on_hit=False,
           layer=LAYER_A, mask=LAYER_B, x=0.0, y=0.0)
    _, projectile_index = _spawn(world, EntityKind.PROJECTILE, current_hp=1.0, contact_damage=10.0,
                                  destroy_on_hit=True, layer=LAYER_B, mask=LAYER_A, x=1.0, y=0.0)
    damage_system = _make_system(memory_manager, world)

    world.step(0.016)  # inimigo morre E o projetil e consumido -- 2 indices enfileirados p/ liberar
    # o recalculo de enemies_remaining dentro do MESMO update() que causa a morte ainda ve a pool
    # de ANTES do flush() (flush so roda no fim do step()) -- um segundo step (sem colisoes) deixa
    # o recalculo enxergar a pool ja sem os dois.
    world.step(0.016)

    assert damage_system.enemies_remaining == 0

    # uma nova entidade PROJETIL (nao inimigo) reaproveita um dos indices liberados
    _, recycled_index = _spawn(world, EntityKind.PROJECTILE, current_hp=1.0, contact_damage=0.0,
                                destroy_on_hit=False, layer=LAYER_A, mask=LAYER_B, x=999.0, y=999.0)

    world.step(0.016)

    assert damage_system.enemies_remaining == 0  # a entidade reciclada e PROJECTILE, nao ENEMY
