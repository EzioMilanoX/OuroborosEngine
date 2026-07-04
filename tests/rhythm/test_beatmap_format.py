"""Sanity check dos campos/versao neutros compartilhados por offline e runtime."""
from __future__ import annotations

from ouroboros.rhythm.beatmap_format import (
    BEATMAP_SCHEMA_VERSION,
    REQUIRED_ROOT_FIELDS,
    REQUIRED_THREAT_FIELDS,
)


def test_schema_version_is_positive_int():
    assert isinstance(BEATMAP_SCHEMA_VERSION, int)
    assert BEATMAP_SCHEMA_VERSION >= 1


def test_required_root_fields_contains_expected_keys():
    assert isinstance(REQUIRED_ROOT_FIELDS, tuple)
    for field in ("version", "track_id", "bpm", "threats"):
        assert field in REQUIRED_ROOT_FIELDS


def test_required_threat_fields_contains_expected_keys():
    assert isinstance(REQUIRED_THREAT_FIELDS, tuple)
    for field in ("timestamp_seconds", "threat_type", "lane", "strength"):
        assert field in REQUIRED_THREAT_FIELDS


def test_no_duplicate_fields():
    assert len(REQUIRED_ROOT_FIELDS) == len(set(REQUIRED_ROOT_FIELDS))
    assert len(REQUIRED_THREAT_FIELDS) == len(set(REQUIRED_THREAT_FIELDS))
