# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de ModifierApplicationSystem (Pilar 1): recompute_all em varias stacks, na ordem certa."""
from __future__ import annotations

import pytest

from ouroboros.core.modifiers.modifier_stack import ModifierStack
from ouroboros.core.modifiers.schemas import ModifierOperation
from ouroboros.core.systems.modifier_application_system import ModifierApplicationSystem


class _TrackedModifierStack(ModifierStack):
    """Subclasse minima usada apenas para observar em qual ordem
    `recompute_all` foi chamado pelo sistema, sem alterar o comportamento
    real de `ModifierStack`."""

    def __init__(self, name: str, call_order: list, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._name = name
        self._call_order = call_order

    def recompute_all(self) -> None:
        self._call_order.append(self._name)
        super().recompute_all()


def test_update_recomputes_all_registered_stacks(world) -> None:
    character_stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    weapon_stack = ModifierStack(attribute_capacity=1, entry_capacity=1)

    character_attr = character_stack.register_attribute(base_value=10.0, min_clamp=0.0, max_clamp=1_000.0)
    weapon_attr = weapon_stack.register_attribute(base_value=5.0, min_clamp=0.0, max_clamp=1_000.0)

    character_stack.push(character_attr, ModifierOperation.FLAT, 2.0, source_id=1)
    weapon_stack.push(weapon_attr, ModifierOperation.FLAT, 3.0, source_id=1)

    system = ModifierApplicationSystem((character_stack, weapon_stack))
    system.update(world, 0.016)

    assert float(character_stack.attributes[character_attr]["final_value"]) == pytest.approx(12.0)
    assert float(weapon_stack.attributes[weapon_attr]["final_value"]) == pytest.approx(8.0)


def test_update_calls_recompute_all_in_registration_order(world) -> None:
    call_order: list = []
    stack_a = _TrackedModifierStack("a", call_order, attribute_capacity=1, entry_capacity=1)
    stack_b = _TrackedModifierStack("b", call_order, attribute_capacity=1, entry_capacity=1)

    system = ModifierApplicationSystem((stack_a, stack_b))
    system.update(world, 0.016)

    assert call_order == ["a", "b"]


def test_update_respects_reversed_registration_order(world) -> None:
    call_order: list = []
    stack_a = _TrackedModifierStack("a", call_order, attribute_capacity=1, entry_capacity=1)
    stack_b = _TrackedModifierStack("b", call_order, attribute_capacity=1, entry_capacity=1)

    system = ModifierApplicationSystem((stack_b, stack_a))
    system.update(world, 0.016)

    assert call_order == ["b", "a"]


def test_update_ignores_delta_time(world) -> None:
    stack = ModifierStack(attribute_capacity=1, entry_capacity=1)
    attribute_index = stack.register_attribute(base_value=1.0, min_clamp=0.0, max_clamp=100.0)
    stack.push(attribute_index, ModifierOperation.FLAT, 4.0, source_id=1)

    system = ModifierApplicationSystem((stack,))
    system.update(world, 0.0)
    value_with_zero_dt = float(stack.attributes[attribute_index]["final_value"])
    system.update(world, 999.0)
    value_with_huge_dt = float(stack.attributes[attribute_index]["final_value"])

    assert value_with_zero_dt == value_with_huge_dt == pytest.approx(5.0)
