# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Replay generico (ouroboros.bootstrap.replay): gravar, salvar, carregar, reproduzir
bit a bit e pegar a dessincronizacao no quadro em que acontece."""
from __future__ import annotations

import gc
import json

import numpy as np
import pytest

from ouroboros.bootstrap.replay import (
    REPLAY_FORMAT_VERSION,
    ActionMask,
    Replay,
    ReplayError,
    ReplayInputProvider,
    ReplayRecorder,
    world_state_hash,
)
from ouroboros.core.memory.memory_manager import MemoryManager
from ouroboros.core.systems.base_system import ISystem
from ouroboros.core.world import World
from ouroboros.interfaces.null.null_input_provider import NullInputProvider

ACOES = ("esquerda", "direita", "pular", "atirar")
CORPO = np.dtype([("x", np.float64), ("y", np.float64), ("vy", np.float64)])
TIRO = np.dtype([("x", np.float64), ("dx", np.float64)])


class _Jogo(ISystem):
    """Um joguinho deterministico: anda, pula, mira com eixo e cursor e atira com espalhamento
    sorteado por uma RNG com semente (a do replay)."""

    def __init__(self, inp, seed: int, trapaca: int = -1) -> None:
        self.inp = inp
        self.rng = np.random.default_rng(seed)
        self.quadro = 0
        self.trapaca = trapaca  # quadro em que o jogo "dessincroniza" (para o teste)

    def update(self, world, dt):
        c = world.get_pool("corpo").active_view()
        andar = float(self.inp.is_action_held("direita")) - float(self.inp.is_action_held("esquerda"))
        c["x"][0] += (andar * 3.0 + self.inp.get_axis("mira")) * dt
        if self.inp.is_action_pressed("pular") and c["y"][0] <= 0.0:
            c["vy"][0] = 5.0
        c["vy"][0] -= 9.8 * dt
        c["y"][0] = max(0.0, c["y"][0] + c["vy"][0] * dt)
        if self.inp.is_action_pressed("atirar"):
            e = world.create_entity("tiro")
            t = world.get_pool("tiro")
            v = t.active_view()
            row = t.dense_row_of(e & 0xFFFFFFFF)
            v["x"][row] = c["x"][0] + self.inp.get_cursor_position()[0] * 0.01
            v["dx"][row] = 4.0 + self.rng.normal()
        t = world.get_pool("tiro")
        t.active_view()["x"] += t.active_view()["dx"] * dt
        if self.quadro == self.trapaca:
            c["x"][0] += 1e-9
        self.quadro += 1


def _mundo(inp, seed: int, trapaca: int = -1):
    mm = MemoryManager(entity_capacity=256)
    mm.create_pool("corpo", CORPO)
    mm.create_pool("tiro", TIRO)
    w = World(mm)
    w.register_archetype("jogador", ("corpo",))
    w.register_archetype("tiro", ("tiro",))
    w.create_entity("jogador")
    w.register_system(_Jogo(inp, seed, trapaca))
    return w


def _dt(f: int) -> float:
    return 1 / 60 + (f % 7) * 1e-4  # dt variavel: o replay tem que usar o gravado, nao 1/60


def _entrada(inp: NullInputProvider, f: int) -> None:
    inp.set_action_held("direita", (f // 20) % 2 == 0)
    inp.set_action_held("esquerda", (f // 20) % 2 == 1)
    inp.set_action_held("pular", f % 45 < 3)
    inp.set_action_held("atirar", f % 11 == 0)
    inp.set_axis("mira", ((f * 37) % 100) / 100 - 0.5)
    inp.set_cursor_position(f % 640, 100)


def _gravar(frames: int = 300, seed: int = 1234, hash_every: int = 10):
    inp = NullInputProvider()
    w = _mundo(inp, seed)
    rec = ReplayRecorder(ACOES, axes=("mira",), cursor=True, capacity=64, hash_every=hash_every,
                         game_version="1.2.3")
    rec.start(seed=seed, meta={"fase": "teste"})
    estados = []
    for f in range(frames):
        _entrada(inp, f)
        inp.poll()
        rec.record(inp, _dt(f))
        w.step(_dt(f))
        if rec.wants_hash():
            rec.record_hash(world_state_hash(w, ("corpo", "tiro")))
        estados.append(world_state_hash(w, ("corpo", "tiro")))
    return rec, estados


def _reproduzir(replay: Replay, trapaca: int = -1):
    ri = ReplayInputProvider(replay)
    w = _mundo(ri, replay.seed, trapaca)
    estados = []
    while True:
        ri.poll()
        if not ri.has_more():
            break
        w.step(ri.current_dt())
        h = world_state_hash(w, ("corpo", "tiro"))
        if ri.wants_hash():
            ri.verify(h)
        estados.append(h)
    return ri, estados


def test_action_mask():
    m = ActionMask(ACOES)
    assert m.bit("pular") == 4 and m.bit("nada") == 0
    inp = NullInputProvider()
    inp.set_action_held("atirar", True)
    inp.set_action_held("esquerda", True)
    inp.poll()
    assert m.encode(inp) == 0b1001
    with pytest.raises(ValueError):
        ActionMask(["a", "a"])
    with pytest.raises(ValueError):
        ActionMask([str(i) for i in range(65)])


def test_reproduz_bit_a_bit_e_cresce_alem_da_capacidade():
    rec, original = _gravar()
    assert rec.capacity >= 300 and len(rec) == 300  # comecou com 64 e dobrou
    ri, reproduzido = _reproduzir(rec.replay())
    assert reproduzido == original
    assert not ri.desynced


def test_salva_e_carrega(tmp_path):
    rec, original = _gravar()
    caminho = tmp_path / "replays" / "ultima.json"
    assert rec.replay().save(caminho)
    r = Replay.load(caminho, expected_game_version="1.2.3")
    assert (r.seed, r.game_version, r.meta, r.actions, r.axis_names) == (1234, "1.2.3", {"fase": "teste"}, ACOES,
                                                                         ("mira",))
    assert r.frame_count == 300 and r.duration == pytest.approx(sum(_dt(f) for f in range(300)))
    assert len(r.hashes()) == 30
    assert _reproduzir(r)[1] == original
    assert json.loads(caminho.read_text(encoding="utf-8"))["format_version"] == REPLAY_FORMAT_VERSION


def test_dessincronizacao_aparece_no_primeiro_quadro_com_hash_depois_do_erro():
    rec, _ = _gravar(hash_every=10)
    ri, _ = _reproduzir(rec.replay(), trapaca=123)
    assert ri.desynced and ri.desync_frame == 130


def test_sem_hash_nada_para_conferir():
    rec, _ = _gravar(hash_every=0)
    r = rec.replay()
    assert len(r.hash_frames) == 0
    ri, _ = _reproduzir(r, trapaca=5)
    assert not ri.desynced


def test_provider_bordas_fim_e_dt():
    rec = ReplayRecorder(ACOES)
    for bits, dt in ((0, 0.01), (4, 0.02), (4, 0.03), (0, 0.04)):
        rec.record_bits(bits, dt)
    rp = ReplayInputProvider(rec.replay())
    assert not rp.has_more() and rp.frame == -1
    rp.poll()
    assert not rp.is_action_held("pular")
    rp.poll()
    assert rp.is_action_pressed("pular") and rp.is_action_held("pular") and rp.current_dt() == 0.02
    rp.poll()
    assert rp.is_action_held("pular") and not rp.is_action_pressed("pular")
    rp.poll()
    assert rp.is_action_released("pular") and not rp.is_action_held("inexistente")
    rp.poll()
    assert not rp.has_more() and rp.current_dt() == pytest.approx(1 / 60)
    assert rp.get_axis("mira") == 0.0 and rp.get_cursor_position() == (0.0, 0.0)
    assert rp.wants_quit() is False and rp.verify(123)
    rp.set_rumble(1, 1, 1)
    rp.load_bindings("x.json")


@pytest.mark.parametrize("conteudo,erro", [
    (None, "ausente"),
    ("{nao e json", "ausente"),
    ('{"format": "outra coisa"}', "nao e um arquivo"),
    ('{"format": "ouroboros-replay", "format_version": 99}', "mais novo"),
    ('{"format": "ouroboros-replay", "format_version": 1, "frames": 2}', "incompleto"),
    ('{"format": "ouroboros-replay", "format_version": 1, "frames": 2, "actions": [], "bits": "!!", "dt": ""}',
     "corrompido"),
])
def test_carregar_arquivo_ruim_levanta_replay_error(tmp_path, conteudo, erro):
    caminho = tmp_path / "r.json"
    if conteudo is not None:
        caminho.write_text(conteudo, encoding="utf-8")
    with pytest.raises(ReplayError, match=erro):
        Replay.load(caminho)


def test_versao_do_jogo_diferente(tmp_path):
    rec, _ = _gravar(frames=5)
    rec.replay().save(tmp_path / "r.json")
    with pytest.raises(ReplayError, match="versao"):
        Replay.load(tmp_path / "r.json", expected_game_version="2.0.0")
    assert Replay.load(tmp_path / "r.json").game_version == "1.2.3"


def test_start_recomeca_e_replay_e_copia():
    rec, _ = _gravar(frames=20)
    r = rec.replay()
    rec.start(seed=9)
    assert len(rec) == 0 and not rec and rec.seed == 9 and rec.meta == {"fase": "teste"}
    assert r.frame_count == 20
    with pytest.raises(RuntimeError):
        rec.record_hash(1)


def test_gravar_quadro_nao_dispara_o_coletor():
    rec = ReplayRecorder(ACOES, axes=("mira",), capacity=20000)
    inp = NullInputProvider()
    inp.set_action_held("pular", True)
    inp.poll()
    coletas = []

    def sonda(fase, info):
        if fase == "start":
            coletas.append(info)

    gc.collect()
    gc.callbacks.append(sonda)
    try:
        for _ in range(20000):
            rec.record(inp, 1 / 60)
    finally:
        gc.callbacks.remove(sonda)
    assert coletas == []
