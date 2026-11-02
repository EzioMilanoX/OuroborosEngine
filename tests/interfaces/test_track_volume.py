"""M17: volume da faixa musical (`IAudioEngine.set_track_volume`)."""

import os
import wave

import pytest

from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.null.null_audio_engine import NullAudioEngine


def test_default_e_no_op():
    """Backend que nao implementa continua valido: o metodo existe e nao faz nada."""

    class Minimo(NullAudioEngine):
        pass

    IAudioEngine.set_track_volume(Minimo(), 0.3)  # a implementacao da ABC nao quebra


def test_null_registra_e_limita():
    audio = NullAudioEngine()
    audio.set_track_volume(0.4)
    assert audio._track_volume == pytest.approx(0.4)
    audio.set_track_volume(3)
    assert audio._track_volume == 1.0
    audio.set_track_volume(-1)
    assert audio._track_volume == 0.0


@pytest.fixture
def faixa(tmp_path):
    caminho = tmp_path / "silencio.wav"
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 2205)
    return str(caminho)


def test_pygame_aplica_e_mantem_entre_faixas(faixa):
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    pygame = pytest.importorskip("pygame")
    from ouroboros.adapters.pygame_backend.pygame_audio_engine import PygameAudioEngine

    try:
        audio = PygameAudioEngine()
    except pygame.error:
        pytest.skip("sem mixer neste ambiente")
    audio.load_track("a", faixa)
    audio.set_track_volume(0.25)
    audio.play_track("a", loop=True)
    assert pygame.mixer.music.get_volume() == pytest.approx(0.25, abs=0.01)
    audio.play_track("a")  # uma faixa nova nao volta ao volume cheio
    assert pygame.mixer.music.get_volume() == pytest.approx(0.25, abs=0.01)
    audio.stop_track("a")
