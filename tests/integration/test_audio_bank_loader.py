# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testa load_audio_bank: registra tone/file no IAudioEngine, tudo-ou-nada na validacao."""
from __future__ import annotations

import json

import pytest

from ouroboros.bootstrap.audio_bank_loader import AudioBankDefinitionError, load_audio_bank


def _write_bank(tmp_path, data: dict) -> str:
    path = tmp_path / "bank.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


def test_tone_entry_registers_via_register_tone(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {
        "hit": {"type": "tone", "kind": "zap", "freq": 900.0, "duration": 0.05},
    })

    loaded = load_audio_bank(null_audio_engine, bank_path)

    assert loaded == frozenset({"hit"})
    assert null_audio_engine._registered_tones["hit"] == ("zap", 900.0, 0.05)


def test_tone_entry_defaults_kind_to_square(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {
        "hit": {"type": "tone", "freq": 440.0, "duration": 0.1},
    })

    load_audio_bank(null_audio_engine, bank_path)

    assert null_audio_engine._registered_tones["hit"] == ("square", 440.0, 0.1)


def test_file_entry_registers_via_load_sound(tmp_path, null_audio_engine, synthetic_wav_factory):
    audio_path = synthetic_wav_factory(bpm=100.0, duration_seconds=0.2)
    bank_path = _write_bank(tmp_path, {
        "explosion": {"type": "file", "path": audio_path},
    })

    loaded = load_audio_bank(null_audio_engine, bank_path)

    assert loaded == frozenset({"explosion"})
    assert null_audio_engine._loaded_sounds["explosion"] == audio_path


def test_multiple_entries_all_registered(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {
        "a": {"type": "tone", "kind": "square", "freq": 440.0, "duration": 0.1},
        "b": {"type": "tone", "kind": "noise", "freq": 200.0, "duration": 0.1},
    })

    loaded = load_audio_bank(null_audio_engine, bank_path)

    assert loaded == frozenset({"a", "b"})


def test_unknown_type_raises_and_registers_nothing(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {
        "a": {"type": "tone", "kind": "square", "freq": 440.0, "duration": 0.1},
        "b": {"type": "synth", "kind": "square", "freq": 440.0, "duration": 0.1},
    })

    with pytest.raises(AudioBankDefinitionError):
        load_audio_bank(null_audio_engine, bank_path)

    assert null_audio_engine._registered_tones == {}  # nada registrado -- tudo ou nada


def test_unknown_tone_kind_raises_and_registers_nothing(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {
        "a": {"type": "tone", "kind": "square", "freq": 440.0, "duration": 0.1},
        "b": {"type": "tone", "kind": "sqare", "freq": 440.0, "duration": 0.1},  # typo proposital
    })

    with pytest.raises(AudioBankDefinitionError):
        load_audio_bank(null_audio_engine, bank_path)

    assert null_audio_engine._registered_tones == {}


def test_missing_required_field_raises(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {
        "a": {"type": "tone", "kind": "square", "freq": 440.0},  # falta 'duration'
    })

    with pytest.raises(AudioBankDefinitionError):
        load_audio_bank(null_audio_engine, bank_path)


def test_file_entry_missing_path_raises(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {
        "a": {"type": "file"},
    })

    with pytest.raises(AudioBankDefinitionError):
        load_audio_bank(null_audio_engine, bank_path)


def test_malformed_json_raises(tmp_path, null_audio_engine):
    path = tmp_path / "bank.json"
    path.write_text("{not valid json", encoding="utf-8")

    with pytest.raises(AudioBankDefinitionError):
        load_audio_bank(null_audio_engine, str(path))


def test_entry_missing_type_raises(tmp_path, null_audio_engine):
    bank_path = _write_bank(tmp_path, {"a": {"kind": "square"}})

    with pytest.raises(AudioBankDefinitionError):
        load_audio_bank(null_audio_engine, bank_path)
