# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import zlib

from ouroboros.core.stable_id import stable_id_from_name


def test_stable_id_is_deterministic_across_calls():
    assert stable_id_from_name("hit_perfect") == stable_id_from_name("hit_perfect")


def test_stable_id_differs_for_different_names():
    assert stable_id_from_name("a") != stable_id_from_name("b")


def test_stable_id_matches_the_crc32_formula():
    assert stable_id_from_name("player_sprite") == (zlib.crc32("player_sprite".encode("utf-8")) & 0x7FFFFFFF)


def test_stable_id_is_always_non_negative():
    for name in ("a", "b", "some_longer_name", "", "🎮"):
        assert stable_id_from_name(name) >= 0
