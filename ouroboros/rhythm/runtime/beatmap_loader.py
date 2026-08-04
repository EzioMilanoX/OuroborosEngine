# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le beatmap.json e produz um array SCHEDULED_THREAT_DTYPE pronto para consumo vetorizado."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np

from ouroboros.rhythm.beatmap_format import (
    BEATMAP_SCHEMA_VERSION,
    REQUIRED_ROOT_FIELDS,
    REQUIRED_THREAT_FIELDS,
)
from ouroboros.rhythm.runtime.schemas import SCHEDULED_THREAT_DTYPE


class BeatmapFormatError(Exception):
    """Levantado quando o `beatmap.json` tem uma versao de schema
    desconhecida (diferente de `BEATMAP_SCHEMA_VERSION` importada de
    `ouroboros.rhythm.beatmap_format`) ou esta estruturalmente
    inconsistente.
    """


class BeatmapLoader:
    """Le `beatmap.json` e produz um array `SCHEDULED_THREAT_DTYPE`
    pronto para consumo vetorizado pelo `RhythmSpawnerSystem`.

    Invariante de fronteira: este modulo importa
    `BEATMAP_SCHEMA_VERSION`/`REQUIRED_*_FIELDS` EXCLUSIVAMENTE de
    `ouroboros.rhythm.beatmap_format` -- NUNCA de
    `ouroboros.rhythm.offline.beatmap_schema` nem de qualquer outro
    modulo do pacote `offline`. Isso evita que importar este modulo no
    processo de jogo shippado arraste transitivamente a dependencia
    pesada de librosa que o pipeline offline usa.

    Invariante Zero-GC: `load()` roda inteiramente FORA do loop de
    gameplay (durante o carregamento da fase/nivel, antes de qualquer
    `ISystem.update` ser chamado). O array resultante e ORDENADO por
    `timestamp_seconds` -- pre-condicao exigida por
    `RhythmSpawnerSystem`, que faz busca vetorizada assumindo ordenacao
    -- e tem tamanho FIXO igual ao numero de ameacas do beatmap. Nenhuma
    entidade "Event" Python e criada: apenas linhas de um unico array
    estruturado contiguo, alocado uma vez.
    """

    DEFAULT_LAYER_NAME_TO_ID: Dict[str, int] = {"": 0, "kick": 0, "vocal": 1}
    """Mapeamento padrao da tag opcional `layer` (Perfis de Extracao)
    para o inteiro de `SCHEDULED_THREAT_DTYPE['layer']`. Camada
    desconhecida cai em 0 (comportamento legado, nunca um erro)."""

    def __init__(
        self,
        threat_type_name_to_id: Dict[str, int],
        layer_name_to_id: Dict[str, int] = None,
    ) -> None:
        """Recebe o mapeamento (data-driven, carregado antes deste ponto)
        de nome de tipo de ameaca (string, como aparece no JSON) para o
        inteiro usado em `SCHEDULED_THREAT_DTYPE['threat_type']`, e
        opcionalmente o mapeamento das tags de camada.
        """
        self._threat_type_name_to_id = dict(threat_type_name_to_id)
        self._layer_name_to_id = dict(
            layer_name_to_id if layer_name_to_id is not None else self.DEFAULT_LAYER_NAME_TO_ID
        )

    def load(self, beatmap_path: Path) -> np.ndarray:
        """Le e desserializa `beatmap_path`, valida a versao de schema
        (contra `BEATMAP_SCHEMA_VERSION` de `beatmap_format`), e
        retorna um array `SCHEDULED_THREAT_DTYPE` ordenado por
        `timestamp_seconds`.

        Levanta `BeatmapFormatError` se a versao do schema for
        desconhecida, se um `threat_type` nao constar em
        `threat_type_name_to_id`, ou se a lista de ameacas nao puder
        ser normalizada de forma deterministica.
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
            for field in REQUIRED_THREAT_FIELDS:
                if field not in threat:
                    raise BeatmapFormatError(f"threats[{i}] missing required field '{field}'")
            if threat["threat_type"] not in self._threat_type_name_to_id:
                raise BeatmapFormatError(
                    f"threats[{i}] has unknown threat_type '{threat['threat_type']}' "
                    f"(not present in threat_type_name_to_id mapping)"
                )

        sorted_threats = sorted(threats, key=lambda threat: threat["timestamp_seconds"])

        scheduled_threats = np.zeros(len(sorted_threats), dtype=SCHEDULED_THREAT_DTYPE)
        for row_index, threat in enumerate(sorted_threats):
            scheduled_threats[row_index]["timestamp_seconds"] = threat["timestamp_seconds"]
            scheduled_threats[row_index]["threat_type"] = self._threat_type_name_to_id[threat["threat_type"]]
            scheduled_threats[row_index]["lane"] = threat["lane"]
            scheduled_threats[row_index]["strength"] = threat["strength"]
            scheduled_threats[row_index]["layer"] = self._layer_name_to_id.get(threat.get("layer", ""), 0)
            scheduled_threats[row_index]["has_spawned"] = False

        return scheduled_threats
