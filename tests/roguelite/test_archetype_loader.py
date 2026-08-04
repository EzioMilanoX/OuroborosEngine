# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de ArchetypeLoader (Pilar 3): carga real de data/archetypes e validacao atomica de pools."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ouroboros.core.memory.handles import unpack_index
from ouroboros.core.world import World
from ouroboros.roguelite.entities.archetype_loader import ArchetypeDefinitionError, ArchetypeLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_ARCHETYPES_DIR = REPO_ROOT / "data" / "archetypes"


def test_load_and_register_all_real_archetypes(world: World) -> None:
    loader = ArchetypeLoader(REAL_ARCHETYPES_DIR)
    registered = loader.load_and_register_all(world)

    assert "enemy_goblin" in registered
    assert "rhythm_threat_basic" in registered
    assert registered["enemy_goblin"] == ("transform", "velocity", "hitbox", "sprite")

    assert world.has_archetype("enemy_goblin")
    assert world.has_archetype("rhythm_threat_basic")


def test_create_entity_from_loaded_archetype_attaches_correct_pools(world: World) -> None:
    loader = ArchetypeLoader(REAL_ARCHETYPES_DIR)
    loader.load_and_register_all(world)

    packed = world.create_entity("enemy_goblin")
    index = unpack_index(packed)

    for pool_name in ("transform", "velocity", "hitbox", "sprite"):
        assert world.get_pool(pool_name).is_attached(index)


def test_missing_pool_raises_before_registering_anything(world: World, tmp_path) -> None:
    archetypes_dir = tmp_path / "archetypes"
    archetypes_dir.mkdir()

    # Um arquivo valido...
    (archetypes_dir / "valid_one.json").write_text(
        json.dumps({"id": "valid_one", "pools": ["transform"], "initial_values": {}}), encoding="utf-8"
    )
    # ...e um arquivo que referencia um pool inexistente.
    (archetypes_dir / "invalid_one.json").write_text(
        json.dumps({"id": "invalid_one", "pools": ["transform", "nonexistent_pool"], "initial_values": {}}),
        encoding="utf-8",
    )

    loader = ArchetypeLoader(archetypes_dir)
    with pytest.raises(ArchetypeDefinitionError):
        loader.load_and_register_all(world)

    # Nenhum arquetipo deve ter sido registrado -- nem mesmo o valido --
    # porque a validacao cruzada acontece ANTES de registrar qualquer um.
    assert not world.has_archetype("valid_one")
    assert not world.has_archetype("invalid_one")


def test_malformed_json_missing_required_field_raises(world: World, tmp_path) -> None:
    archetypes_dir = tmp_path / "archetypes"
    archetypes_dir.mkdir()
    (archetypes_dir / "broken.json").write_text(json.dumps({"pools": ["transform"]}), encoding="utf-8")

    loader = ArchetypeLoader(archetypes_dir)
    with pytest.raises(ArchetypeDefinitionError):
        loader.load_and_register_all(world)


def test_duplicate_archetype_id_raises(world: World, tmp_path) -> None:
    archetypes_dir = tmp_path / "archetypes"
    archetypes_dir.mkdir()
    (archetypes_dir / "a.json").write_text(
        json.dumps({"id": "dup", "pools": ["transform"], "initial_values": {}}), encoding="utf-8"
    )
    (archetypes_dir / "b.json").write_text(
        json.dumps({"id": "dup", "pools": ["velocity"], "initial_values": {}}), encoding="utf-8"
    )

    loader = ArchetypeLoader(archetypes_dir)
    with pytest.raises(ArchetypeDefinitionError):
        loader.load_and_register_all(world)
