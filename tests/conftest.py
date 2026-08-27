# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# ============================================================================
# PILAR 5 -- tests/conftest.py
#
# Fixtures pytest compartilhadas por toda a suite headless.
#
# Nota sobre "esqueleto": a diretriz de "nenhum corpo de metodo
# implementado" aplica-se aos CORPOS das fixtures (usam "..." como
# corpo). A UNICA excecao e a linha de configuracao de ambiente no topo
# do modulo (ver comentario "(a)" abaixo): precisa ser codigo real
# executado na COLETA do pytest -- antes de qualquer import capaz de
# tocar pygame -- porque nao ha como expressar "force uma variavel de
# ambiente antes de outros imports" como o corpo de uma fixture (uma
# fixture so executaria DEPOIS que os modulos de teste do diretorio ja
# tivessem sido importados, tarde demais para o SDL). Isso nao e logica
# de gameplay nem parte da API dos Pilares 1-4; e fiacao de
# infraestrutura de teste.
# ============================================================================

import os

# (a) Forca drivers de video E audio "dummy" (headless) ANTES de qualquer
# import que possa, direta ou transitivamente, inicializar pygame (ex.: um
# IRenderer/IAudioEngine real usado em algum teste de integracao). Fica no
# topo do modulo, antes inclusive de `import pytest`, para nao correr o
# risco de algum import abaixo ja ter tocado pygame antes destas linhas.
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import numpy as np
import pytest

from ouroboros.core.components.schemas import COMPONENT_SCHEMAS
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.world import World
from ouroboros.interfaces.audio_clock import IAudioClock
from ouroboros.interfaces.audio_engine import IAudioEngine
from ouroboros.interfaces.input_provider import IInputProvider
from ouroboros.interfaces.null.null_audio_engine import NullAudioEngine
from ouroboros.interfaces.null.null_input_provider import NullInputProvider
from ouroboros.interfaces.null.null_renderer import NullRenderer
from ouroboros.interfaces.renderer import IRenderer


DEFAULT_TEST_ENTITY_CAPACITY: int = 1024
"""Capacidade de entidades usada pela fixture `memory_manager`: pequena o
bastante para os testes rodarem rapido, grande o bastante para exercitar
indices/geracoes nao triviais (varios ciclos de acquire/release) sem
esgotar a capacidade em um teste que crie/destrua entidades em lote.
"""


@pytest.fixture
def memory_manager() -> MemoryManager:
    """Fornece um `MemoryManager` minimo (`entity_capacity =
    DEFAULT_TEST_ENTITY_CAPACITY`), SEM nenhuma pool de componente
    pre-criada.

    Cada modulo de teste e responsavel por criar (via `create_pool`) as
    pools especificas do que esta exercitando. Escopo `function`
    (padrao): cada teste recebe uma instancia nova e isolada, evitando
    vazamento de estado (entidades vivas, contadores de generation) entre
    testes.
    """
    return MemoryManager(entity_capacity=DEFAULT_TEST_ENTITY_CAPACITY)


@pytest.fixture
def world(memory_manager: MemoryManager) -> World:
    """Fornece um `World` minimo, construido sobre `memory_manager`,
    com as pools GENERICAS do Pilar 1 (`transform`, `velocity`,
    `hitbox`, `sprite`, conforme `COMPONENT_SCHEMAS`) ja criadas e
    registradas via `memory_manager.create_pool`.

    NAO registra nenhum arquetipo nem nenhum `ISystem` -- cada modulo
    de teste registra exatamente o que precisa para o cenario sob teste,
    mantendo esta fixture neutra em relacao a qualquer produto (roguelite
    ou rhythm) especifico. Schemas especificos de produto (ex.:
    `MODIFIABLE_ATTRIBUTE_DTYPE`, `SCHEDULED_THREAT_DTYPE`) NUNCA sao
    criados aqui -- o modulo de teste que precisa deles cria suas
    proprias pools sobre este `world`/`memory_manager`.
    """
    for pool_name, dtype in COMPONENT_SCHEMAS.items():
        memory_manager.create_pool(pool_name, dtype)
    return World(memory_manager)


@pytest.fixture
def null_renderer() -> IRenderer:
    """Fornece uma instancia de `NullRenderer` (Pilar 2) ja inicializada
    (`initialize()` chamado), para injecao em sistemas de apresentacao
    sob teste sem abrir uma janela real nem depender de um driver de
    video verdadeiro (complementa `SDL_VIDEODRIVER=dummy` forcado no
    topo deste modulo).
    """
    renderer = NullRenderer()
    renderer.initialize(width=640, height=480, title="test")
    return renderer


