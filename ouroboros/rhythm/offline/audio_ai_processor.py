"""Orquestra o pipeline offline completo: audio -> BPM -> onsets -> beatmap.json."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Tuple

from ouroboros.rhythm.offline.audio_loader import AudioLoader, LoadedAudio
from ouroboros.rhythm.offline.beatmap_schema import BeatmapValidator, ScheduledThreatDefinition
from ouroboros.rhythm.offline.beatmap_writer import BeatmapWriter
from ouroboros.rhythm.offline.bpm_extractor import BpmExtractionResult, BpmExtractor
from ouroboros.rhythm.offline.onset_extractor import OnsetExtractionResult, OnsetExtractor


@dataclass(frozen=True)
class AudioAIProcessorResult:
    """Resumo do processamento de uma faixa, para logging/relatorio de CLI.

    Atributos:
        audio: resultado da etapa de carregamento.
        bpm_result: resultado da etapa de extracao de BPM.
        onset_result: resultado da etapa de extracao de onsets.
        beatmap_path: caminho final onde `beatmap.json` foi gravado.
        threat_count: quantidade de ameacas agendadas geradas.
    """

    audio: LoadedAudio
    bpm_result: BpmExtractionResult
    onset_result: OnsetExtractionResult
    beatmap_path: Path
    threat_count: int


class AudioAIProcessor:
    """Orquestra o pipeline offline completo: carregar audio -> extrair
    BPM -> extrair onsets -> mapear onsets em ameacas agendadas -> escrever
    `beatmap.json` atomicamente.

    ROBUSTEZ COMO PRIORIDADE ARQUITETURAL: cada etapa e delegada a um
    colaborador dedicado e testavel ISOLADAMENTE (`AudioLoader`,
    `BpmExtractor`, `OnsetExtractor`, `BeatmapValidator`,
    `BeatmapWriter`); este orquestrador nao contem logica propria de
    extracao/serializacao, apenas a SEQUENCIA das etapas e a propagacao
    de falhas. Uma falha em QUALQUER etapa (`AudioLoadError`,
    `BpmExtractionError`, `OnsetExtractionError`,
    `BeatmapValidationError`, `BeatmapWriteError`) interrompe o
    pipeline ANTES da escrita em disco -- um `beatmap.json` de destino
    pre-existente permanece intocado ate que TODAS as etapas tenham
    sucesso nesta nova execucao.

    Roda 100% fora do loop de gameplay (script/CLI batch); pode alocar
    objetos Python livremente.
    """

    def __init__(
        self,
        audio_loader: AudioLoader,
        bpm_extractor: BpmExtractor,
        onset_extractor: OnsetExtractor,
        beatmap_validator: BeatmapValidator,
        beatmap_writer: BeatmapWriter,
        lane_count: int,
        extraction_profile: str = None,
    ) -> None:
        """Injeta cada colaborador de etapa (permite substituir por
        dubles de teste sem tocar audio real nem disco) e `lane_count`
        usado para distribuir ameacas entre lanes.

        `extraction_profile` (opcional): nome de um Perfil de Extracao
        ("groove" | "vocal_shred" | "hybrid", ver
        `extraction_profiles.py`). Quando definido, a etapa de extracao
        usa o pipeline DSP do perfil (HPSS/mel filtrado/PLP ou
        onset_detect agressivo) e cada ameaca gerada carrega a tag
        `layer` da camada de origem; `None` mantem o caminho legado
        (BpmExtractor + OnsetExtractor genericos), preservando o
        comportamento historico e os testes existentes.
        """
        self._audio_loader = audio_loader
        self._bpm_extractor = bpm_extractor
        self._onset_extractor = onset_extractor
        self._beatmap_validator = beatmap_validator
        self._beatmap_writer = beatmap_writer
        self._lane_count = lane_count
        self._extraction_profile = extraction_profile

    def process(self, audio_path: Path, beatmap_output_path: Path, track_id: str) -> AudioAIProcessorResult:
        """Executa o pipeline completo para `audio_path` e grava o
        resultado em `beatmap_output_path`.

        Ordem estrita: `audio_loader.load` -> `bpm_extractor.extract`
        -> `onset_extractor.extract` -> `_map_onsets_to_threats` ->
        `beatmap_validator.build_beatmap_dict` -> `beatmap_writer.write`.
        Propaga (nao engole) qualquer excecao de etapa para o chamador.
        """
        audio = self._audio_loader.load(audio_path)
        bpm_result = self._bpm_extractor.extract(audio)
        onset_result = self._onset_extractor.extract(audio)
        if self._extraction_profile is not None:
            threats = self._map_profile_layers_to_threats(audio)
        else:
            threats = self._map_onsets_to_threats(onset_result, bpm_result)
        beatmap_dict = self._beatmap_validator.build_beatmap_dict(
            track_id=track_id,
            bpm=bpm_result.bpm,
            threats=threats,
        )
        self._beatmap_writer.write(beatmap_dict, beatmap_output_path)

        return AudioAIProcessorResult(
            audio=audio,
            bpm_result=bpm_result,
            onset_result=onset_result,
            beatmap_path=beatmap_output_path,
            threat_count=len(threats),
        )

    def _map_profile_layers_to_threats(self, audio) -> Tuple[ScheduledThreatDefinition, ...]:
        """Mapeia as camadas do Perfil de Extracao ativo em ameacas
        agendadas, cada uma com a tag `layer` da camada de origem
        ("kick"/"vocal"). Mantem a heuristica deliberadamente simples da
        engine (lane ciclica por camada); curadoria fina e interpretacao
        espacial pertencem ao produto."""
        from ouroboros.rhythm.offline.extraction_profiles import extract_with_profile

        result = extract_with_profile(audio, self._extraction_profile)
        threats = []
        for extraction_layer in result.layers:
            times = extraction_layer.onset_timestamps_seconds
            strengths = extraction_layer.onset_strengths
            for i in range(times.shape[0]):
                threats.append(
                    ScheduledThreatDefinition(
                        timestamp_seconds=float(times[i]),
                        threat_type="rhythm_threat_basic",
                        lane=i % self._lane_count,
                        strength=float(min(max(strengths[i], 0.0), 1.0)),
                        layer=extraction_layer.layer,
                    )
                )
        return tuple(sorted(threats, key=lambda threat: threat.timestamp_seconds))

    def _map_onsets_to_threats(
        self,
        onset_result: OnsetExtractionResult,
        bpm_result: BpmExtractionResult,
    ) -> Tuple[ScheduledThreatDefinition, ...]:
        """Converte onsets detectados em definicoes de ameaca agendada,
        atribuindo `lane` e `threat_type` de forma deterministica a
        partir de `onset_strengths` e da posicao relativa as batidas de
        `bpm_result`. Isolada para poder ser testada com resultados
        sinteticos, sem rodar librosa de verdade.
        """
        # `bpm_result` nao influencia hoje a escolha de lane/threat_type
        # (heuristica deliberadamente simples e deterministica, ver
        # docstring de classe), mas e recebido para permitir evoluir a
        # heuristica (ex.: alinhar ameacas a batidas) sem mudar a
        # assinatura publica.
        del bpm_result

        threat_type = "rhythm_threat_basic"
        threats = []
        timestamps = onset_result.onset_timestamps_seconds
        strengths = onset_result.onset_strengths
        for onset_index in range(timestamps.shape[0]):
            lane = onset_index % self._lane_count
            threats.append(
                ScheduledThreatDefinition(
                    timestamp_seconds=float(timestamps[onset_index]),
                    threat_type=threat_type,
                    lane=int(lane),
                    strength=float(strengths[onset_index]),
                )
            )
        return tuple(threats)
