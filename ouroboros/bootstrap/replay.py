# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Replay: gravar as entradas de cada quadro e reproduzir a partida igualzinha.

Veio do BulletHell (`bullethell/replay.py`, que veio do `ReplayRecorder` do jogo legado) e
ficou generico. A ideia e a de sempre em jogo deterministico: o estado da partida e funcao
de (semente, entradas de cada quadro, dt de cada quadro). Grave isso e reproduza com os
MESMOS sistemas -- o `World` nao sabe que e replay, porque `ReplayInputProvider` cumpre o
contrato de `IInputProvider` devolvendo o que foi gravado em vez de ler o teclado.

Pecas:

* `ActionMask` -- as acoes que entram no replay, uma por bit (ate 64): um `int` por quadro.
* `ReplayRecorder` -- grava (bits, dt[, eixos][, cursor]) em arrays pre-alocados: gravar um
  quadro nao cria objeto (Zero-GC). Cheio, dobra de tamanho (raro, amortizado; ajuste
  `capacity` para a partida tipica e nunca acontece).
* `Replay` -- o que foi gravado + semente + versao do jogo + `meta` (o que o jogo precisar
  para remontar a partida: chefe, arma, dificuldade...). `save`/`load` em JSON (arrays
  comprimidos em base64), escrita atomica pelo `SaveFile`.
* `ReplayInputProvider` -- o `IInputProvider` que toca o replay.
* Dessincronizacao (opcional): com `hash_every=N`, o jogo grava um hash do estado a cada N
  quadros (`world_state_hash`, CRC32 das pools escolhidas) e, ao reproduzir, confere; o
  primeiro quadro diferente fica em `desync_frame`. Pega bug de determinismo (RNG global,
  ordem de dict, dt real vazando) no quadro em que acontece, nao minutos depois.

Fluxo, no jogo:

    rec = ReplayRecorder(ACOES, game_version=__version__, hash_every=60)
    rec.start(seed=semente, meta={"boss": "decalogue"})
    # a cada quadro de partida, antes do world.step:
    rec.record(input_provider, dt)
    world.step(dt)
    if rec.wants_hash():
        rec.record_hash(world_state_hash(world, POOLS))
    # no fim: rec.replay().save(caminho)  -- ou guarde em memoria

    ri = ReplayInputProvider(Replay.load(caminho, expected_game_version=__version__))
    # monte o World com `ri` como input e a semente de ri.replay.seed; a cada quadro:
    ri.poll()
    if not ri.has_more(): fim
    world.step(ri.current_dt())
    if ri.wants_hash() and not ri.verify(world_state_hash(world, POOLS)): avisar
