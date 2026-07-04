"""Valida e monta o dict serializavel de beatmap, antes da escrita atomica. So importa beatmap_format."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from ouroboros.rhythm.beatmap_format import (
    BEATMAP_SCHEMA_VERSION,
    REQUIRED_ROOT_FIELDS,
    REQUIRED_THREAT_FIELDS,
)


class BeatmapValidationError(Exception):
    """Levantado quando um dict de beatmap nao satisfaz o schema esperado:
    campo obrigatorio ausente, tipo incorreto, timestamps nao-ordenados,
    lane fora do intervalo valido, `strength` fora de `[0.0, 1.0]`,
    versao desconhecida, etc. A mensagem deve identificar o PRIMEIRO
    problema encontrado.
    """


@dataclass(frozen=True)
class ScheduledThreatDefinition:
    """Representacao intermediaria (em memoria, offline) de UMA ameaca
    agendada, antes de ser serializada para JSON ou materializada em
    NumPy pelo `BeatmapLoader` do runtime.

    Atributos:
        timestamp_seconds: instante de disparo, relativo ao inicio da
            faixa (mesma base de tempo de `IAudioClock.now_seconds`).
        threat_type: string identificando o tipo de ameaca (data-driven;
            mapeada para um inteiro pelo `BeatmapLoader` no momento do
            carregamento em runtime).
        lane: indice de lane/pista onde a ameaca deve aparecer.
        strength: intensidade normalizada (`0.0`-`1.0`), derivada de
            `OnsetExtractionResult.onset_strengths`.
    """

    timestamp_seconds: float
    threat_type: str
    lane: int
    strength: float


class BeatmapValidator:
    """Valida a estrutura de um dict de beatmap antes da escrita/leitura.

    Usado pelo escritor offline (`BeatmapWriter`, garantindo que nunca
    se escreva um beatmap invalido em disco) e, opcionalmente, por
    ferramentas de QA/CI que auditam beatmaps ja existentes em `data/`.
    Importa `BEATMAP_SCHEMA_VERSION`/`REQUIRED_*_FIELDS` exclusivamente
    de `ouroboros.rhythm.beatmap_format`.
    """

    def validate(self, beatmap_dict: Dict[str, Any]) -> None:
        """Verifica presenca/tipo de todos os campos de
        `REQUIRED_ROOT_FIELDS`/`REQUIRED_THREAT_FIELDS`, a versao
        (`beatmap_dict['version'] == BEATMAP_SCHEMA_VERSION`) e a
        invariante de ordenacao estrita (nao-decrescente) de
        `threats[*].timestamp_seconds`.

        Levanta `BeatmapValidationError` com mensagem descritiva no
        primeiro problema encontrado; nao retorna nada em caso de sucesso.
        """
        if not isinstance(beatmap_dict, dict):
            raise BeatmapValidationError(f"beatmap document must be a dict, got {type(beatmap_dict).__name__}")

        for field in REQUIRED_ROOT_FIELDS:
            if field not in beatmap_dict:
                raise BeatmapValidationError(f"beatmap document missing required field '{field}'")

        version = beatmap_dict["version"]
        if not isinstance(version, int) or isinstance(version, bool) or version != BEATMAP_SCHEMA_VERSION:
            raise BeatmapValidationError(
                f"beatmap schema version mismatch: expected {BEATMAP_SCHEMA_VERSION}, got {version!r}"
            )

        track_id = beatmap_dict["track_id"]
        if not isinstance(track_id, str) or not track_id:
            raise BeatmapValidationError(f"beatmap 'track_id' must be a non-empty string, got {track_id!r}")

        bpm = beatmap_dict["bpm"]
        if not isinstance(bpm, (int, float)) or isinstance(bpm, bool) or bpm <= 0:
            raise BeatmapValidationError(f"beatmap 'bpm' must be a positive number, got {bpm!r}")

        threats = beatmap_dict["threats"]
        if not isinstance(threats, (list, tuple)):
            raise BeatmapValidationError(f"beatmap 'threats' must be a list, got {type(threats).__name__}")

        previous_timestamp = None
        for i, threat in enumerate(threats):
            if not isinstance(threat, dict):
                raise BeatmapValidationError(f"threats[{i}] must be a dict, got {type(threat).__name__}")

            for field in REQUIRED_THREAT_FIELDS:
                if field not in threat:
                    raise BeatmapValidationError(f"threats[{i}] missing required field '{field}'")

            timestamp_seconds = threat["timestamp_seconds"]
            if (
                not isinstance(timestamp_seconds, (int, float))
                or isinstance(timestamp_seconds, bool)
                or timestamp_seconds < 0
            ):
                raise BeatmapValidationError(
                    f"threats[{i}].timestamp_seconds must be a non-negative number, got {timestamp_seconds!r}"
                )

            threat_type = threat["threat_type"]
            if not isinstance(threat_type, str) or not threat_type:
                raise BeatmapValidationError(f"threats[{i}].threat_type must be a non-empty string, got {threat_type!r}")

            lane = threat["lane"]
            if not isinstance(lane, int) or isinstance(lane, bool) or lane < 0:
                raise BeatmapValidationError(f"threats[{i}].lane must be a non-negative integer, got {lane!r}")

            strength = threat["strength"]
            if not isinstance(strength, (int, float)) or isinstance(strength, bool) or not (0.0 <= float(strength) <= 1.0):
                raise BeatmapValidationError(f"threats[{i}].strength must be within [0.0, 1.0], got {strength!r}")

            if previous_timestamp is not None and timestamp_seconds < previous_timestamp:
                raise BeatmapValidationError(
                    f"threats[{i}].timestamp_seconds ({timestamp_seconds}) is out of order "
                    f"(previous timestamp was {previous_timestamp})"
                )
            previous_timestamp = timestamp_seconds

    def build_beatmap_dict(
        self,
        track_id: str,
        bpm: float,
        threats: Tuple[ScheduledThreatDefinition, ...],
    ) -> Dict[str, Any]:
        """Monta o dict serializavel (com `version = BEATMAP_SCHEMA_VERSION`)
        a partir dos resultados intermediarios do pipeline, ordenando
        `threats` por `timestamp_seconds` antes de retornar.

        Nao escreve em disco (ver `BeatmapWriter`) nem valida (ver
        `validate`) -- o chamador deve validar o resultado antes de
        gravar.
        """
        sorted_threats = sorted(threats, key=lambda threat: threat.timestamp_seconds)
        return {
            "version": BEATMAP_SCHEMA_VERSION,
            "track_id": track_id,
            "bpm": float(bpm),
            "threats": [
                {
                    "timestamp_seconds": float(threat.timestamp_seconds),
                    "threat_type": threat.threat_type,
                    "lane": int(threat.lane),
                    "strength": float(threat.strength),
                }
                for threat in sorted_threats
            ],
        }
