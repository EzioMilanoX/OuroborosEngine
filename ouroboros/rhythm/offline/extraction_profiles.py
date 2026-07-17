"""
Perfis de Extracao (Extraction Profiles) do pipeline offline de IA.

Motivacao: um unico filtro DSP nao serve a toda musica. O perfil
"groove" (HPSS percussivo + mel grave + PLP) e excelente para faixas
guiadas por bumbo/caixa, mas DESTROI faixas guiadas por voz/synth lead
rapido (estilo FNF), onde a melodia dita as notas. A solucao e a IA ser
adaptavel: o chamador escolhe o perfil (ou pede os dois em camadas).

Perfis:

    "groove" -- estabilidade ritmica:
        HPSS -> y_percussive; envelope de onset em mel GRAVE/medio
        (fmax ~250 Hz: bumbo + corpo de caixa); PLP (Predominant Local
        Pulse) para o pulso dominante; picos com threshold inteligente
        (intervalo minimo + altura relativa). Camada "kick".

    "vocal_shred" -- melodia sincopada:
        separacao SUAVE via HPSS (`y_harmonic + 0.5*y_percussive`):
        medido empiricamente, o harmonico PURO destroi o timing melodico
        (o ATAQUE de um synth/voz e um transiente vertical que o HPSS
        manda para o percussivo -- onsets sairiam ~150 ms fora; 0% dos
        onsets no lead vs 67% com a separacao suave). O filtro de banda
        (fmin 300 Hz, fmax 8000 Hz) e a atenuacao percussiva e que matam
        bumbo/bateria. `librosa.onset.onset_detect` agressivo (sem
        backtrack, delta baixo) com intervalo minimo curto -- SEM o
        rigor do PLP, para abracar metralhadoras de notas e sincopa.
        Camada "vocal".

    "hybrid" -- multi-camada:
        roda os dois processos e devolve as duas camadas taggeadas
        ("kick" e "vocal"). O beatmap resultante carrega a tag opcional
        `layer` por ameaca; o produto (jogo) roteia como quiser (ex.:
        kicks nas extremidades, vocais no centro).

Fronteira: a MATEMATICA do audio vive aqui (engine, offline); a
INTERPRETACAO (modos de jogo, UI, roteamento espacial) vive no produto.
librosa e importado lazy dentro das funcoes -- offline-only, nunca no
loop de gameplay.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
from scipy.signal import find_peaks

from ouroboros.rhythm.offline.audio_loader import LoadedAudio

LAYER_KICK = "kick"
LAYER_VOCAL = "vocal"

EXTRACTION_PROFILES = ("groove", "vocal_shred", "hybrid")
"""Nomes validos para o parametro `--profile` da CLI."""


@dataclass(frozen=True)
class ExtractionLayer:
    """Uma camada de eventos extraida do audio.

    Atributos:
        layer: tag da camada ("kick" | "vocal"), gravada por ameaca no
            beatmap (propriedade opcional `layer` do schema).
        pulse_timestamps_seconds / pulse_strengths: pulsos RITMICOS
            confiaveis (grade) -- vazios na camada vocal, que abraca o
            sincopado em vez de impor pulso.
        onset_timestamps_seconds / onset_strengths: eventos de energia
            da camada (votos/notas), forcas normalizadas 0..1.
        tempo_bpm_estimate: BPM estimado da camada (0.0 quando nao ha
            pulso confiavel).
    """

    layer: str
    pulse_timestamps_seconds: np.ndarray
    pulse_strengths: np.ndarray
    onset_timestamps_seconds: np.ndarray
    onset_strengths: np.ndarray
    tempo_bpm_estimate: float


@dataclass(frozen=True)
class ProfileExtractionResult:
    """Saida de `extract_with_profile`: uma camada (groove/vocal_shred)
    ou duas (hybrid), na ordem (kick, vocal)."""

    profile: str
    layers: Tuple[ExtractionLayer, ...]


# ------------------------------------------------------------------ puras

def select_curve_peaks(
    curve: np.ndarray,
    frame_times: np.ndarray,
    minimum_interval_sec: float,
    min_height_ratio: float,
) -> Tuple[np.ndarray, np.ndarray]:
    """Threshold inteligente, puro: picos de `curve` com espacamento
    minimo em SEGUNDOS (convertido pela taxa real da curva) e altura
    minima `min_height_ratio * max(curve)`. Retorna
    `(tempos, alturas_normalizadas)`."""
    curve = np.asarray(curve, dtype=np.float64)
    frame_times = np.asarray(frame_times, dtype=np.float64)
    if curve.shape[0] < 3:
        return np.zeros(0), np.zeros(0)
    peak_value = float(curve.max())
    if peak_value <= 0.0:
        return np.zeros(0), np.zeros(0)

    frame_period = float(np.median(np.diff(frame_times))) if frame_times.shape[0] > 1 else 1.0
    distance_frames = max(1, int(round(minimum_interval_sec / max(frame_period, 1e-9))))
    peak_indices, _ = find_peaks(
        curve, distance=distance_frames, height=min_height_ratio * peak_value
    )
    return frame_times[peak_indices], curve[peak_indices] / peak_value


def estimate_bpm_from_pulses(pulse_times: np.ndarray, fallback_bpm: float = 120.0) -> float:
    """BPM pela MEDIANA dos intervalos entre pulsos (robusta a pulso
    perdido), com dobra de oitava para a faixa musical usual [70, 180):
    o PLP pode travar no dobro/metade do tempo percebido -- isso nao
    afeta a grade (mesmos pulsos), so o metadado."""
    pulse_times = np.asarray(pulse_times, dtype=np.float64)
    if pulse_times.shape[0] < 2:
        return fallback_bpm
    median_gap = float(np.median(np.diff(pulse_times)))
    if median_gap <= 0.0:
        return fallback_bpm
    bpm = 60.0 / median_gap
    while bpm >= 180.0:
        bpm /= 2.0
    while bpm < 70.0:
        bpm *= 2.0
    return bpm


# ------------------------------------------------------------ com librosa

def _mel_onset_envelope(
    samples: np.ndarray,
    sample_rate: int,
    hop_length: int,
    n_mels: int,
    fmin: float,
    fmax: float,
):
    """Envelope de onset sobre um mel-espectrograma limitado a
    [fmin, fmax] -- o filtro de banda que decide O QUE cada perfil ouve."""
    import librosa

    mel_spectrogram = librosa.feature.melspectrogram(
        y=samples, sr=sample_rate, hop_length=hop_length,
        n_mels=n_mels, fmin=fmin, fmax=fmax,
    )
    envelope = librosa.onset.onset_strength(
        S=librosa.power_to_db(mel_spectrogram, ref=np.max),
        sr=sample_rate, hop_length=hop_length,
    )
    frame_times = librosa.times_like(envelope, sr=sample_rate, hop_length=hop_length)
    return envelope, frame_times


def extract_groove_layer(
    audio: LoadedAudio,
    fmax_hz: float = 250.0,
    n_mels: int = 40,
    hop_length: int = 512,
    plp_tempo_min: float = 40.0,
    plp_tempo_max: float = 220.0,
    minimum_interval_sec: float = 0.10,
    pulse_min_height_ratio: float = 0.30,
    onset_min_height_ratio: float = 0.12,
) -> ExtractionLayer:
    """PERFIL "groove": HPSS percussivo + mel grave + PLP + threshold.
    Foco em estabilidade de tempo (bumbo/caixa)."""
    import librosa

    samples = np.asarray(audio.samples, dtype=np.float32)
    _, y_percussive = librosa.effects.hpss(samples)

    envelope, frame_times = _mel_onset_envelope(
        y_percussive, audio.sample_rate, hop_length, n_mels, fmin=0.0, fmax=fmax_hz
    )
    plp_curve = librosa.beat.plp(
        onset_envelope=envelope, sr=audio.sample_rate, hop_length=hop_length,
        tempo_min=plp_tempo_min, tempo_max=plp_tempo_max,
    )
    pulse_times, pulse_strengths = select_curve_peaks(
        plp_curve, frame_times, minimum_interval_sec, pulse_min_height_ratio
    )
    onset_times, onset_strengths = select_curve_peaks(
        envelope, frame_times, minimum_interval_sec, onset_min_height_ratio
    )
    return ExtractionLayer(
        layer=LAYER_KICK,
        pulse_timestamps_seconds=pulse_times,
        pulse_strengths=pulse_strengths,
        onset_timestamps_seconds=onset_times,
        onset_strengths=onset_strengths,
        tempo_bpm_estimate=estimate_bpm_from_pulses(pulse_times),
    )


def extract_vocal_shred_layer(
    audio: LoadedAudio,
    fmin_hz: float = 300.0,
    fmax_hz: float = 8000.0,
    n_mels: int = 64,
    hop_length: int = 512,
    minimum_interval_sec: float = 0.10,
    onset_delta: float = 0.05,
    onset_min_height_ratio: float = 0.25,
    percussive_bleed: float = 0.5,
) -> ExtractionLayer:
    """PERFIL "vocal_shred": separacao suave (harmonico + percussivo
    atenuado por `percussive_bleed` -- preserva os ATAQUES da melodia,
    ver docstring do modulo) + mel medio/agudo + `onset_detect`
    agressivo (sem backtrack, delta baixo, intervalo minimo curto).
    SEM PLP: a melodia sincopada dita as notas -- pulsos vazios
    sinalizam ao mapeador para NAO quantizar esta camada."""
    import librosa

    samples = np.asarray(audio.samples, dtype=np.float32)
    y_harmonic, y_percussive = librosa.effects.hpss(samples)
    melody_signal = y_harmonic + np.float32(percussive_bleed) * y_percussive

    envelope, frame_times = _mel_onset_envelope(
        melody_signal, audio.sample_rate, hop_length, n_mels, fmin=fmin_hz, fmax=fmax_hz
    )
    wait_frames = max(1, int(round(
        minimum_interval_sec / max(float(np.median(np.diff(frame_times))), 1e-9)
    )))
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=envelope, sr=audio.sample_rate, hop_length=hop_length,
        backtrack=False,  # backtracking adianta as notas; aqui nao
        delta=onset_delta, wait=wait_frames,
    )
    onset_times = frame_times[onset_frames]
    peak_value = float(envelope.max()) if envelope.shape[0] else 0.0
    onset_strengths = (
        envelope[onset_frames] / peak_value if peak_value > 0.0 else np.zeros(onset_times.shape[0])
    )
    # threshold inteligente tambem aqui: a agressividade do detector
    # captura a metralhadora REAL, mas ondulacoes fracas do envelope e
    # vazamento residual do HPSS ficam abaixo do piso relativo
    strong_enough = onset_strengths >= onset_min_height_ratio
    onset_times = onset_times[strong_enough]
    onset_strengths = onset_strengths[strong_enough]
    return ExtractionLayer(
        layer=LAYER_VOCAL,
        pulse_timestamps_seconds=np.zeros(0),
        pulse_strengths=np.zeros(0),
        onset_timestamps_seconds=onset_times,
        onset_strengths=np.clip(onset_strengths, 0.0, 1.0),
        tempo_bpm_estimate=0.0,
    )


def extract_with_profile(audio: LoadedAudio, profile: str = "groove") -> ProfileExtractionResult:
    """Executa o(s) processo(s) DSP do perfil pedido. "hybrid" roda os
    dois e devolve as camadas na ordem (kick, vocal)."""
    if profile not in EXTRACTION_PROFILES:
        raise ValueError(f"perfil de extracao desconhecido: {profile!r} (validos: {EXTRACTION_PROFILES})")
    if profile == "groove":
        layers = (extract_groove_layer(audio),)
    elif profile == "vocal_shred":
        layers = (extract_vocal_shred_layer(audio),)
    else:
        layers = (extract_groove_layer(audio), extract_vocal_shred_layer(audio))
    return ProfileExtractionResult(profile=profile, layers=layers)
