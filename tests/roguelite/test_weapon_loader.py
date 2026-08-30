# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de WeaponLoader (Pilar 3): carga real de data/weapons e isolamento entre instancias equipadas."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ouroboros.core.memory.component_pool import ComponentPool
from ouroboros.core.modifiers.modifier_stack import ModifierStack
from ouroboros.core.modifiers.schemas import ModifierOperation
from ouroboros.core.stable_id import stable_id_from_name
from ouroboros.roguelite.items.inventory_pool import InventoryPool
from ouroboros.roguelite.items.schemas import INVENTORY_SLOT_DTYPE
from ouroboros.roguelite.items.weapon_loader import WeaponDefinitionError, WeaponLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_WEAPONS_DIR = REPO_ROOT / "data" / "weapons"


def _make_inventory(entity_capacity: int = 32) -> InventoryPool:
    pool = ComponentPool(dtype=INVENTORY_SLOT_DTYPE, dense_capacity=entity_capacity, entity_capacity=entity_capacity)
    return InventoryPool(pool, max_slots_per_owner=2)


def test_load_all_definitions_reads_real_starter_pistol() -> None:
    loader = WeaponLoader(REAL_WEAPONS_DIR)
    definitions = loader.load_all_definitions()

    assert len(definitions) >= 1
    row = next(iter(definitions.values()))
    assert row["damage_attribute_index"] >= 0
    assert row["cooldown_attribute_index"] >= 0
    assert row["range_attribute_index"] >= 0


def test_materialize_before_load_raises() -> None:
    loader = WeaponLoader(REAL_WEAPONS_DIR)
    modifier_stack = ModifierStack(attribute_capacity=8, entry_capacity=8)
    inventory = _make_inventory()

    with pytest.raises(WeaponDefinitionError):
        loader.materialize(
            weapon_def_id=1,
            definitions={},
            inventory=inventory,
            modifier_stack=modifier_stack,
            owner_local_index=0,
            slot_index=0,
            instance_source_id=1,
        )


def test_materialize_unknown_weapon_def_id_raises() -> None:
    loader = WeaponLoader(REAL_WEAPONS_DIR)
    definitions = loader.load_all_definitions()
    modifier_stack = ModifierStack(attribute_capacity=8, entry_capacity=8)
    inventory = _make_inventory()

    with pytest.raises(WeaponDefinitionError):
        loader.materialize(
            weapon_def_id=-1,
            definitions=definitions,
            inventory=inventory,
            modifier_stack=modifier_stack,
            owner_local_index=0,
            slot_index=0,
            instance_source_id=1,
        )


def test_materialize_copies_base_values_from_definition() -> None:
    loader = WeaponLoader(REAL_WEAPONS_DIR)
    definitions = loader.load_all_definitions()
    weapon_def_id = next(iter(definitions))
    raw = json.loads((REAL_WEAPONS_DIR / "starter_pistol.json").read_text(encoding="utf-8"))

    modifier_stack = ModifierStack(attribute_capacity=8, entry_capacity=8)
    inventory = _make_inventory()

    dense_row = loader.materialize(
        weapon_def_id=weapon_def_id,
        definitions=definitions,
        inventory=inventory,
        modifier_stack=modifier_stack,
        owner_local_index=0,
        slot_index=0,
        instance_source_id=555,
    )

    slot = inventory.active_view()[dense_row]
    modifier_stack.recompute_all()
    damage_attribute = modifier_stack.attributes[int(slot["damage_attribute_index"])]

    assert float(damage_attribute["final_value"]) == pytest.approx(float(raw["base_damage"]))
    assert int(slot["modifier_source_id"]) == 555


