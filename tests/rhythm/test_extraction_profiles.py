# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Perfis de Extracao: groove ouve o bumbo, vocal_shred ouve a melodia, hybrid tagueia as camadas."""
import numpy as np
import pytest

from ouroboros.rhythm.offline.audio_loader import AudioLoader
from ouroboros.rhythm.offline.beatmap_schema import BeatmapValidator, ScheduledThreatDefinition
from ouroboros.rhythm.offline.extraction_profiles import (
    EXTRACTION_PROFILES,
    LAYER_KICK,
    LAYER_VOCAL,
    estimate_bpm_from_pulses,
    extract_with_profile,
    select_curve_peaks,
)
from ouroboros.rhythm.runtime.beatmap_loader import BeatmapLoader


def _kick_plus_lead(bpm=120.0, seconds=8.0, sample_rate=22050):
    """Mix guiado pela MELODIA (o caso de uso do vocal_shred): lead agudo
    forte em colcheias DESLOCADAS + bumbo grave curto e mais baixo em
    cada batida. Cada perfil deve ouvir a sua metade."""
    n = int(seconds * sample_rate)
    mix = np.zeros(n)
    beat = 60.0 / bpm

    kick_len = int(0.08 * sample_rate)
    tt = np.arange(kick_len) / sample_rate
    kick = np.exp(-tt * 42.0) * np.sin(2 * np.pi * np.cumsum(120.0 * np.exp(-tt * 22.0) + 45.0) / sample_rate)
    for start_s in np.arange(0.5, seconds - 0.2, beat):
        s = int(start_s * sample_rate)
        mix[s : s + kick_len] += 0.5 * kick[: max(0, min(kick_len, n - s))]

    lead_len = int(0.15 * sample_rate)
    lt = np.arange(lead_len) / sample_rate
    for i, start_s in enumerate(np.arange(0.5 + beat / 2, seconds - 0.2, beat)):
        s = int(start_s * sample_rate)
        freq = (880.0, 1108.7, 1318.5)[i % 3]
        note = np.exp(-lt * 22.0) * np.sin(2 * np.pi * freq * lt)
        mix[s : s + lead_len] += 0.85 * note[: max(0, min(lead_len, n - s))]

    mix /= np.max(np.abs(mix)) * 1.05

    class _Audio:
        pass

    audio = _Audio()
    audio.samples = mix.astype(np.float32)
    audio.sample_rate = sample_rate
    return audio


def test_unknown_profile_is_rejected():
    with pytest.raises(ValueError):
        extract_with_profile(_kick_plus_lead(seconds=1.0), "techno_ultra")


def test_groove_profile_returns_kick_layer_with_pulse_grid():
    result = extract_with_profile(_kick_plus_lead(), "groove")
    assert result.profile == "groove"
    assert [layer.layer for layer in result.layers] == [LAYER_KICK]
    kick = result.layers[0]
    assert kick.pulse_timestamps_seconds.shape[0] >= 6
    assert abs(estimate_bpm_from_pulses(kick.pulse_timestamps_seconds) - 120.0) < 12.0


def test_vocal_shred_hears_the_offbeat_lead_not_the_kick_grid():
    result = extract_with_profile(_kick_plus_lead(), "vocal_shred")
    assert [layer.layer for layer in result.layers] == [LAYER_VOCAL]
    vocal = result.layers[0]
    assert vocal.pulse_timestamps_seconds.shape[0] == 0  # sem PLP: abraca a sincopa
    assert vocal.onset_timestamps_seconds.shape[0] >= 6
    # os onsets vocais caem nas COLCHEIAS deslocadas (lead), nao nas batidas do bumbo
    lead_times = np.arange(0.75, 7.8, 0.5)
    near_lead = sum(
        1 for t in vocal.onset_timestamps_seconds if np.min(np.abs(lead_times - t)) < 0.07
    )
    assert near_lead >= 0.55 * vocal.onset_timestamps_seconds.shape[0]
    # e nao degenera em metralhadora de ruido nem em silencio
    assert 8 <= vocal.onset_timestamps_seconds.shape[0] <= 45


def test_hybrid_returns_both_layers_tagged():
    result = extract_with_profile(_kick_plus_lead(), "hybrid")
    assert [layer.layer for layer in result.layers] == [LAYER_KICK, LAYER_VOCAL]
    assert result.layers[0].onset_timestamps_seconds.shape[0] > 0
    assert result.layers[1].onset_timestamps_seconds.shape[0] > 0


def test_layer_tag_roundtrips_schema_and_runtime_loader(tmp_path):
    """A tag `layer` atravessa o pipeline inteiro: dict -> validacao ->
    JSON -> loader de runtime (string -> inteiro), com beatmaps legados
    (sem o campo) continuando validos."""
    validator = BeatmapValidator()
    beatmap_dict = validator.build_beatmap_dict(
        track_id="t",
        bpm=120.0,
        threats=(
            ScheduledThreatDefinition(1.0, "basic", 0, 0.5, layer="kick"),
            ScheduledThreatDefinition(2.0, "basic", 1, 0.5, layer="vocal"),
            ScheduledThreatDefinition(3.0, "basic", 2, 0.5),  # legado: sem layer
        ),
    )
    validator.validate(beatmap_dict)  # inclui a checagem de tipo da tag

    import json
    path = tmp_path / "b.json"
    path.write_text(json.dumps(beatmap_dict), encoding="utf-8")
    scheduled = BeatmapLoader({"basic": 0}).load(path)
    assert scheduled["layer"].tolist() == [0, 1, 0]  # kick=0, vocal=1, ""=0


def test_all_profiles_are_exposed():
    assert set(EXTRACTION_PROFILES) == {"groove", "vocal_shred", "hybrid"}
