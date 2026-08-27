# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa `split_spawn_and_hit_schedules`: separacao de tempo-de-spawn vs tempo-de-acerto."""
from __future__ import annotations

import numpy as np

from ouroboros.rhythm.runtime.approach_schedule import split_spawn_and_hit_schedules
from ouroboros.rhythm.runtime.schemas import SCHEDULED_THREAT_DTYPE


def _build_scheduled_threats() -> np.ndarray:
    timestamps = [0.5, 2.0, 10.0]
    lanes = [0, 1, 2]
    threat_types = [0, 1, 0]

    scheduled = np.zeros(len(timestamps), dtype=SCHEDULED_THREAT_DTYPE)
    scheduled["timestamp_seconds"] = timestamps
    scheduled["lane"] = lanes
    scheduled["threat_type"] = threat_types
    scheduled["strength"] = 0.5
    scheduled["has_spawned"] = False
    return scheduled


def test_hit_times_matches_original_timestamps_exactly():
    scheduled = _build_scheduled_threats()
    _, hit_times = split_spawn_and_hit_schedules(scheduled, approach_seconds=1.5)

    np.testing.assert_array_equal(hit_times, [0.5, 2.0, 10.0])


def test_spawn_threats_timestamp_is_shifted_back_by_approach_seconds():
    scheduled = _build_scheduled_threats()
    spawn_threats, _ = split_spawn_and_hit_schedules(scheduled, approach_seconds=1.5)

    # 0.5 - 1.5 = -1.0 -> clamped a 0.0; os demais so deslocados.
    np.testing.assert_allclose(spawn_threats["timestamp_seconds"], [0.0, 0.5, 8.5])


def test_spawn_timestamp_is_clamped_at_zero_never_negative():
    scheduled = _build_scheduled_threats()
    spawn_threats, _ = split_spawn_and_hit_schedules(scheduled, approach_seconds=100.0)

    assert np.all(spawn_threats["timestamp_seconds"] >= 0.0)
    np.testing.assert_array_equal(spawn_threats["timestamp_seconds"], [0.0, 0.0, 0.0])


def test_other_fields_preserved_intact_in_spawn_threats():
    scheduled = _build_scheduled_threats()
    spawn_threats, _ = split_spawn_and_hit_schedules(scheduled, approach_seconds=1.5)

    np.testing.assert_array_equal(spawn_threats["lane"], scheduled["lane"])
    np.testing.assert_array_equal(spawn_threats["threat_type"], scheduled["threat_type"])
    np.testing.assert_array_equal(spawn_threats["strength"], scheduled["strength"])


def test_original_array_is_never_mutated():
    scheduled = _build_scheduled_threats()
    original_timestamps = scheduled["timestamp_seconds"].copy()

    split_spawn_and_hit_schedules(scheduled, approach_seconds=1.5)

    np.testing.assert_array_equal(scheduled["timestamp_seconds"], original_timestamps)


def test_empty_scheduled_threats_returns_empty_arrays():
    empty_scheduled = np.zeros(0, dtype=SCHEDULED_THREAT_DTYPE)
    spawn_threats, hit_times = split_spawn_and_hit_schedules(empty_scheduled, approach_seconds=1.5)

    assert spawn_threats.shape[0] == 0
    assert hit_times.shape[0] == 0
