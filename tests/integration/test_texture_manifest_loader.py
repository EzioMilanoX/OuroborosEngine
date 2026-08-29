# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa load_texture_manifest: registra cada entrada no IRenderer, com guarda de colisao de id."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ouroboros.bootstrap.texture_manifest_loader import load_texture_manifest
from ouroboros.core.stable_id import stable_id_from_name
from ouroboros.interfaces.renderer import SHAPE_MAX


def _write_manifest(tmp_path, data: dict) -> str:
    path = tmp_path / "textures.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_loads_every_entry_and_returns_the_names(tmp_path, null_renderer):
    manifest_path = _write_manifest(tmp_path, {"player": "player.png", "enemy": "enemy.png"})

    loaded = load_texture_manifest(null_renderer, manifest_path, textures_root=Path(tmp_path))

    assert loaded == frozenset({"player", "enemy"})
    assert null_renderer._loaded_textures[stable_id_from_name("player")] == str(Path(tmp_path) / "player.png")
    assert null_renderer._loaded_textures[stable_id_from_name("enemy")] == str(Path(tmp_path) / "enemy.png")


def test_resolves_paths_relative_to_textures_root(tmp_path, null_renderer):
    manifest_path = _write_manifest(tmp_path, {"player": "sprites/player.png"})
    textures_root = Path(tmp_path) / "assets"

    load_texture_manifest(null_renderer, manifest_path, textures_root=textures_root)

    expected_path = str(textures_root / "sprites/player.png")
    assert null_renderer._loaded_textures[stable_id_from_name("player")] == expected_path


def test_colliding_names_raise_before_registering_anything(tmp_path, null_renderer, monkeypatch):
    # Forca uma colisao artificial: duas entradas cujo `stable_id_from_name` bate.
    import ouroboros.bootstrap.texture_manifest_loader as loader_module

    monkeypatch.setattr(loader_module, "stable_id_from_name", lambda name: 42)
    manifest_path = _write_manifest(tmp_path, {"player": "player.png", "enemy": "enemy.png"})

    with pytest.raises(ValueError):
        load_texture_manifest(null_renderer, manifest_path, textures_root=Path(tmp_path))

    assert null_renderer._loaded_textures == {}


def test_texture_id_colliding_with_a_reserved_primitive_shape_id_raises_before_registering_anything(
    tmp_path, null_renderer, monkeypatch
):
    """PygameRenderer._draw_shape consulta a tabela de texturas carregadas ANTES do
    fallback pra SHAPE_RECT/CIRCLE/RING (0/1/2) -- uma colisao sequestraria
    silenciosamente o desenho de uma forma primitiva em QUALQUER produto."""
    import ouroboros.bootstrap.texture_manifest_loader as loader_module

    monkeypatch.setattr(loader_module, "stable_id_from_name", lambda name: SHAPE_MAX - 1)
    manifest_path = _write_manifest(tmp_path, {"player": "player.png", "enemy": "enemy.png"})

    with pytest.raises(ValueError):
        load_texture_manifest(null_renderer, manifest_path, textures_root=Path(tmp_path))

    assert null_renderer._loaded_textures == {}


def test_empty_manifest_returns_empty_set(tmp_path, null_renderer):
    manifest_path = _write_manifest(tmp_path, {})

    loaded = load_texture_manifest(null_renderer, manifest_path, textures_root=Path(tmp_path))

    assert loaded == frozenset()
    assert null_renderer._loaded_textures == {}
