# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa TurnQueue: ordenacao por iniciativa, avanco pulando mortos, remocao, casos-limite."""
from __future__ import annotations

from ouroboros.tactics.turn_queue import TurnQueue


def test_build_orders_by_initiative_descending():
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20, 30], initiative_values=[1.0, 5.0, 3.0])

    assert queue.current_entity_index == 20  # maior iniciativa primeiro


def test_build_uses_a_stable_tiebreak_for_equal_initiative():
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20, 30], initiative_values=[5.0, 5.0, 1.0])

    # empate entre 10 e 20 -- ordem de chegada (10 antes de 20) preservada
    assert queue.current_entity_index == 10
    assert queue.advance_to_next() == 20


def test_advance_to_next_cycles_through_everyone_and_wraps_around():
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20], initiative_values=[2.0, 1.0])

    assert queue.current_entity_index == 10
    assert queue.advance_to_next() == 20
    assert queue.advance_to_next() == 10  # wraparound


def test_advance_to_next_skips_dead_entries():
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20, 30], initiative_values=[3.0, 2.0, 1.0])
    queue.remove(20)

    assert queue.current_entity_index == 10
    assert queue.advance_to_next() == 30  # pula o 20, que morreu


def test_current_entity_index_is_none_after_everyone_dies():
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20], initiative_values=[2.0, 1.0])
    queue.remove(10)
    queue.remove(20)

    assert queue.current_entity_index is None


def test_advance_to_next_returns_none_immediately_when_everyone_is_dead():
    """Nao deve escanear a fila inteira (ou travar) so pra descobrir que
    ninguem esta vivo -- retorna None de cara."""
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20], initiative_values=[2.0, 1.0])
    queue.remove(10)
    queue.remove(20)

    assert queue.advance_to_next() is None


def test_remove_on_the_currently_active_unit_makes_current_entity_index_none():
    """Defensivo: se a propria unidade ativa morrer no meio do turno dela
    (ex.: um futuro contra-ataque), current_entity_index nao deve devolver
    um indice de uma unidade ja morta."""
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20], initiative_values=[2.0, 1.0])
    queue.remove(10)  # 10 e quem esta ativo agora

    assert queue.current_entity_index is None


def test_remove_is_a_no_op_when_called_twice():
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20], initiative_values=[2.0, 1.0])
    queue.remove(10)
    queue.remove(10)  # nao deve decrementar _alive_count duas vezes

    assert queue.advance_to_next() == 20


def test_remove_is_a_no_op_for_an_entity_index_never_in_the_queue():
    queue = TurnQueue(capacity=8)
    queue.build(entity_indices=[10, 20], initiative_values=[2.0, 1.0])
    queue.remove(999)

    assert queue.current_entity_index == 10
