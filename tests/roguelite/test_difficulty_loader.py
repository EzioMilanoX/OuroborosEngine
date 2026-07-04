"""Testes de DifficultyLoader (Pilar 3): carga real de data/difficulties."""
from __future__ import annotations

from pathlib import Path

import pytest

from ouroboros.roguelite.loaders.difficulty_loader import DifficultyDefinitionError, DifficultyLoader

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_DIFFICULTIES_DIR = REPO_ROOT / "data" / "difficulties"


def test_load_real_normal_difficulty() -> None:
    loader = DifficultyLoader(REAL_DIFFICULTIES_DIR)
    data = loader.load("normal")

    assert data["name"] == "normal"
    assert data["enemy_health_multiplier"] == 1.0
    assert data["enemy_damage_multiplier"] == 1.0
    assert data["spawn_rate_multiplier"] == 1.0
    assert data["loot_rarity_bias"] == 0.0


def test_list_available_discovers_files_not_hardcoded() -> None:
    loader = DifficultyLoader(REAL_DIFFICULTIES_DIR)
    available = loader.list_available()

    assert "normal" in available
    assert isinstance(available, tuple)


def test_load_missing_difficulty_raises() -> None:
    loader = DifficultyLoader(REAL_DIFFICULTIES_DIR)
    with pytest.raises(DifficultyDefinitionError):
        loader.load("does_not_exist")


def test_load_malformed_json_raises(tmp_path) -> None:
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    loader = DifficultyLoader(tmp_path)
    with pytest.raises(DifficultyDefinitionError):
        loader.load("broken")


def test_list_available_reflects_directory_contents(tmp_path) -> None:
    (tmp_path / "easy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "hard.json").write_text("{}", encoding="utf-8")
    loader = DifficultyLoader(tmp_path)

    assert loader.list_available() == ("easy", "hard")
