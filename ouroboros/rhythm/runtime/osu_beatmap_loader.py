# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le beatmap.json de modo Osu! e produz um array OSU_SCHEDULED_HIT_DTYPE pronto para consumo vetorizado."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np

from ouroboros.rhythm.beatmap_format import (
    BEATMAP_SCHEMA_VERSION,
    REQUIRED_OSU_HIT_OBJECT_FIELDS,
    REQUIRED_ROOT_FIELDS,
)
from ouroboros.rhythm.runtime.beatmap_loader import BeatmapFormatError, BeatmapLoader
from ouroboros.rhythm.runtime.schemas import OSU_SCHEDULED_HIT_DTYPE


class OsuBeatmapLoader:
    """Le `*.beatmap.json` de modo Osu! e produz um array
    `OSU_SCHEDULED_HIT_DTYPE` pronto para consumo vetorizado pelo
    `OsuSpawnerSystem`. Mesma invariante de fronteira de `BeatmapLoader`:
    importa `BEATMAP_SCHEMA_VERSION`/`REQUIRED_*_FIELDS` exclusivamente
    de `ouroboros.rhythm.beatmap_format` -- NUNCA de
    `ouroboros.rhythm.offline.*` (evita arrastar a dependencia pesada de
    librosa para o processo de jogo shippado). Reusa `BeatmapFormatError`
    (nao um tipo de excecao novo -- mesma familia de erro de carregamento
    de beatmap, so o schema de cada entrada diverge).

    Invariante Zero-GC: `load()` roda inteiramente FORA do loop de
    gameplay, igual a `BeatmapLoader.load()`.
    """

    def __init__(
        self,
        threat_type_name_to_id: Dict[str, int],
        slider_threat_type_id: int,
        layer_name_to_id: Dict[str, int] = None,
    ) -> None:
        """`threat_type_name_to_id`: mapeamento (data-driven, definido
        pela composicao do jogo) de nome de tipo (string, como aparece
        no JSON -- ex.: `"osu_circle"`/`"osu_slider"`) para o inteiro
        usado em `OSU_SCHEDULED_HIT_DTYPE['threat_type']`.
        `slider_threat_type_id`: qual dos inteiros resolvidos acima
        denota um SLIDER -- usado apenas para decidir quando exigir
        `end_x`/`end_y`/`duration_seconds` (um CIRCLE nunca os tem).
        """
        self._threat_type_name_to_id = dict(threat_type_name_to_id)
        self._slider_threat_type_id = int(slider_threat_type_id)
        self._layer_name_to_id = dict(
            layer_name_to_id if layer_name_to_id is not None else BeatmapLoader.DEFAULT_LAYER_NAME_TO_ID
        )

    def load(self, beatmap_path: Path) -> np.ndarray:
        """Le e desserializa `beatmap_path`, valida a versao de schema e
        os campos obrigatorios de cada hit-object (exigindo
        `end_x`/`end_y`/`duration_seconds` quando o `threat_type`
        resolvido for `slider_threat_type_id`), e retorna um array
        `OSU_SCHEDULED_HIT_DTYPE` ordenado por `timestamp_seconds`.

        Levanta `BeatmapFormatError` se a versao do schema for
        desconhecida, se um `threat_type` nao constar em
        `threat_type_name_to_id`, se um slider estiver sem seus campos
        obrigatorios, ou se a lista de hit-objects nao puder ser
        normalizada de forma deterministica.
        """
        beatmap_path = Path(beatmap_path)
        try:
            with open(beatmap_path, "r", encoding="utf-8") as beatmap_file:
                beatmap_dict = json.load(beatmap_file)
        except (OSError, json.JSONDecodeError) as exc:
            raise BeatmapFormatError(f"failed to read beatmap file {beatmap_path}: {exc}") from exc

        if not isinstance(beatmap_dict, dict):
            raise BeatmapFormatError(f"beatmap document must be a JSON object, got {type(beatmap_dict).__name__}")

        for field in REQUIRED_ROOT_FIELDS:
            if field not in beatmap_dict:
                raise BeatmapFormatError(f"beatmap document missing required field '{field}'")

        version = beatmap_dict["version"]
        if version != BEATMAP_SCHEMA_VERSION:
            raise BeatmapFormatError(
                f"unsupported beatmap schema version: expected {BEATMAP_SCHEMA_VERSION}, got {version!r}"
            )

        threats = beatmap_dict["threats"]
        if not isinstance(threats, list):
            raise BeatmapFormatError(f"beatmap 'threats' must be a list, got {type(threats).__name__}")

        for i, threat in enumerate(threats):
            if not isinstance(threat, dict):
                raise BeatmapFormatError(f"threats[{i}] must be a JSON object, got {type(threat).__name__}")
            for field in REQUIRED_OSU_HIT_OBJECT_FIELDS:
                if field not in threat:
                    raise BeatmapFormatError(f"threats[{i}] missing required field '{field}'")
            if threat["threat_type"] not in self._threat_type_name_to_id:
                raise BeatmapFormatError(
                    f"threats[{i}] has unknown threat_type '{threat['threat_type']}' "
                    f"(not present in threat_type_name_to_id mapping)"
                )
            resolved_type = self._threat_type_name_to_id[threat["threat_type"]]
            if resolved_type == self._slider_threat_type_id:
                for slider_field in ("end_x", "end_y", "duration_seconds"):
                    if slider_field not in threat:
                        raise BeatmapFormatError(
                            f"threats[{i}] e um slider (threat_type={threat['threat_type']!r}) "
                            f"sem campo obrigatorio '{slider_field}'"
                        )

        sorted_threats = sorted(threats, key=lambda threat: threat["timestamp_seconds"])

        scheduled_hits = np.zeros(len(sorted_threats), dtype=OSU_SCHEDULED_HIT_DTYPE)
        for row_index, threat in enumerate(sorted_threats):
            scheduled_hits[row_index]["timestamp_seconds"] = threat["timestamp_seconds"]
            scheduled_hits[row_index]["threat_type"] = self._threat_type_name_to_id[threat["threat_type"]]
            scheduled_hits[row_index]["x"] = threat["x"]
            scheduled_hits[row_index]["y"] = threat["y"]
            scheduled_hits[row_index]["end_x"] = threat.get("end_x", 0.0)
            scheduled_hits[row_index]["end_y"] = threat.get("end_y", 0.0)
            scheduled_hits[row_index]["duration_seconds"] = threat.get("duration_seconds", 0.0)
            scheduled_hits[row_index]["strength"] = threat["strength"]
            scheduled_hits[row_index]["layer"] = self._layer_name_to_id.get(threat.get("layer", ""), 0)
            scheduled_hits[row_index]["has_spawned"] = False

        return scheduled_hits
