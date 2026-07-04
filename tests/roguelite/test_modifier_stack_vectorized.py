"""Testes vetorizados de ModifierStack (Pilar 3): FLAT/PERCENT_ADD/PERCENT_MULT, reciclagem e idempotencia."""
from __future__ import annotations

import pytest

from ouroboros.roguelite.modifiers.modifier_stack import ModifierStack
from ouroboros.roguelite.modifiers.schemas import ModifierOperation


def test_register_attribute_returns_stable_sequential_indices() -> None:
    stack = ModifierStack(attribute_capacity=4, entry_capacity=4)
    first = stack.register_attribute(base_value=10.0, min_clamp=0.0, max_clamp=100.0)
    second = stack.register_attribute(base_value=20.0, min_clamp=0.0, max_clamp=100.0)

    assert first == 0
    assert second == 1
    assert stack.attribute_count == 2


def test_register_attribute_raises_when_capacity_exceeded() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    stack.register_attribute(base_value=1.0, min_clamp=0.0, max_clamp=10.0)
    with pytest.raises(IndexError):
        stack.register_attribute(base_value=1.0, min_clamp=0.0, max_clamp=10.0)


def test_push_raises_when_entry_capacity_exceeded() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    attribute_index = stack.register_attribute(base_value=1.0, min_clamp=0.0, max_clamp=10.0)
    stack.push(attribute_index, ModifierOperation.FLAT, 1.0, source_id=1)
    with pytest.raises(IndexError):
        stack.push(attribute_index, ModifierOperation.FLAT, 1.0, source_id=2)


def test_flat_percent_add_and_percent_mult_apply_in_fixed_order() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=8)
    attribute_index = stack.register_attribute(base_value=100.0, min_clamp=0.0, max_clamp=10_000.0)

    # base=100, +10 flat -> 110; +20% e +10% aditivos entre si -> *1.30 -> 143;
    # *1.5 multiplicativo -> 214.5
    stack.push(attribute_index, ModifierOperation.FLAT, 10.0, source_id=1)
    stack.push(attribute_index, ModifierOperation.PERCENT_ADD, 0.20, source_id=2)
    stack.push(attribute_index, ModifierOperation.PERCENT_ADD, 0.10, source_id=3)
    stack.push(attribute_index, ModifierOperation.PERCENT_MULT, 1.5, source_id=4)

    stack.recompute_all()

    final_value = float(stack.attributes[attribute_index]["final_value"])
    assert final_value == pytest.approx(214.5)


def test_clamp_restricts_final_value() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=4)
    attribute_index = stack.register_attribute(base_value=100.0, min_clamp=0.0, max_clamp=120.0)
    stack.push(attribute_index, ModifierOperation.FLAT, 1000.0, source_id=1)

    stack.recompute_all()

    assert float(stack.attributes[attribute_index]["final_value"]) == pytest.approx(120.0)


def test_remove_by_source_deactivates_only_matching_entries() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=4)
    attribute_index = stack.register_attribute(base_value=0.0, min_clamp=0.0, max_clamp=1_000.0)
    stack.push(attribute_index, ModifierOperation.FLAT, 5.0, source_id=1)
    stack.push(attribute_index, ModifierOperation.FLAT, 7.0, source_id=2)

    removed = stack.remove_by_source(1)
    assert removed == 1

    stack.recompute_all()
    assert float(stack.attributes[attribute_index]["final_value"]) == pytest.approx(7.0)


def test_remove_by_source_recycles_slot_for_future_push() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    attribute_index = stack.register_attribute(base_value=0.0, min_clamp=0.0, max_clamp=1_000.0)
    stack.push(attribute_index, ModifierOperation.FLAT, 5.0, source_id=1)

    # Capacidade de entradas esgotada (1/1) -- deve falhar antes da reciclagem.
    with pytest.raises(IndexError):
        stack.push(attribute_index, ModifierOperation.FLAT, 3.0, source_id=2)

    stack.remove_by_source(1)

    # Apos remocao, o unico slot deve estar livre para reciclagem.
    new_index = stack.push(attribute_index, ModifierOperation.FLAT, 3.0, source_id=2)
    assert new_index == 0

    stack.recompute_all()
    assert float(stack.attributes[attribute_index]["final_value"]) == pytest.approx(3.0)


def test_recompute_all_is_idempotent() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=4)
    attribute_index = stack.register_attribute(base_value=10.0, min_clamp=0.0, max_clamp=1_000.0)
    stack.push(attribute_index, ModifierOperation.FLAT, 5.0, source_id=1)

    stack.recompute_all()
    first_value = float(stack.attributes[attribute_index]["final_value"])
    stack.recompute_all()
    second_value = float(stack.attributes[attribute_index]["final_value"])
    stack.recompute_all()
    third_value = float(stack.attributes[attribute_index]["final_value"])

    assert first_value == second_value == third_value == pytest.approx(15.0)


def test_recompute_all_leaves_no_ghost_residue_from_removed_modifiers() -> None:
    """Cenario do 'residuo fantasma' mencionado na docstring de
    `accumulate_entries_into`: sem o reset explicito dos scratches no
    Passo 0, uma entrada desativada em um frame anterior continuaria
    contribuindo silenciosamente para `flat_sum`/`percent_add_sum`/
    `percent_mult_product` em recomputacoes futuras."""
    stack = ModifierStack(attribute_capacity=1, entry_capacity=4)
    attribute_index = stack.register_attribute(base_value=10.0, min_clamp=0.0, max_clamp=1_000.0)

    stack.push(attribute_index, ModifierOperation.FLAT, 50.0, source_id=1)
    stack.recompute_all()
    assert float(stack.attributes[attribute_index]["final_value"]) == pytest.approx(60.0)

    removed = stack.remove_by_source(1)
    assert removed == 1

    # Recomputar SEM nenhuma entrada ativa deve voltar exatamente ao
    # base_value -- nao a base_value + residuo do flat_sum antigo.
    stack.recompute_all()
    assert float(stack.attributes[attribute_index]["final_value"]) == pytest.approx(10.0)

    # E recomputar repetidamente nao deve reintroduzir o residuo.
    stack.recompute_all()
    stack.recompute_all()
    assert float(stack.attributes[attribute_index]["final_value"]) == pytest.approx(10.0)


def test_multiple_attributes_are_independent() -> None:
    stack = ModifierStack(attribute_capacity=2, entry_capacity=4)
    attribute_a = stack.register_attribute(base_value=10.0, min_clamp=0.0, max_clamp=1_000.0)
    attribute_b = stack.register_attribute(base_value=20.0, min_clamp=0.0, max_clamp=1_000.0)

    stack.push(attribute_a, ModifierOperation.FLAT, 5.0, source_id=1)

    stack.recompute_all()

    assert float(stack.attributes[attribute_a]["final_value"]) == pytest.approx(15.0)
    assert float(stack.attributes[attribute_b]["final_value"]) == pytest.approx(20.0)


def test_entry_count_tracks_used_slots_prefix() -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=4)
    attribute_index = stack.register_attribute(base_value=0.0, min_clamp=0.0, max_clamp=1_000.0)
    assert stack.entry_count == 0
    stack.push(attribute_index, ModifierOperation.FLAT, 1.0, source_id=1)
    stack.push(attribute_index, ModifierOperation.FLAT, 1.0, source_id=2)
    assert stack.entry_count == 2
