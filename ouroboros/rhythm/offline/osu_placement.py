# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deriva posicoes x/y e sliders deterministicamente a partir de onsets JA extraidos -- nunca reanalisa audio."""
from __future__ import annotations

from typing import Optional, Sequence, Tuple

import numpy as np

from ouroboros.core.stable_id import stable_id_from_name
from ouroboros.rhythm.offline.osu_beatmap_schema import (
    OSU_CIRCLE_THREAT_TYPE_NAME,
    OSU_SLIDER_THREAT_TYPE_NAME,
    OsuHitObjectDefinition,
)

DEFAULT_MARGIN_PX = 60.0
DEFAULT_MIN_OBJECT_SPACING_PX = 80.0
DEFAULT_MAX_PLACEMENT_ATTEMPTS = 16
DEFAULT_SLIDER_EVERY_N = 4
DEFAULT_SLIDER_DURATION_BEATS = 1.0
DEFAULT_SLIDER_SAFETY_MARGIN_SECONDS = 0.05
DEFAULT_MIN_SLIDER_DURATION_SECONDS = 0.05


def place_hit_objects(
    threats: Sequence[dict],
    track_id: str,
    bpm: float,
    playfield_width: float,
    playfield_height: float,
    margin_px: float = DEFAULT_MARGIN_PX,
    min_object_spacing_px: float = DEFAULT_MIN_OBJECT_SPACING_PX,
    max_placement_attempts: int = DEFAULT_MAX_PLACEMENT_ATTEMPTS,
    slider_every_n: int = DEFAULT_SLIDER_EVERY_N,
    slider_duration_beats: float = DEFAULT_SLIDER_DURATION_BEATS,
    slider_safety_margin_seconds: float = DEFAULT_SLIDER_SAFETY_MARGIN_SECONDS,
) -> Tuple[OsuHitObjectDefinition, ...]:
    """Deriva `(x, y)` (e, para 1 a cada `slider_every_n` onsets, uma
    cauda `(end_x, end_y)` + `duration_seconds`) para cada entrada de
    `threats` -- entradas JA ORDENADAS de um `beatmap.json` lane-mode
    EXISTENTE (mesma forma de `threats` de um documento validado por
    `ouroboros.rhythm.runtime.beatmap_loader.BeatmapLoader`: cada dict
    tem pelo menos `timestamp_seconds`/`strength`, opcionalmente
    `layer`) -- reusa `timestamp_seconds`/`strength`/`layer` JA
    extraidos pelo pipeline offline, nunca reanalisa audio.

    DETERMINISMO: semeado por `track_id` via
    `stable_id_from_name(f"{track_id}:osu_placement")` (nao
    `hash()` nativo, que e aleatorizado por processo) -- a MESMA
    `track_id` sempre produz o MESMO layout entre execucoes.

    ALGORITMO:
        Para cada onset, em ordem: amostra `(x, y)` uniforme no
        playfield (menos `margin_px` de cada borda); se a distancia ao
        objeto anterior for menor que `min_object_spacing_px`,
        rejeita-e-reamostra ate `max_placement_attempts` vezes (NUNCA um
        laco sem limite -- se o teto for atingido, mantem o ultimo ponto
        amostrado, mesmo que ainda proximo demais: um layout um pouco
        apertado e preferivel a travar a geracao). A cada
        `slider_every_n`-esimo onset (por indice, nao por `strength` --
        o pipeline offline hoje nao produz `strength` variavel o
        bastante para um limiar significativo), o hit-object vira um
        SLIDER: a cauda e amostrada com a MESMA logica de espacamento
        (a partir da cabeca), e `duration_seconds` e derivada de
        `beat_seconds = 60.0 / bpm` (`slider_duration_beats` batidas),
        CLAMPADA contra o intervalo de tempo real ate o PROXIMO onset do
        `threats` de origem menos `slider_safety_margin_seconds` -- sem
        esse clamp, um slider poderia permanecer "ativo" (em tracking)
        alem do instante em que o proximo hit-object ja deveria ter sido
        clicado, sobrepondo as janelas de julgamento dos dois (achado
        real da critica de M15, verificado numericamente contra
        `data/beatmaps/demo_track.beatmap.json`: gaps de ~0.488s/0.511s
        entre onsets consecutivos, mais curtos que 1 batida inteira).

    Nao escreve em disco (ver `OsuBeatmapWriter`) nem valida (ver
    `OsuBeatmapValidator`) -- roda inteiramente fora do loop de
    gameplay, como ferramenta manual (`games/rhythm_game/tools/
    generate_osu_beatmap.py`).
    """
    if not threats:
        return ()

    rng = np.random.default_rng(np.random.SeedSequence(entropy=stable_id_from_name(f"{track_id}:osu_placement")))
    beat_seconds = 60.0 / float(bpm)
    nominal_slider_duration_seconds = slider_duration_beats * beat_seconds

    min_x, max_x = margin_px, max(margin_px + 1.0, playfield_width - margin_px)
    min_y, max_y = margin_px, max(margin_px + 1.0, playfield_height - margin_px)

    hit_objects = []
    previous_x: Optional[float] = None
    previous_y: Optional[float] = None
    for index, threat in enumerate(threats):
        x, y = _sample_position(
            rng, min_x, max_x, min_y, max_y, previous_x, previous_y, min_object_spacing_px, max_placement_attempts
        )
        is_slider = (index % slider_every_n) == (slider_every_n - 1)

        if is_slider:
            end_x, end_y = _sample_position(
                rng, min_x, max_x, min_y, max_y, x, y, min_object_spacing_px, max_placement_attempts
            )
            duration_seconds = nominal_slider_duration_seconds
            if index + 1 < len(threats):
                gap_to_next_seconds = float(threats[index + 1]["timestamp_seconds"]) - float(threat["timestamp_seconds"])
                duration_seconds = min(duration_seconds, gap_to_next_seconds - slider_safety_margin_seconds)
            duration_seconds = max(DEFAULT_MIN_SLIDER_DURATION_SECONDS, duration_seconds)

            hit_objects.append(
                OsuHitObjectDefinition(
                    timestamp_seconds=float(threat["timestamp_seconds"]),
                    threat_type=OSU_SLIDER_THREAT_TYPE_NAME,
                    x=x,
                    y=y,
                    strength=float(threat.get("strength", 0.0)),
                    layer=str(threat.get("layer", "")),
                    end_x=end_x,
                    end_y=end_y,
                    duration_seconds=duration_seconds,
                )
            )
            previous_x, previous_y = end_x, end_y
        else:
            hit_objects.append(
                OsuHitObjectDefinition(
                    timestamp_seconds=float(threat["timestamp_seconds"]),
                    threat_type=OSU_CIRCLE_THREAT_TYPE_NAME,
                    x=x,
                    y=y,
                    strength=float(threat.get("strength", 0.0)),
                    layer=str(threat.get("layer", "")),
                )
            )
            previous_x, previous_y = x, y

    return tuple(hit_objects)


def _sample_position(
    rng: np.random.Generator,
    min_x: float,
    max_x: float,
    min_y: float,
    max_y: float,
    avoid_x: Optional[float],
    avoid_y: Optional[float],
    min_spacing_px: float,
    max_attempts: int,
) -> Tuple[float, float]:
    """Amostra `(x, y)` uniforme no retangulo `[min_x,max_x] x
    [min_y,max_y]`; se `avoid_x`/`avoid_y` forem fornecidos, rejeita-e-
    reamostra ate `max_attempts` vezes enquanto a distancia for menor
    que `min_spacing_px` -- ao atingir o teto, retorna o ULTIMO ponto
    amostrado (nunca um laco sem limite)."""
    x = float(rng.uniform(min_x, max_x))
    y = float(rng.uniform(min_y, max_y))
    if avoid_x is None or avoid_y is None:
        return x, y

    min_spacing_sq = min_spacing_px * min_spacing_px
    attempts = 1
    while attempts < max_attempts and (x - avoid_x) ** 2 + (y - avoid_y) ** 2 < min_spacing_sq:
        x = float(rng.uniform(min_x, max_x))
        y = float(rng.uniform(min_y, max_y))
        attempts += 1
    return x, y
