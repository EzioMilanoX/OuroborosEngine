"""
Gera o conteudo de demonstracao do vertical slice: um WAV original
(sintetizado por numpy, sem risco de direito autoral) com um padrao de
kick a BPM fixo, e o beatmap real correspondente via pipeline offline
JA TESTADO (`ouroboros.rhythm.offline.cli`) -- nao um JSON escrito a
mao.

Roda uma vez (resultado vai commitado); nao faz parte do jogo em si.
Uso: `python games/rhythm_game/tools/generate_demo_track.py` (funciona
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
BPM = 120.0
BEAT_PERIOD_SECONDS = 60.0 / BPM
ACTIVE_BEATS = 40  # ~20s de padrao ritmico ativo (kick a cada beat)
TRAIL_SECONDS = 3.0
"""
Cauda silenciosa apos o ultimo beat: sem ela, a ultima nota poderia
nunca expirar normalmente (auto-erro) antes do fim real da faixa --
`pygame.mixer.music.get_pos()`/`get_busy()` tem comportamento
inconsistente entre plataformas/versoes quando uma faixa nao-repetida
termina, o que poderia fazer `PygameAudioClock.now_seconds()` voltar a
0 de forma imprevisivel logo apos o fim. Com folga suficiente de audio
real tocando depois do ultimo evento, a ultima nota sempre expira
normalmente enquanto o relogio ainda avanca de forma previsivel.
"""

KICK_DECAY_RATE = 30.0
KICK_FREQ_HZ = 100.0
KICK_DURATION_SECONDS = 0.15

_TOOLS_DIR = Path(__file__).resolve().parent
_GAME_DIR = _TOOLS_DIR.parent
_REPO_ROOT = _GAME_DIR.parent.parent
WAV_OUTPUT_PATH = _GAME_DIR / "assets" / "audio" / "demo_track.wav"
BEATMAP_OUTPUT_PATH = _REPO_ROOT / "data" / "beatmaps" / "demo_track.beatmap.json"
TRACK_ID = "demo_track"


def _synthesize_kick_track() -> np.ndarray:
    """Sintetiza um padrao de kick original (tom grave com decaimento
    exponencial) a BPM fixo, com a cauda silenciosa documentada acima."""
    active_duration = ACTIVE_BEATS * BEAT_PERIOD_SECONDS
    total_duration = active_duration + TRAIL_SECONDS
    n_samples = int(total_duration * SAMPLE_RATE)
    audio = np.zeros(n_samples, dtype=np.float64)

    kick_samples = int(KICK_DURATION_SECONDS * SAMPLE_RATE)
    t_kick = np.arange(kick_samples) / SAMPLE_RATE
    kick_waveform = np.exp(-t_kick * KICK_DECAY_RATE) * np.sin(2.0 * np.pi * KICK_FREQ_HZ * t_kick)

    for beat_index in range(ACTIVE_BEATS):
        start = int(beat_index * BEAT_PERIOD_SECONDS * SAMPLE_RATE)
        end = min(start + kick_samples, n_samples)
        audio[start:end] += kick_waveform[: end - start]

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
    audio = _synthesize_kick_track()
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
    ]
    result = subprocess.run(cli_args, cwd=str(_REPO_ROOT))
    if result.returncode != 0:
        return result.returncode

    print(f"Beatmap gerado via pipeline offline real: {BEATMAP_OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
