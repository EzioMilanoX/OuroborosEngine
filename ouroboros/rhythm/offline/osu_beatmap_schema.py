# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Valida e monta o dict serializavel de beatmap Osu!, antes da escrita atomica. So importa beatmap_format."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from ouroboros.rhythm.beatmap_format import (
    BEATMAP_SCHEMA_VERSION,
    REQUIRED_OSU_HIT_OBJECT_FIELDS,
    REQUIRED_ROOT_FIELDS,
)

OSU_CIRCLE_THREAT_TYPE_NAME = "osu_circle"
OSU_SLIDER_THREAT_TYPE_NAME = "osu_slider"
"""Strings gravadas no beatmap.json pelo gerador offline (`osu_placement.py`)
-- mesmo espirito de `BEATMAP_THREAT_TYPE_NAME` em
`games/rhythm_game/composition.py` (uma constante local do jogo, nao um
nome de arquetipo ECS): `games/rhythm_game/osu/composition.py` define sua
PROPRIA constante local de runtime que, por convencao (nao por import
compartilhado), usa os MESMOS literais."""


class OsuBeatmapValidationError(Exception):
    """Levantado quando um dict de beatmap Osu! nao satisfaz o schema
    esperado: campo obrigatorio ausente, tipo incorreto, timestamps
    nao-ordenados, `strength` fora de `[0.0, 1.0]`, slider sem
    `end_x`/`end_y`/`duration_seconds`, versao desconhecida, etc. A
    mensagem deve identificar o PRIMEIRO problema encontrado.
    """


@dataclass(frozen=True)
class OsuHitObjectDefinition:
    """Representacao intermediaria (em memoria, offline) de UM hit-object
    Osu!, antes de ser serializado para JSON ou materializado em NumPy
    pelo `OsuBeatmapLoader` do runtime.

    Atributos:
        timestamp_seconds: instante de disparo (CIRCLE) ou de inicio do
            arraste (SLIDER, cabeca).
        threat_type: `OSU_CIRCLE_THREAT_TYPE_NAME` ou
            `OSU_SLIDER_THREAT_TYPE_NAME`.
        x, y: posicao da cabeca, em pixels de tela.
        strength: intensidade normalizada (`0.0`-`1.0`), copiada do
            beatmap lane-mode de origem.
        layer: tag OPCIONAL da camada de extracao (mesmo idioma de
            `ScheduledThreatDefinition.layer`).
        end_x, end_y, duration_seconds: SO relevantes para
            `OSU_SLIDER_THREAT_TYPE_NAME` (trajeto reta cabeca->cauda +
            duracao do arraste); permanecem `0.0` para um CIRCLE.
    """

    timestamp_seconds: float
    threat_type: str
    x: float
    y: float
    strength: float
    layer: str = ""
    end_x: float = 0.0
    end_y: float = 0.0
    duration_seconds: float = 0.0


