"""
Gera a segunda musica jogavel (ROADMAP M11.2): um WAV original
(sintetizado por numpy, sem risco de direito autoral) com DUAS camadas
distintas -- um padrao de kick grave a cada batida (mesma familia de
`generate_demo_track.py`) e um "blip" tonal agudo no contratempo de cada
batida (frequencia bem acima da banda que o perfil "groove" escuta,
timbre sustentado que o HPSS tende a classificar como harmonico, no
lugar/tempo certo pro perfil "vocal_shred" achar sincopa de verdade) --
e o beatmap real correspondente via pipeline offline JA TESTADO
(`ouroboros.rhythm.offline.cli --profile hybrid`), que tageia cada
camada com "kick"/"vocal" (ROADMAP M11.4 -- primeiro beatmap real com
diversidade de `layer`, ao contrario de `demo_track` que usa extracao
legada e tem `layer=""` em toda nota).

Roda uma vez (resultado vai commitado); nao faz parte do jogo em si.
Uso: `python games/rhythm_game/tools/generate_second_track.py` (funciona
como script solto, ao contrario de `main.py`, pois nao importa nada de
`games.rhythm_game.*`).
"""
from __future__ import annotations

import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 22050
BPM = 100.0
BEAT_PERIOD_SECONDS = 60.0 / BPM
ACTIVE_BEATS = 32  # ~19.2s de padrao ritmico ativo (kick a cada beat + blip no contratempo)
TRAIL_SECONDS = 3.0
"""Cauda silenciosa apos o ultimo evento -- mesmo motivo documentado em
generate_demo_track.py (comportamento inconsistente de
pygame.mixer.music.get_pos()/get_busy() ao fim de uma faixa nao-repetida)."""

KICK_DECAY_RATE = 30.0
KICK_FREQ_HZ = 100.0
KICK_DURATION_SECONDS = 0.15

# "Vocal": bem acima da banda grave que o perfil "groove" escuta (fmax=250Hz,
# ver extraction_profiles.py) e dentro da banda media/aguda que "vocal_shred"
# filtra (300-8000Hz); um tom com 2 parciais e ataque suave (nao um clique
# instantaneo/largo-espectro como o kick) tende a HPSS classificar como
# harmonico, nao percussivo.
VOCAL_FREQ_HZ = 900.0
VOCAL_PARTIAL_FREQ_HZ = 1800.0
VOCAL_PARTIAL_GAIN = 0.4
VOCAL_ATTACK_SECONDS = 0.015
VOCAL_DECAY_RATE = 12.0
VOCAL_DURATION_SECONDS = 0.22

_TOOLS_DIR = Path(__file__).resolve().parent
_GAME_DIR = _TOOLS_DIR.parent
_REPO_ROOT = _GAME_DIR.parent.parent
WAV_OUTPUT_PATH = _GAME_DIR / "assets" / "audio" / "second_track.wav"
BEATMAP_OUTPUT_PATH = _REPO_ROOT / "data" / "beatmaps" / "second_track.beatmap.json"
TRACK_ID = "second_track"


def _kick_waveform() -> np.ndarray:
    kick_samples = int(KICK_DURATION_SECONDS * SAMPLE_RATE)
    t_kick = np.arange(kick_samples) / SAMPLE_RATE
    return np.exp(-t_kick * KICK_DECAY_RATE) * np.sin(2.0 * np.pi * KICK_FREQ_HZ * t_kick)


def _vocal_waveform() -> np.ndarray:
    n_samples = int(VOCAL_DURATION_SECONDS * SAMPLE_RATE)
    t = np.arange(n_samples) / SAMPLE_RATE
    tone = np.sin(2.0 * np.pi * VOCAL_FREQ_HZ * t) + VOCAL_PARTIAL_GAIN * np.sin(
        2.0 * np.pi * VOCAL_PARTIAL_FREQ_HZ * t
    )
    attack_samples = max(1, int(VOCAL_ATTACK_SECONDS * SAMPLE_RATE))
    envelope = np.exp(-t * VOCAL_DECAY_RATE)
    envelope[:attack_samples] *= np.linspace(0.0, 1.0, attack_samples)
    return tone * envelope


def _synthesize_kick_and_vocal_track() -> np.ndarray:
    """Kick em cada batida cheia (0, 1, 2, ...) + blip vocal no
    contratempo (0.5, 1.5, 2.5, ...) -- as duas camadas nunca coincidem
    no tempo, entao cada uma produz sua propria grade de onsets."""
    active_duration = ACTIVE_BEATS * BEAT_PERIOD_SECONDS
    total_duration = active_duration + TRAIL_SECONDS
    n_samples = int(total_duration * SAMPLE_RATE)
    audio = np.zeros(n_samples, dtype=np.float64)

    kick_waveform = _kick_waveform()
    vocal_waveform = _vocal_waveform()

    for beat_index in range(ACTIVE_BEATS):
        kick_start = int(beat_index * BEAT_PERIOD_SECONDS * SAMPLE_RATE)
        kick_end = min(kick_start + kick_waveform.shape[0], n_samples)
        audio[kick_start:kick_end] += kick_waveform[: kick_end - kick_start]

        vocal_start = int((beat_index + 0.5) * BEAT_PERIOD_SECONDS * SAMPLE_RATE)
        vocal_end = min(vocal_start + vocal_waveform.shape[0], n_samples)
        if vocal_start < n_samples:
            audio[vocal_start:vocal_end] += vocal_waveform[: vocal_end - vocal_start]

    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.85
    return audio


def _write_wav(samples: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples_int16 = (samples * np.iinfo(np.int16).max).astype(np.int16)
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)
        wav_file.writeframes(samples_int16.tobytes())


def main() -> int:
    audio = _synthesize_kick_and_vocal_track()
    _write_wav(audio, WAV_OUTPUT_PATH)
    print(f"WAV original sintetizado: {WAV_OUTPUT_PATH}")

    cli_args = [
        sys.executable,
        "-m",
        "ouroboros.rhythm.offline.cli",
        "--audio",
        str(WAV_OUTPUT_PATH),
        "--output",
        str(BEATMAP_OUTPUT_PATH),
        "--track-id",
        TRACK_ID,
        "--lanes",
        "4",
        "--profile",
        "hybrid",
    ]
    result = subprocess.run(cli_args, cwd=str(_REPO_ROOT))
    if result.returncode != 0:
        return result.returncode

    print(f"Beatmap gerado via pipeline offline real (perfil hybrid): {BEATMAP_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
