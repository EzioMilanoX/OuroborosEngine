"""Testes de determinismo/isolamento de StrictRandom (Pilar 3)."""
from __future__ import annotations

import numpy as np

from ouroboros.roguelite.generation.random import RandomStreamPurpose, StrictRandom


def test_same_root_seed_produces_same_numbers() -> None:
    a = StrictRandom(root_seed=12345)
    b = StrictRandom(root_seed=12345)

    values_a = a.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=7).integers(0, 1_000_000, size=16)
    values_b = b.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=7).integers(0, 1_000_000, size=16)

    np.testing.assert_array_equal(values_a, values_b)


def test_different_root_seed_produces_different_numbers() -> None:
    a = StrictRandom(root_seed=1)
    b = StrictRandom(root_seed=2)

    values_a = a.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=0).integers(0, 1_000_000, size=16)
    values_b = b.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=0).integers(0, 1_000_000, size=16)

    assert not np.array_equal(values_a, values_b)


def test_stream_is_cached_and_cursor_persists_across_calls() -> None:
    strict_random = StrictRandom(root_seed=999)
    stream_first_call = strict_random.stream(RandomStreamPurpose.LOOT_TABLE, salt=1)
    first_draw = stream_first_call.integers(0, 1_000_000, size=4)

    # Segunda chamada com o MESMO (purpose, salt) deve retornar o MESMO
    # objeto Generator (com o cursor ja avancado), nunca um novo gerador
    # reiniciado do zero.
    stream_second_call = strict_random.stream(RandomStreamPurpose.LOOT_TABLE, salt=1)
    assert stream_second_call is stream_first_call

    second_draw = stream_second_call.integers(0, 1_000_000, size=4)
    assert not np.array_equal(first_draw, second_draw)


def test_different_purposes_are_independent_streams() -> None:
    strict_random = StrictRandom(root_seed=42)
    dungeon_stream = strict_random.stream(RandomStreamPurpose.DUNGEON_LAYOUT, salt=0)
    loot_stream = strict_random.stream(RandomStreamPurpose.LOOT_TABLE, salt=0)

    assert dungeon_stream is not loot_stream

    dungeon_draw = dungeon_stream.integers(0, 1_000_000, size=8)

    # Consumir do stream DUNGEON_LAYOUT nao deve influenciar o que
    # LOOT_TABLE produziria com o mesmo salt -- comparado contra uma
    # instancia totalmente fresca com a mesma seed raiz.
    fresh = StrictRandom(root_seed=42)
    fresh_loot_draw = fresh.stream(RandomStreamPurpose.LOOT_TABLE, salt=0).integers(0, 1_000_000, size=8)
    loot_draw_after_dungeon_consumed = loot_stream.integers(0, 1_000_000, size=8)

    np.testing.assert_array_equal(fresh_loot_draw, loot_draw_after_dungeon_consumed)
    # Sanidade: o stream dungeon consumido nao e, ele mesmo, igual ao loot.
    assert not np.array_equal(dungeon_draw, fresh_loot_draw)


def test_different_salts_are_independent_streams_for_same_purpose() -> None:
    strict_random = StrictRandom(root_seed=7)
    stream_salt_a = strict_random.stream(RandomStreamPurpose.ENEMY_PLACEMENT, salt=1)
    stream_salt_b = strict_random.stream(RandomStreamPurpose.ENEMY_PLACEMENT, salt=2)

    draw_a = stream_salt_a.integers(0, 1_000_000, size=8)
    draw_b = stream_salt_b.integers(0, 1_000_000, size=8)

    assert not np.array_equal(draw_a, draw_b)


def test_order_of_first_stream_creation_does_not_matter() -> None:
    """`SeedSequence.spawn()` sequencial NAO e usado: pedir os streams em
    ordens diferentes deve produzir exatamente os mesmos numeros para
    cada par (purpose, salt), independentemente de qual foi solicitado
    primeiro."""
    root_seed = 2024
    purposes_and_salts = [
        (RandomStreamPurpose.DUNGEON_LAYOUT, 5),
        (RandomStreamPurpose.LOOT_TABLE, 3),
        (RandomStreamPurpose.ENEMY_PLACEMENT, 1),
        (RandomStreamPurpose.MODIFIER_ROLLS, 0),
    ]

    forward = StrictRandom(root_seed=root_seed)
    forward_draws = {}
    for purpose, salt in purposes_and_salts:
        forward_draws[(purpose, salt)] = forward.stream(purpose, salt).integers(0, 1_000_000, size=8)

    backward = StrictRandom(root_seed=root_seed)
    backward_draws = {}
    for purpose, salt in reversed(purposes_and_salts):
        backward_draws[(purpose, salt)] = backward.stream(purpose, salt).integers(0, 1_000_000, size=8)

    for key in forward_draws:
        np.testing.assert_array_equal(forward_draws[key], backward_draws[key])


def test_root_seed_property_is_exposed_and_immutable_value() -> None:
    strict_random = StrictRandom(root_seed=555)
    assert strict_random.root_seed == 555
