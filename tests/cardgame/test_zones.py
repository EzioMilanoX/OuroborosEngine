# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de ouroboros.cardgame.zones (Zone/CardInstance)."""
from __future__ import annotations

import random

from ouroboros.cardgame.zones import CardInstance, Zone


def test_draw_top_pops_from_the_end_of_the_list_in_topmost_first_order() -> None:
    zone = Zone("deck")
    zone.cards = [CardInstance(0, 1), CardInstance(1, 1), CardInstance(2, 1)]

    drawn = zone.draw_top(2)

    assert [c.instance_id for c in drawn] == [2, 1]
    assert [c.instance_id for c in zone.cards] == [0]


def test_draw_top_from_an_empty_zone_returns_an_empty_list_without_raising() -> None:
    zone = Zone("deck")

    drawn = zone.draw_top(3)

    assert drawn == []


def test_draw_top_returns_fewer_than_requested_when_the_zone_runs_dry() -> None:
    zone = Zone("deck")
    zone.cards = [CardInstance(0, 1)]

    drawn = zone.draw_top(5)

    assert [c.instance_id for c in drawn] == [0]
    assert zone.cards == []


def test_move_top_to_moves_cards_from_one_zone_onto_the_top_of_another() -> None:
    deck = Zone("deck")
    hand = Zone("hand")
    deck.cards = [CardInstance(0, 1), CardInstance(1, 1)]

    moved = deck.move_top_to(hand, count=1)

    assert [c.instance_id for c in moved] == [1]
    assert [c.instance_id for c in hand.cards] == [1]
    assert [c.instance_id for c in deck.cards] == [0]


def test_move_specific_to_removes_the_exact_instance_by_identity_not_by_value() -> None:
    """Duas copias com os MESMOS valores de campo (mesmo instance_id/
    card_def_id, simulando o pior caso) -- so a copia REFERENCIADA (por
    identidade de objeto) deve ser removida, provando que
    `CardInstance(eq=False)` esta realmente em vigor (com `eq` padrao,
    `list.remove` removeria a PRIMEIRA copia igual por valor, nao
    necessariamente a pretendida)."""
    hand = Zone("hand")
    discard = Zone("discard")
    first_copy = CardInstance(instance_id=5, card_def_id=1)
    second_copy = CardInstance(instance_id=5, card_def_id=1)
    hand.cards = [first_copy, second_copy]

    hand.move_specific_to(second_copy, discard)

    assert hand.cards == [first_copy]
    assert hand.cards[0] is first_copy
    assert discard.cards == [second_copy]


def test_shuffle_uses_the_injected_rng_deterministically() -> None:
    zone_a = Zone("deck")
    zone_a.cards = [CardInstance(i, 1) for i in range(10)]
    zone_b = Zone("deck")
    zone_b.cards = [CardInstance(i, 1) for i in range(10)]

    zone_a.shuffle(random.Random(42))
    zone_b.shuffle(random.Random(42))

    assert [c.instance_id for c in zone_a.cards] == [c.instance_id for c in zone_b.cards]