class OsuBeatmapValidator:
    """Valida a estrutura de um dict de beatmap Osu! antes da escrita/leitura.

    Usado pelo escritor offline (`OsuBeatmapWriter`, garantindo que nunca
    se escreva um beatmap invalido em disco). Importa
    `BEATMAP_SCHEMA_VERSION`/`REQUIRED_*_FIELDS` exclusivamente de
    `ouroboros.rhythm.beatmap_format`.
    """

    def validate(self, beatmap_dict: Dict[str, Any]) -> None:
        """Verifica presenca/tipo de todos os campos de
        `REQUIRED_ROOT_FIELDS`/`REQUIRED_OSU_HIT_OBJECT_FIELDS`, a
        versao, a invariante de ordenacao estrita (nao-decrescente) de
        `threats[*].timestamp_seconds`, e que todo SLIDER tenha
        `end_x`/`end_y`/`duration_seconds` presentes e `duration_seconds > 0`.

        Levanta `OsuBeatmapValidationError` com mensagem descritiva no
        primeiro problema encontrado; nao retorna nada em caso de sucesso.
        """
        if not isinstance(beatmap_dict, dict):
            raise OsuBeatmapValidationError(f"beatmap document must be a dict, got {type(beatmap_dict).__name__}")

        for field in REQUIRED_ROOT_FIELDS:
            if field not in beatmap_dict:
                raise OsuBeatmapValidationError(f"beatmap document missing required field '{field}'")

        version = beatmap_dict["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version != BEATMAP_SCHEMA_VERSION:
            raise OsuBeatmapValidationError(
                f"beatmap schema version mismatch: expected {BEATMAP_SCHEMA_VERSION}, got {version!r}"
            )

        track_id = beatmap_dict["track_id"]
        if not isinstance(track_id, str) or not track_id:
            raise OsuBeatmapValidationError(f"beatmap 'track_id' must be a non-empty string, got {track_id!r}")

        bpm = beatmap_dict["bpm"]
        if not isinstance(bpm, (int, float)) or isinstance(bpm, bool) or bpm <= 0:
            raise OsuBeatmapValidationError(f"beatmap 'bpm' must be a positive number, got {bpm!r}")

        threats = beatmap_dict["threats"]
        if not isinstance(threats, (list, tuple)):
            raise OsuBeatmapValidationError(f"beatmap 'threats' must be a list, got {type(threats).__name__}")

        previous_timestamp = None
        for i, threat in enumerate(threats):
            if not isinstance(threat, dict):
                raise OsuBeatmapValidationError(f"threats[{i}] must be a dict, got {type(threat).__name__}")

            for field in REQUIRED_OSU_HIT_OBJECT_FIELDS:
                if field not in threat:
                    raise OsuBeatmapValidationError(f"threats[{i}] missing required field '{field}'")

            timestamp_seconds = threat["timestamp_seconds"]
            if (
                not isinstance(timestamp_seconds, (int, float))
                or isinstance(timestamp_seconds, bool)
                or timestamp_seconds < 0
            ):
                raise OsuBeatmapValidationError(
                    f"threats[{i}].timestamp_seconds must be a non-negative number, got {timestamp_seconds!r}"
                )

            threat_type = threat["threat_type"]
            if not isinstance(threat_type, str) or not threat_type:
                raise OsuBeatmapValidationError(f"threats[{i}].threat_type must be a non-empty string, got {threat_type!r}")

            for coord_field in ("x", "y"):
                coord = threat[coord_field]
                if not isinstance(coord, (int, float)) or isinstance(coord, bool):
                    raise OsuBeatmapValidationError(f"threats[{i}].{coord_field} must be a number, got {coord!r}")

            strength = threat["strength"]
            if not isinstance(strength, (int, float)) or isinstance(strength, bool) or not (0.0 <= float(strength) <= 1.0):
                raise OsuBeatmapValidationError(f"threats[{i}].strength must be within [0.0, 1.0], got {strength!r}")

            layer = threat.get("layer", "")
            if not isinstance(layer, str):
                raise OsuBeatmapValidationError(f"threats[{i}].layer must be a string when present, got {layer!r}")

            if threat_type == OSU_SLIDER_THREAT_TYPE_NAME:
                for slider_field in ("end_x", "end_y", "duration_seconds"):
                    if slider_field not in threat:
                        raise OsuBeatmapValidationError(
                            f"threats[{i}] e um slider (threat_type={threat_type!r}) sem campo obrigatorio '{slider_field}'"
                        )
                duration_seconds = threat["duration_seconds"]
                if not isinstance(duration_seconds, (int, float)) or isinstance(duration_seconds, bool) or duration_seconds <= 0:
                    raise OsuBeatmapValidationError(
                        f"threats[{i}].duration_seconds deve ser > 0, got {duration_seconds!r}"
                    )

            if previous_timestamp is not None and timestamp_seconds < previous_timestamp:
                raise OsuBeatmapValidationError(
                    f"threats[{i}].timestamp_seconds ({timestamp_seconds}) is out of order "
                    f"(previous timestamp was {previous_timestamp})"
                )
            previous_timestamp = timestamp_seconds

    def build_beatmap_dict(
        self,
        track_id: str,
        bpm: float,
        hit_objects: Tuple[OsuHitObjectDefinition, ...],
    ) -> Dict[str, Any]:
        """Monta o dict serializavel (com `version = BEATMAP_SCHEMA_VERSION`)
        a partir dos hit-objects ja calculados por `place_hit_objects`,
        ordenando `threats` por `timestamp_seconds` antes de retornar.

        Nao escreve em disco (ver `OsuBeatmapWriter`) nem valida (ver
        `validate`) -- o chamador deve validar o resultado antes de
        gravar.
        """
        sorted_hit_objects = sorted(hit_objects, key=lambda hit_object: hit_object.timestamp_seconds)
        threats = []
        for hit_object in sorted_hit_objects:
            threat = {
                "timestamp_seconds": float(hit_object.timestamp_seconds),
                "threat_type": hit_object.threat_type,
                "x": float(hit_object.x),
                "y": float(hit_object.y),
                "strength": float(hit_object.strength),
                "layer": str(hit_object.layer),
            }
            if hit_object.threat_type == OSU_SLIDER_THREAT_TYPE_NAME:
                threat["end_x"] = float(hit_object.end_x)
                threat["end_y"] = float(hit_object.end_y)
                threat["duration_seconds"] = float(hit_object.duration_seconds)
            threats.append(threat)

        return {
            "version": BEATMAP_SCHEMA_VERSION,
            "track_id": track_id,
            "bpm": float(bpm),
            "threats": threats,
        }