"""
from __future__ import annotations

import base64
import zlib
from typing import Dict, Optional, Sequence, Tuple

import numpy as np

from ouroboros.bootstrap.save_file import SaveFile
from ouroboros.interfaces.input_provider import IInputProvider

REPLAY_FORMAT = "ouroboros-replay"
REPLAY_FORMAT_VERSION = 1
MAX_ACTIONS = 64
DEFAULT_DT = 1 / 60


class ReplayError(ValueError):
    """Arquivo de replay ausente, corrompido, de formato novo demais ou de outra versao do jogo."""


class ActionMask:
    """As acoes gravadas, na ordem dos bits. A ordem faz parte do formato: mudou a lista,
    replays antigos leem as teclas erradas (por isso ela vai junto no arquivo)."""

    def __init__(self, actions: Sequence[str]) -> None:
        acoes = tuple(actions)
        if len(acoes) > MAX_ACTIONS:
            raise ValueError(f"no maximo {MAX_ACTIONS} acoes num replay (vieram {len(acoes)})")
        if len(set(acoes)) != len(acoes):
            raise ValueError("acao repetida no replay")
        self._actions = acoes
        self._bits: Dict[str, int] = {a: 1 << i for i, a in enumerate(acoes)}
        self._pares = tuple(self._bits.items())  # percorrer uma tupla pronta nao cria objeto

    @property
    def actions(self) -> Tuple[str, ...]:
        return self._actions

    def bit(self, action_name: str) -> int:
        """O bit da acao (0 se ela nao faz parte do replay)."""
        return self._bits.get(action_name, 0)

    def encode(self, input_provider: IInputProvider) -> int:
        """O estado `is_action_held` de todas as acoes, um bit cada."""
        bits = 0
        for acao, b in self._pares:
            if input_provider.is_action_held(acao):
                bits |= b
        return bits


def world_state_hash(world, pool_names: Sequence[str], seed: int = 0) -> int:
    """CRC32 do estado das pools (contagem, entidades e dados ativos), na ordem dada.

    Escolha as pools que DEVEM ser iguais entre gravar e reproduzir (gameplay); deixe de fora
    as de apresentacao que dependem do relogio real (particulas de enfeite, por exemplo).
    Le os arrays sem copiar; feito a cada N quadros, nao pesa."""
    h = seed & 0xFFFFFFFF
    for nome in pool_names:
        pool = world.get_pool(nome)
        h = zlib.crc32(pool.count.to_bytes(8, "little"), h)
        h = zlib.crc32(np.ascontiguousarray(pool.active_entity_indices()), h)
        h = zlib.crc32(np.ascontiguousarray(pool.active_view()), h)
    return h


# --------------------------------------------------------------------- arquivo


def _pack(arr: np.ndarray) -> str:
    return base64.b64encode(zlib.compress(np.ascontiguousarray(arr).astype(arr.dtype.newbyteorder("<")).tobytes(),
                                          6)).decode("ascii")


def _unpack(texto: str, dtype: str, shape: Tuple[int, ...]) -> np.ndarray:
    try:
        dados = zlib.decompress(base64.b64decode(texto.encode("ascii"), validate=True))
        arr = np.frombuffer(dados, dtype=np.dtype(dtype).newbyteorder("<")).astype(dtype)
        return arr.reshape(shape)
    except (ValueError, TypeError, zlib.error, AttributeError) as erro:
        raise ReplayError(f"replay corrompido: {erro}") from None


class Replay:
    """Uma partida gravada. Os arrays tem `frame_count` linhas; `axes`/`cursor` so existem se
    foram gravados. Trate como somente-leitura."""

    def __init__(self, actions: Sequence[str], bits: np.ndarray, dts: np.ndarray, *, seed: int = 0,
                 game_version: str = "", meta: Optional[dict] = None, axis_names: Sequence[str] = (),
                 axes: Optional[np.ndarray] = None, cursor: Optional[np.ndarray] = None,
                 hash_frames: Optional[np.ndarray] = None, hash_values: Optional[np.ndarray] = None) -> None:
        self.mask = ActionMask(actions)
        self.bits = np.asarray(bits, dtype=np.uint64)
        self.dts = np.asarray(dts, dtype=np.float64)
        n = len(self.bits)
        if self.dts.shape != (n,):
            raise ReplayError("bits e dts com tamanhos diferentes")
        self.seed = int(seed)
        self.game_version = str(game_version)
        self.meta = dict(meta or {})
        self.axis_names = tuple(axis_names)
        self.axes = (np.asarray(axes, dtype=np.float64).reshape(n, len(self.axis_names)) if self.axis_names
                     else np.zeros((n, 0), dtype=np.float64))
        self.cursor = None if cursor is None else np.asarray(cursor, dtype=np.float64).reshape(n, 2)
        self.hash_frames = np.zeros(0, np.int64) if hash_frames is None else np.asarray(hash_frames, np.int64)
        self.hash_values = np.zeros(0, np.uint32) if hash_values is None else np.asarray(hash_values, np.uint32)
        if self.hash_frames.shape != self.hash_values.shape:
            raise ReplayError("quadros e valores de hash com tamanhos diferentes")

    @property
    def actions(self) -> Tuple[str, ...]:
        return self.mask.actions

    @property
    def frame_count(self) -> int:
        return len(self.bits)

    def __len__(self) -> int:
        return self.frame_count

    @property
    def duration(self) -> float:
        """Segundos de jogo gravados (soma dos dt)."""
        return float(self.dts.sum())

    def hashes(self) -> Dict[int, int]:
        """{quadro: hash} gravados."""
        return dict(zip(self.hash_frames.tolist(), self.hash_values.tolist()))

    # ------------------------------------------------------------------ arquivo
    def to_dict(self) -> dict:
        d = {
            "format": REPLAY_FORMAT, "format_version": REPLAY_FORMAT_VERSION,
            "game_version": self.game_version, "seed": self.seed, "meta": self.meta,
            "actions": list(self.actions), "axes": list(self.axis_names), "cursor": self.cursor is not None,
            "frames": self.frame_count, "hashes": len(self.hash_frames),
            "bits": _pack(self.bits), "dt": _pack(self.dts),
            "hash_frames": _pack(self.hash_frames), "hash_values": _pack(self.hash_values),
        }
        if self.axis_names:
            d["axis_values"] = _pack(self.axes)
        if self.cursor is not None:
            d["cursor_values"] = _pack(self.cursor)
        return d

    @classmethod
    def from_dict(cls, d: dict, expected_game_version: Optional[str] = None) -> "Replay":
        if not isinstance(d, dict) or d.get("format") != REPLAY_FORMAT:
            raise ReplayError("nao e um arquivo de replay")
        versao = d.get("format_version")
        if not isinstance(versao, int) or versao > REPLAY_FORMAT_VERSION:
            raise ReplayError(f"formato de replay {versao!r} mais novo que este jogo entende")
        jogo = str(d.get("game_version", ""))
        if expected_game_version is not None and jogo != expected_game_version:
            raise ReplayError(f"replay gravado na versao {jogo!r}, este jogo e {expected_game_version!r}")
        try:
            n, nh = int(d["frames"]), int(d.get("hashes", 0))
            eixos = tuple(d.get("axes", ()))
            return cls(
                d["actions"], _unpack(d["bits"], "uint64", (n,)), _unpack(d["dt"], "float64", (n,)),
                seed=int(d.get("seed", 0)), game_version=jogo, meta=d.get("meta") or {}, axis_names=eixos,
                axes=_unpack(d["axis_values"], "float64", (n, len(eixos))) if eixos else None,
                cursor=_unpack(d["cursor_values"], "float64", (n, 2)) if d.get("cursor") else None,
                hash_frames=_unpack(d.get("hash_frames", ""), "int64", (nh,)) if nh else None,
                hash_values=_unpack(d.get("hash_values", ""), "uint32", (nh,)) if nh else None,
            )
        except (KeyError, TypeError) as erro:
            raise ReplayError(f"replay incompleto: {erro}") from None
        except ValueError as erro:
            if isinstance(erro, ReplayError):
                raise
            raise ReplayError(f"replay invalido: {erro}") from None

    def save(self, path) -> bool:
        """Grava atomicamente (`SaveFile`). Devolve se conseguiu; nunca levanta por disco."""
        return SaveFile(path).write(self.to_dict())

    @classmethod
    def load(cls, path, expected_game_version: Optional[str] = None) -> "Replay":
        """Le um replay. Levanta `ReplayError` (ausente, corrompido, de formato mais novo ou,
        se `expected_game_version` for dado, de outra versao do jogo -- replay de outra
        versao quase sempre dessincroniza, porque as regras mudaram)."""
        d = SaveFile(path).read()
        if not d:
            raise ReplayError(f"replay ausente ou ilegivel: {path}")
        return cls.from_dict(d, expected_game_version)


# --------------------------------------------------------------------- gravar


class ReplayRecorder:
    """Grava uma partida quadro a quadro. `capacity`: quadros pre-alocados (36000 = 10 min a
    60 qps); `hash_every`: 0 desliga a verificacao de dessincronizacao."""

    def __init__(self, actions: Sequence[str], *, axes: Sequence[str] = (), cursor: bool = False,
                 capacity: int = 36000, hash_every: int = 0, game_version: str = "", seed: int = 0,
                 meta: Optional[dict] = None) -> None:
        self.mask = ActionMask(actions)
        self.axis_names = tuple(axes)
        self._grava_cursor = bool(cursor)
        self.hash_every = int(hash_every)
        self.game_version = str(game_version)
        cap = max(1, int(capacity))
        self._bits = np.zeros(cap, dtype=np.uint64)
        self._dts = np.zeros(cap, dtype=np.float64)
        self._axes = np.zeros((cap, len(self.axis_names)), dtype=np.float64)
        self._cursor = np.zeros((cap, 2), dtype=np.float64) if self._grava_cursor else None
        hcap = cap // self.hash_every + 1 if self.hash_every > 0 else 1
        self._hf = np.zeros(hcap, dtype=np.int64)
        self._hv = np.zeros(hcap, dtype=np.uint32)
        self._n = 0
        self._nh = 0
        self.seed = int(seed)
        self.meta: dict = dict(meta or {})

    def start(self, seed: Optional[int] = None, meta: Optional[dict] = None) -> None:
        """Comeca uma gravacao nova (reaproveita os arrays)."""
        self._n = self._nh = 0
        if seed is not None:
            self.seed = int(seed)
        self.meta = dict(meta or {}) if meta is not None else self.meta

    @property
    def frame_count(self) -> int:
        return self._n

    def __len__(self) -> int:
        return self._n

    def __bool__(self) -> bool:
        return self._n > 0

    @property
    def capacity(self) -> int:
        return len(self._bits)

    def _crescer(self) -> None:
        cap = 2 * len(self._bits)
        self._bits = np.resize(self._bits, cap)
        self._dts = np.resize(self._dts, cap)
        self._axes = np.resize(self._axes, (cap, len(self.axis_names)))
        if self._cursor is not None:
            self._cursor = np.resize(self._cursor, (cap, 2))

    def record(self, input_provider: IInputProvider, dt: float) -> int:
        """Grava o estado ATUAL do input (depois do `poll()` do quadro) e o dt que o
        `world.step` vai usar. Devolve o indice do quadro."""
        i = self.record_bits(self.mask.encode(input_provider), dt)
        if self.axis_names:
            linha = self._axes[i]
            for k, nome in enumerate(self.axis_names):
                linha[k] = input_provider.get_axis(nome)
        if self._cursor is not None:
            x, y = input_provider.get_cursor_position()
            self._cursor[i, 0], self._cursor[i, 1] = x, y
        return i

    def record_bits(self, bits: int, dt: float) -> int:
        """Grava um quadro ja codificado (ex.: vindo da rede, ou de um teste)."""
        i = self._n
        if i >= len(self._bits):
            self._crescer()
        self._bits[i] = bits
        self._dts[i] = dt
        self._n = i + 1
        return i

    def wants_hash(self) -> bool:
        """O ultimo quadro gravado e um dos que levam hash? (Calcule so quando pedir.)"""
        return self.hash_every > 0 and self._n > 0 and (self._n - 1) % self.hash_every == 0

    def record_hash(self, state_hash: int) -> None:
        """O hash do estado DEPOIS do `world.step` do ultimo quadro gravado."""
        if self._n == 0:
            raise RuntimeError("record_hash antes de gravar algum quadro")
        if self._nh >= len(self._hf):
            self._hf = np.resize(self._hf, 2 * len(self._hf))
            self._hv = np.resize(self._hv, 2 * len(self._hv))
        self._hf[self._nh] = self._n - 1
        self._hv[self._nh] = state_hash & 0xFFFFFFFF
        self._nh += 1

    def replay(self) -> Replay:
        """O que foi gravado ate agora, numa copia independente (a gravacao pode seguir)."""
        n, nh = self._n, self._nh
        return Replay(self.mask.actions, self._bits[:n].copy(), self._dts[:n].copy(), seed=self.seed,
                      game_version=self.game_version, meta=self.meta, axis_names=self.axis_names,
                      axes=self._axes[:n].copy() if self.axis_names else None,
                      cursor=self._cursor[:n].copy() if self._cursor is not None else None,
                      hash_frames=self._hf[:nh].copy(), hash_values=self._hv[:nh].copy())


# --------------------------------------------------------------------- reproduzir


class ReplayInputProvider(IInputProvider):
    """`IInputProvider` sintetico: cada `poll()` avanca para o proximo quadro gravado em vez
    de consultar o SO. Depois do ultimo quadro, `has_more()` fica falso e tudo solta."""

    def __init__(self, replay: Replay) -> None:
        self.replay = replay
        self._mask = replay.mask
        self._bits = replay.bits.tolist()  # leitura escalar rapida, sem objeto numpy por quadro
        self._dts = replay.dts.tolist()
        self._n = len(self._bits)
        self._eixo = {nome: k for k, nome in enumerate(replay.axis_names)}
        self._hashes = replay.hashes()
        self._idx = -1
        self._current = 0
        self._previous = 0
        self.desync_frame: Optional[int] = None

    # -- IInputProvider -------------------------------------------------------
    def load_bindings(self, bindings_path: str) -> None:
        pass

    def poll(self) -> None:
        self._previous = self._current
        self._idx += 1
        self._current = self._bits[self._idx] if self._idx < self._n else 0

    def is_action_pressed(self, action_name: str) -> bool:
        b = self._mask.bit(action_name)
        return bool(self._current & b) and not bool(self._previous & b)

    def is_action_held(self, action_name: str) -> bool:
        return bool(self._current & self._mask.bit(action_name))

    def is_action_released(self, action_name: str) -> bool:
        b = self._mask.bit(action_name)
        return bool(self._previous & b) and not bool(self._current & b)

    def get_axis(self, axis_name: str) -> float:
        k = self._eixo.get(axis_name)
        if k is None or not self.has_more():
            return 0.0
        return float(self.replay.axes[self._idx, k])

    def get_cursor_position(self) -> Tuple[float, float]:
        c = self.replay.cursor
        if c is None or not self.has_more():
            return (0.0, 0.0)
        return (float(c[self._idx, 0]), float(c[self._idx, 1]))

    def wants_quit(self) -> bool:
        return False

    def set_rumble(self, low_freq: float, high_freq: float, duration_sec: float) -> None:
        pass  # replay nao vibra o controle de quem assiste

    # -- driver do replay ---------------------------------------------------------
    @property
    def frame(self) -> int:
        """O quadro atual (o do ultimo `poll()`); -1 antes do primeiro."""
        return self._idx

    def has_more(self) -> bool:
        """O ultimo `poll()` caiu num quadro gravado?"""
        return 0 <= self._idx < self._n

    def current_dt(self, default: float = DEFAULT_DT) -> float:
        """O dt gravado para o quadro atual (fora da gravacao: `default`)."""
        return self._dts[self._idx] if self.has_more() else default

    def wants_hash(self) -> bool:
        """Este quadro tem hash gravado para conferir?"""
        return self._idx in self._hashes

    def verify(self, state_hash: int) -> bool:
        """Confere o hash do estado depois do `world.step` deste quadro. Quadro sem hash
        gravado conta como certo. O primeiro erro fica em `desync_frame`."""
        esperado = self._hashes.get(self._idx)
        if esperado is None or esperado == (state_hash & 0xFFFFFFFF):
            return True
        if self.desync_frame is None:
            self.desync_frame = self._idx
        return False

    @property
    def desynced(self) -> bool:
        return self.desync_frame is not None
