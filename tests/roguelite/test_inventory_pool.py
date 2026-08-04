# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de InventoryPool (Pilar 3): equip/unequip e nao-colisao entre slots de um mesmo dono."""
from __future__ import annotations

import numpy as np
import pytest

from ouroboros.core.memory.component_pool import ComponentPool
from ouroboros.roguelite.items.inventory_pool import InventoryPool
from ouroboros.roguelite.items.schemas import INVENTORY_SLOT_DTYPE

MAX_SLOTS_PER_OWNER = 2


def _make_inventory(entity_capacity: int = 32) -> InventoryPool:
    pool = ComponentPool(dtype=INVENTORY_SLOT_DTYPE, dense_capacity=entity_capacity, entity_capacity=entity_capacity)
    return InventoryPool(pool, max_slots_per_owner=MAX_SLOTS_PER_OWNER)


def _weapon_row(weapon_def_id: int, modifier_source_id: int) -> np.void:
    row = np.zeros(1, dtype=INVENTORY_SLOT_DTYPE)[0]
    row["weapon_def_id"] = weapon_def_id
    row["modifier_source_id"] = modifier_source_id
    row["damage_attribute_index"] = 0
    row["cooldown_attribute_index"] = 1
    row["range_attribute_index"] = 2
    return row


def test_compute_flat_slot_id_is_pure_and_matches_formula() -> None:
    assert InventoryPool.compute_flat_slot_id(owner_local_index=3, slot_index=1, max_slots_per_owner=2) == 7
    assert InventoryPool.compute_flat_slot_id(owner_local_index=0, slot_index=0, max_slots_per_owner=2) == 0


def test_equip_occupies_slot_and_writes_fields() -> None:
    inventory = _make_inventory()
    row = _weapon_row(weapon_def_id=42, modifier_source_id=1001)

    dense_row = inventory.equip(owner_local_index=0, slot_index=0, weapon_row=row)

    active = inventory.active_view()
    assert active.shape[0] == 1
    assert int(active[dense_row]["weapon_def_id"]) == 42
    assert int(active[dense_row]["modifier_source_id"]) == 1001


def test_multiple_slots_per_owner_do_not_collide() -> None:
    inventory = _make_inventory()

    inventory.equip(owner_local_index=5, slot_index=0, weapon_row=_weapon_row(1, 100))
    inventory.equip(owner_local_index=5, slot_index=1, weapon_row=_weapon_row(2, 200))

    active = inventory.active_view()
    assert active.shape[0] == 2
    weapon_ids = sorted(int(row["weapon_def_id"]) for row in active)
    assert weapon_ids == [1, 2]


def test_different_owners_do_not_collide() -> None:
    inventory = _make_inventory()

    inventory.equip(owner_local_index=0, slot_index=0, weapon_row=_weapon_row(1, 100))
    inventory.equip(owner_local_index=1, slot_index=0, weapon_row=_weapon_row(2, 200))

    active = inventory.active_view()
    assert active.shape[0] == 2


def test_unequip_frees_slot_for_reuse() -> None:
    inventory = _make_inventory()
    inventory.equip(owner_local_index=0, slot_index=0, weapon_row=_weapon_row(1, 100))

    inventory.unequip(owner_local_index=0, slot_index=0)
    assert inventory.active_view().shape[0] == 0

    # O mesmo slot achatado pode ser reocupado apos liberado.
    inventory.equip(owner_local_index=0, slot_index=0, weapon_row=_weapon_row(2, 200))
    assert inventory.active_view().shape[0] == 1
    assert int(inventory.active_view()[0]["weapon_def_id"]) == 2


def test_unequip_only_affects_targeted_slot() -> None:
    inventory = _make_inventory()
    inventory.equip(owner_local_index=2, slot_index=0, weapon_row=_weapon_row(1, 100))
    inventory.equip(owner_local_index=2, slot_index=1, weapon_row=_weapon_row(2, 200))

    inventory.unequip(owner_local_index=2, slot_index=0)

    active = inventory.active_view()
    assert active.shape[0] == 1
    assert int(active[0]["weapon_def_id"]) == 2


def test_equip_same_flat_slot_twice_raises() -> None:
    inventory = _make_inventory()
    inventory.equip(owner_local_index=0, slot_index=0, weapon_row=_weapon_row(1, 100))
    with pytest.raises(ValueError):
        inventory.equip(owner_local_index=0, slot_index=0, weapon_row=_weapon_row(2, 200))