@pytest.fixture
def null_input_provider() -> IInputProvider:
    """Fornece uma instancia de `NullInputProvider` (Pilar 2),
    permitindo que testes simulem estados de input deterministicos
    (acoes pressionadas/seguradas/soltas, eixos) sem depender de
    hardware ou driver de input real.
    """
    return NullInputProvider()


@pytest.fixture
def null_audio_engine() -> IAudioEngine:
    """Fornece uma instancia de `NullAudioEngine` (Pilar 2): nao abre
    nenhum dispositivo de audio real. Sua `get_clock()` e a UNICA fonte
    do clock nulo consumido por `null_audio_clock` abaixo -- evitando
    duas instancias de clock nulo divergentes coexistindo no mesmo teste.
    """
    return NullAudioEngine()


@pytest.fixture
def null_audio_clock(null_audio_engine: IAudioEngine) -> IAudioClock:
    """Fornece o `IAudioClock` retornado por
    `null_audio_engine.get_clock()` -- NUNCA uma instancia de
    `NullAudioClock` construida separadamente -- para que testes que
    controlam o tempo diretamente (ex.: `RhythmSpawnerSystem`) e testes
    que exercitam o engine de audio completo (`play_track`/
    `stop_track`/`play_one_shot`) sempre observem o MESMO relogio.

    Essencial para testar `RhythmSpawnerSystem` (Pilar 4) de forma
    deterministica: o teste avanca `now_seconds()`/
    `get_output_latency_seconds()` manualmente (via a API de controle
    exposta pela implementacao concreta de `NullAudioClock`) e verifica
    exatamente quantas entidades foram criadas por `update()`, sem
    depender de um relogio de audio real nem de I/O de audio.
    """
    return null_audio_engine.get_clock()


@pytest.fixture
def bind_quit_after():
    """Fornece uma funcao que monkeypatcha `.poll()`/`.wants_quit()` de QUALQUER
    `IInputProvider` ja construido (Null ou backend real) para que `GameLoop.run()`
    termine deterministicamente apos um numero fixo de chamadas de `poll()` --
    fixture oficial do Pilar 5 (ROADMAP M5.3), unificando os dois padroes ad-hoc
    que existiam espalhados pela suite antes desta fixture (uma subclasse de
    `NullInputProvider` que so funcionava com um input_provider criado do zero, e
    um closure `counting_poll()` inline repetido em varios testes que precisavam
    monkeypatchar um input_provider REAL ja construido por `CompositionRoot`).

    Uso: `poll_count = bind_quit_after(input_provider, quit_after=3)`, depois
    `game_loop.run()` -- `poll_count["n"]` fica disponivel para os testes que
    querem confirmar o numero exato de frames rodados (varios o fazem).
    """

    def _bind(input_provider, quit_after: int) -> dict:
        poll_count = {"n": 0}
        original_poll = input_provider.poll

        def counting_poll() -> None:
            original_poll()
            poll_count["n"] += 1

        input_provider.poll = counting_poll
        input_provider.wants_quit = lambda: poll_count["n"] >= quit_after
        return poll_count

    return _bind


@pytest.fixture
def synthetic_wav_factory(tmp_path):
    """
    Fabrica um arquivo WAV sintetico curto (clique metronomico a um BPM
    conhecido), para testar o backend de audio (Pilar 2) e o pipeline
    offline de IA (Pilar 4) sem depender de nenhum asset de audio real
    versionado no repositorio.

    Uso: `path = synthetic_wav_factory(bpm=120.0, duration_seconds=4.0)`.
    """
    import wave

    def _make(bpm: float = 120.0, duration_seconds: float = 4.0, sample_rate: int = 22050) -> str:
        n_samples = int(duration_seconds * sample_rate)
        t = np.arange(n_samples) / sample_rate
        beat_period = 60.0 / bpm
        # Um "clique" curto e audivel exatamente a cada batida: um envelope
        # de decaimento exponencial multiplicando um tom de 1 kHz.
        phase_in_beat = np.mod(t, beat_period)
        envelope = np.exp(-phase_in_beat * 40.0)
        click = envelope * np.sin(2 * np.pi * 1000.0 * t)
        samples = (click * 0.8 * np.iinfo(np.int16).max).astype(np.int16)

        path = tmp_path / f"synthetic_{bpm:.0f}bpm.wav"
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(samples.tobytes())
        return str(path)

    return _make
