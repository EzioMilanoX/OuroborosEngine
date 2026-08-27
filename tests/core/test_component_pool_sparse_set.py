# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

import numpy as np
import pytest

from ouroboros.core.constants import INVALID_DENSE_ROW
from ouroboros.core.memory.component_pool import ComponentPool, intersect_entity_indices

POINT_DTYPE = np.dtype([("x", np.float32), ("y", np.float32)])


def make_pool(dense_capacity=8, entity_capacity=16):
    return ComponentPool(dtype=POINT_DTYPE, dense_capacity=dense_capacity, entity_capacity=entity_capacity)


def test_attach_returns_sequential_dense_rows():
    pool = make_pool()
    assert pool.attach(3) == 0
    assert pool.attach(5) == 1
    assert pool.count == 2
    assert pool.is_attached(3)
    assert pool.is_attached(5)
    assert not pool.is_attached(4)


def test_attach_twice_raises():
    pool = make_pool()
    pool.attach(3)
    with pytest.raises(ValueError):
        pool.attach(3)


def test_attach_beyond_capacity_raises():
    pool = make_pool(dense_capacity=2, entity_capacity=16)
    pool.attach(0)
    pool.attach(1)
    with pytest.raises(IndexError):
        pool.attach(2)


def test_detach_is_noop_when_not_attached():
    pool = make_pool()
    pool.detach(9)  # should not raise
    assert pool.count == 0


def test_detach_swap_remove_keeps_dense_prefix_contiguous():
    pool = make_pool()
    pool.attach(1)
    pool.attach(2)
    pool.attach(3)
    pool.active_view()["x"] = [10.0, 20.0, 30.0]

    pool.detach(1)  # removes first row, swaps last (entity 3) into its place

    assert pool.count == 2
    assert not pool.is_attached(1)
    assert pool.is_attached(2)
    assert pool.is_attached(3)

    # entity 3's data must have moved to row 0, entity 2 stays at row 1
    row3 = pool.dense_row_of(3)
    row2 = pool.dense_row_of(2)
    assert pool.active_view()["x"][row3] == 30.0
    assert pool.active_view()["x"][row2] == 20.0


def test_active_view_and_active_entity_indices_stay_parallel():
    pool = make_pool()
    for entity_index, value in [(4, 1.0), (7, 2.0), (2, 3.0)]:
        row = pool.attach(entity_index)
        pool.active_view()["x"][row] = value

    values_by_entity = dict(zip(pool.active_entity_indices().tolist(), pool.active_view()["x"].tolist()))
    assert values_by_entity == {4: 1.0, 7: 2.0, 2: 3.0}


def test_dense_row_of_unattached_entity_is_invalid_row():
    pool = make_pool()
    assert pool.dense_row_of(0) == INVALID_DENSE_ROW


def test_attach_default_leaves_recycled_row_dirty():
    """Comportamento antigo (default `clear=False`): uma linha densa reciclada
    de um swap-remove anterior mantem o lixo do ocupante antigo se o chamador
    nao escrever aquele campo por conta propria."""
    pool = make_pool()
    row_a = pool.attach(1)
    pool.active_view()["x"][row_a] = 99.0
    pool.active_view()["y"][row_a] = 42.0
    pool.detach(1)  # linha 0 fica livre, com x=99.0/y=42.0 ainda no array denso

    row_b = pool.attach(2)  # recicla a mesma linha densa
    assert row_b == row_a
    assert pool.active_view()["x"][row_b] == 99.0  # lixo do ocupante antigo, nao escrito
    assert pool.active_view()["y"][row_b] == 42.0


def test_attach_clear_true_zeroes_recycled_row():
    """`clear=True` elimina a classe de bug acima: a linha reciclada vem zerada."""
    pool = make_pool()
    row_a = pool.attach(1)
    pool.active_view()["x"][row_a] = 99.0
    pool.active_view()["y"][row_a] = 42.0
    pool.detach(1)

    row_b = pool.attach(2, clear=True)
    assert pool.active_view()["x"][row_b] == 0.0
    assert pool.active_view()["y"][row_b] == 0.0


def test_attach_clear_true_on_a_fresh_never_used_row_is_still_zero():
    pool = make_pool()
    row = pool.attach(1, clear=True)
    assert pool.active_view()["x"][row] == 0.0
    assert pool.active_view()["y"][row] == 0.0


def test_intersect_entity_indices_across_two_pools():
    pool_a = make_pool()
    pool_b = make_pool()
    for e in (1, 2, 3, 4):
        pool_a.attach(e)
    for e in (2, 4, 6):
        pool_b.attach(e)

    result = intersect_entity_indices(pool_a, pool_b)
    assert sorted(result.tolist()) == [2, 4]


def test_intersect_entity_indices_with_no_overlap_is_empty():
    pool_a = make_pool()
    pool_b = make_pool()
    pool_a.attach(1)
    pool_b.attach(2)
    result = intersect_entity_indices(pool_a, pool_b)
    assert result.size == 0


def test_intersect_entity_indices_three_pools():
    pool_a, pool_b, pool_c = make_pool(), make_pool(), make_pool()
    for e in (1, 2, 3):
        pool_a.attach(e)
    for e in (2, 3, 4):
        pool_b.attach(e)
    for e in (3, 4, 5):
        pool_c.attach(e)
    result = intersect_entity_indices(pool_a, pool_b, pool_c)
    assert sorted(result.tolist()) == [3]
