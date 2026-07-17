"""Entrypoint de CLI do pipeline offline de IA (python -m ouroboros.rhythm.offline.cli)."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import List, Optional

from ouroboros.rhythm.offline.audio_ai_processor import AudioAIProcessor
from ouroboros.rhythm.offline.audio_loader import AudioLoader, AudioLoadError
from ouroboros.rhythm.offline.beatmap_schema import BeatmapValidationError, BeatmapValidator
from ouroboros.rhythm.offline.beatmap_writer import BeatmapWriteError, BeatmapWriter
from ouroboros.rhythm.offline.bpm_extractor import BpmExtractionError, BpmExtractor
from ouroboros.rhythm.offline.onset_extractor import OnsetExtractionError, OnsetExtractor


def build_arg_parser() -> argparse.ArgumentParser:
    """Constroi o parser de argumentos da CLI (`--audio`, `--output`,
    `--track-id`, `--lanes`, flags de configuracao de BPM/onset).
    """
    parser = argparse.ArgumentParser(
        prog="python -m ouroboros.rhythm.offline.cli",
        description=(
            "Pipeline offline de IA do Ouroboros Engine: analisa um arquivo de "
            "audio e gera um beatmap.json (data-driven) para o RhythmSpawnerSystem."
        ),
    )
    parser.add_argument(
        "--audio",
        required=True,
        type=Path,
        help="Caminho do arquivo de audio de entrada (wav/ogg/mp3, o que o librosa suportar).",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Caminho de destino do beatmap.json a ser gravado atomicamente.",
    )
    parser.add_argument(
        "--track-id",
        required=True,
        dest="track_id",
        type=str,
        help="Identificador logico da faixa, gravado no campo 'track_id' do beatmap.",
    )
    parser.add_argument(
        "--lanes",
        type=int,
        default=4,
        help="Numero de lanes disponiveis para distribuir as ameacas geradas (default: 4).",
    )
    parser.add_argument(
        "--tightness",
        type=float,
        default=100.0,
        help="Rigidez do rastreamento de batida repassada a librosa.beat.beat_track (default: 100.0).",
    )
    parser.add_argument(
        "--backtrack",
        dest="backtrack",
        action="store_true",
        default=True,
        help="Habilita backtracking de onset (padrao: habilitado).",
    )
    parser.add_argument(
        "--no-backtrack",
        dest="backtrack",
        action="store_false",
        help="Desabilita backtracking de onset.",
    )
    parser.add_argument(
        "--profile",
        choices=["groove", "vocal_shred", "hybrid"],
        default=None,
        help=(
            "Perfil de Extracao DSP: 'groove' (HPSS percussivo + mel grave + PLP; "
            "faixas guiadas por bumbo), 'vocal_shred' (HPSS harmonico + mel medio/agudo + "
            "onset_detect agressivo; melodias/sincopa estilo FNF) ou 'hybrid' "
            "(ambas as camadas, taggeadas com 'layer' kick/vocal no beatmap). "
            "Omitido: extracao legada."
        ),
    )
    return parser


def build_processor(args: argparse.Namespace) -> AudioAIProcessor:
    """Constroi um `AudioAIProcessor` totalmente configurado (com todos
    os colaboradores reais) a partir dos argumentos da CLI ja parseados.
    """
    return AudioAIProcessor(
        audio_loader=AudioLoader(),
        bpm_extractor=BpmExtractor(tightness=args.tightness),
        onset_extractor=OnsetExtractor(backtrack=args.backtrack),
        beatmap_validator=BeatmapValidator(),
        beatmap_writer=BeatmapWriter(BeatmapValidator()),
        lane_count=args.lanes,
        extraction_profile=args.profile,
    )


def main(argv: Optional[List[str]] = None) -> int:
    """Ponto de entrada da CLI: parseia argumentos, roda o pipeline, e
    imprime um resumo (`AudioAIProcessorResult`) ou uma mensagem de erro
    descritiva.

    Retorna o codigo de saida do processo (`0` em sucesso, diferente de
    `0` se qualquer etapa do pipeline levantar uma excecao).
    """
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    processor = build_processor(args)

    try:
        result = processor.process(
            audio_path=args.audio,
            beatmap_output_path=args.output,
            track_id=args.track_id,
        )
    except (
        AudioLoadError,
        BpmExtractionError,
        OnsetExtractionError,
        BeatmapValidationError,
        BeatmapWriteError,
    ) as exc:
        print(f"erro no pipeline offline de IA: {exc}")
        return 1

    print(
        "beatmap gerado com sucesso: "
        f"track_id={args.track_id!r} bpm={result.bpm_result.bpm:.2f} "
        f"threats={result.threat_count} -> {result.beatmap_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
