# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de RhythmDifficultyLoader (Pilar 4): carga real de data/difficulties/rhythm."""
from __future__ import annotations

from pathlib import Path

import pytest

from ouroboros.rhythm.loaders.rhythm_difficulty_loader import (
    RhythmDifficultyDefinitionError,
    RhythmDifficultyLoader,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_RHYTHM_DIFFICULTIES_DIR = REPO_ROOT / "data" / "difficulties" / "rhythm"


def test_load_real_rhythm_normal_difficulty() -> None:
    loader = RhythmDifficultyLoader(REAL_RHYTHM_DIFFICULTIES_DIR)
    data = loader.load("rhythm_normal")

    assert data["name"] == "rhythm_normal"
    assert data["perfect_window_seconds"] == 0.05
    assert data["good_window_seconds"] == 0.10
    assert data["miss_window_seconds"] == 0.15


def test_list_available_discovers_files_not_hardcoded() -> None:
    loader = RhythmDifficultyLoader(REAL_RHYTHM_DIFFICULTIES_DIR)
    available = loader.list_available()

    assert "rhythm_normal" in available
    assert isinstance(available, tuple)


def test_list_available_never_picks_up_the_roguelites_sibling_directory() -> None:
    """A subpasta rhythm/ existe exatamente pra evitar que uma varredura
    aqui pegue o normal.json do Roguelite, que vive em data/difficulties/
    (nivel acima) e nao tem nenhuma das chaves que o Jogo Musical espera."""
    loader = RhythmDifficultyLoader(REAL_RHYTHM_DIFFICULTIES_DIR)
    available = loader.list_available()

    assert "normal" not in available


def test_load_missing_difficulty_raises() -> None:
    loader = RhythmDifficultyLoader(REAL_RHYTHM_DIFFICULTIES_DIR)
    with pytest.raises(RhythmDifficultyDefinitionError):
        loader.load("does_not_exist")


def test_load_malformed_json_raises(tmp_path) -> None:
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    loader = RhythmDifficultyLoader(tmp_path)
    with pytest.raises(RhythmDifficultyDefinitionError):
        loader.load("broken")


def test_list_available_reflects_directory_contents(tmp_path) -> None:
    (tmp_path / "easy.json").write_text("{}", encoding="utf-8")
    (tmp_path / "hard.json").write_text("{}", encoding="utf-8")
    loader = RhythmDifficultyLoader(tmp_path)

    assert loader.list_available() == ("easy", "hard")