def test_two_instances_of_same_weapon_do_not_interfere_when_unequipping() -> None:
    """O bug que a docstring de WeaponLoader/MODIFIER_ENTRY_DTYPE avisa
    para evitar: usar um source_id compartilhado (ex.: o weapon_def_id)
    faria `remove_by_source` ao desequipar UMA copia remover tambem os
    modificadores da OUTRA copia da mesma arma equipada em outro dono."""
    loader = WeaponLoader(REAL_WEAPONS_DIR)
    definitions = loader.load_all_definitions()
    weapon_def_id = next(iter(definitions))

    modifier_stack = ModifierStack(attribute_capacity=16, entry_capacity=16)
    inventory = _make_inventory()

    instance_source_id_a = 1001
    instance_source_id_b = 2002

    row_a = loader.materialize(
        weapon_def_id, definitions, inventory, modifier_stack,
        owner_local_index=0, slot_index=0, instance_source_id=instance_source_id_a,
    )
    row_b = loader.materialize(
        weapon_def_id, definitions, inventory, modifier_stack,
        owner_local_index=1, slot_index=0, instance_source_id=instance_source_id_b,
    )

    # Extrai os indices de atributo como INTEIROS Python simples, antes de
    # qualquer mutacao posterior da pool -- `inventory.active_view()[row]`
    # e uma VIEW sujeita a swap-remove (ver docstring de
    # `DungeonStreamingSystem`): cachea-la e reindexa-la DEPOIS de um
    # `unequip` (que faz swap-remove) leria dados de outra instancia.
    damage_attribute_index_a = int(inventory.active_view()[row_a]["damage_attribute_index"])
    damage_attribute_index_b = int(inventory.active_view()[row_b]["damage_attribute_index"])

    # As duas instancias devem ter recebido atributos PROPRIOS (indices
    # distintos), mesmo compartilhando a mesma definicao de catalogo.
    assert damage_attribute_index_a != damage_attribute_index_b

    # Simula um buff pontual aplicado a cada instancia equipada
    # separadamente, atrelado ao source_id UNICO daquela instancia.
    modifier_stack.push(damage_attribute_index_a, ModifierOperation.FLAT, 5.0, instance_source_id_a)
    modifier_stack.push(damage_attribute_index_b, ModifierOperation.FLAT, 7.0, instance_source_id_b)
    modifier_stack.recompute_all()

    base_damage = float(modifier_stack.attributes[damage_attribute_index_a]["base_value"])
    value_a_before = float(modifier_stack.attributes[damage_attribute_index_a]["final_value"])
    value_b_before = float(modifier_stack.attributes[damage_attribute_index_b]["final_value"])
    assert value_a_before == pytest.approx(base_damage + 5.0)
    assert value_b_before == pytest.approx(base_damage + 7.0)

    # Desequipar a instancia A NAO pode afetar a instancia B.
    modifier_stack.remove_by_source(instance_source_id_a)
    inventory.unequip(owner_local_index=0, slot_index=0)
    modifier_stack.recompute_all()

    value_a_after = float(modifier_stack.attributes[damage_attribute_index_a]["final_value"])
    value_b_after = float(modifier_stack.attributes[damage_attribute_index_b]["final_value"])

    assert value_a_after == pytest.approx(base_damage)
    assert value_b_after == pytest.approx(base_damage + 7.0)


def test_json_level_modifiers_are_applied_on_materialize(tmp_path) -> None:
    weapons_dir = tmp_path / "weapons"
    weapons_dir.mkdir()
    (weapons_dir / "buffed_pistol.json").write_text(
        json.dumps(
            {
                "id": "buffed_pistol",
                "display_name": "Pistola Buffada",
                "base_damage": 10.0,
                "fire_rate_per_second": 2.0,
                "projectile_speed": 500.0,
                "modifiers": [
                    {"attribute": "damage", "operation": "flat", "magnitude": 5.0},
                    {"attribute": "damage", "operation": "percent_mult", "magnitude": 2.0},
                ],
            }
        ),
        encoding="utf-8",
    )

    loader = WeaponLoader(weapons_dir)
    definitions = loader.load_all_definitions()
    weapon_def_id = next(iter(definitions))

    modifier_stack = ModifierStack(attribute_capacity=8, entry_capacity=8)
    inventory = _make_inventory()

    dense_row = loader.materialize(
        weapon_def_id, definitions, inventory, modifier_stack,
        owner_local_index=0, slot_index=0, instance_source_id=1,
    )
    modifier_stack.recompute_all()

    slot = inventory.active_view()[dense_row]
    final_value = float(modifier_stack.attributes[int(slot["damage_attribute_index"])]["final_value"])
    # (10 + 5) * 2.0 = 30.0
    assert final_value == pytest.approx(30.0)


def test_materialize_applies_submachine_gun_json_modifiers() -> None:
    """Segunda arma real do catalogo (ROADMAP M10.2), primeiro exercicio de
    `modifiers` nao-vazio contra o `data/weapons/` de verdade (nao um
    fixture em tmp_path como `test_json_level_modifiers_are_applied_on_
    materialize`). Resolve o id por `stable_id_from_name` diretamente (nao
    `next(iter(definitions))`) para nao depender da ordem de iteracao do
    dict, que segue `sorted(glob("*.json"))` -- ver docstring de
    `WeaponLoader.load_all_definitions`."""
    loader = WeaponLoader(REAL_WEAPONS_DIR)
    definitions = loader.load_all_definitions()
    weapon_def_id = stable_id_from_name("submachine_gun")
    assert weapon_def_id in definitions

    modifier_stack = ModifierStack(attribute_capacity=8, entry_capacity=8)
    inventory = _make_inventory()

    dense_row = loader.materialize(
        weapon_def_id, definitions, inventory, modifier_stack,
        owner_local_index=0, slot_index=0, instance_source_id=1,
    )
    modifier_stack.recompute_all()

    slot = inventory.active_view()[dense_row]
    damage = float(modifier_stack.attributes[int(slot["damage_attribute_index"])]["final_value"])
    cooldown = float(modifier_stack.attributes[int(slot["cooldown_attribute_index"])]["final_value"])

    # base_damage=6.0 + flat(-1.0) = 5.0
    assert damage == pytest.approx(5.0)
    # base_cooldown=1/6 * percent_mult(0.85) ~= 0.14166667
    assert cooldown == pytest.approx((1.0 / 6.0) * 0.85)


def test_load_all_definitions_raises_on_missing_required_field(tmp_path) -> None:
    weapons_dir = tmp_path / "weapons"
    weapons_dir.mkdir()
    (weapons_dir / "broken.json").write_text(
        json.dumps({"id": "broken", "display_name": "Broken"}), encoding="utf-8"
    )

    loader = WeaponLoader(weapons_dir)
    with pytest.raises(WeaponDefinitionError):
        loader.load_all_definitions()
