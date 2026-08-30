"""Testa games.platformer.level.load_level: parsing do ASCII, validacao do ponto de spawn."""
from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest

import games.platformer.level as level_module
from ouroboros.core.grid2d import Grid2D
from games.platformer.level import LevelDefinitionError, load_level


def test_load_level_parses_the_real_hardcoded_level():
    level = load_level(cell_size=32.0)

    assert level.grid.cols == 20
    assert level.grid.rows == 10
    assert not level.grid.is_solid([level.spawn_x], [level.spawn_y])[0]
    assert len(level.solid_cell_centers) == 25  # 5 da plataforma + 20 do chao


def test_load_level_raises_on_mismatched_row_lengths():
    with patch.object(level_module, "LEVEL_ROWS", ("....", "...")):
        with pytest.raises(LevelDefinitionError):
            load_level()


def test_load_level_raises_on_unknown_character():
    with patch.object(level_module, "LEVEL_ROWS", ("..X.",)):
        with pytest.raises(LevelDefinitionError):
            load_level()


def test_load_level_raises_when_spawn_point_is_missing():
    with patch.object(level_module, "LEVEL_ROWS", ("....", "####")):
        with pytest.raises(LevelDefinitionError):
            load_level()


def test_load_level_raises_when_more_than_one_spawn_point_exists():
    with patch.object(level_module, "LEVEL_ROWS", ("P.P.",)):
        with pytest.raises(LevelDefinitionError):
            load_level()


def test_load_level_raises_when_spawn_point_is_inside_a_solid_cell(monkeypatch):
    """Defesa em profundidade: o parser ASCII atual nunca produz essa
    situacao de verdade sozinho ('P' e '#' sao caracteres mutuamente
    exclusivos por celula), mas a checagem existe pra qualquer fonte de
    nivel futura que nao garanta isso por construcao -- forca
    Grid2D.is_solid a responder True pra provar que o guard dispara."""
    monkeypatch.setattr(Grid2D, "is_solid", lambda self, x, y: np.array([True]))

    with pytest.raises(LevelDefinitionError):
        load_level()
