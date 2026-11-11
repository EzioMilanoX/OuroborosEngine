# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Os sons da demo, sintetizados (sem arquivos de fora) e salvos como WAV na primeira vez.

No terror o som e metade do medo -- e a pista justa que o blueprint SEN-03 pede: o vulto
nao aparece no escuro, mas o galho que ele quebra estala do lado em que ele esta.
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Callable, Dict

import numpy as np

TAXA = 22050
VERSAO = "1"


def _ruido(n: int, rng) -> np.ndarray:
    return rng.uniform(-1, 1, n)


def _passa_baixa(x: np.ndarray, k: float) -> np.ndarray:
    """Filtro de um polo: k pequeno = mais abafado."""
    y = np.empty_like(x)
    acc = 0.0
    for i, v in enumerate(x):
        acc += k * (v - acc)
        y[i] = acc
    return y


def _env(n: int, ataque: float, queda: float) -> np.ndarray:
    t = np.arange(n) / TAXA
    return np.minimum(1.0, t / max(ataque, 1e-4)) * np.exp(-t / queda)


def passo(rng) -> np.ndarray:
    n = int(0.16 * TAXA)
    terra = _passa_baixa(_ruido(n, rng), 0.25) * _env(n, 0.004, 0.035)
    cascalho = _ruido(n, rng) * (rng.uniform(size=n) > 0.985) * _env(n, 0.01, 0.05)  # pedrinhas
    return 0.9 * terra + 0.35 * cascalho


def clique(rng) -> np.ndarray:
    n = int(0.05 * TAXA)
    t = np.arange(n) / TAXA
    return (0.6 * np.sin(2 * np.pi * 2400 * t) + 0.4 * _ruido(n, rng)) * _env(n, 0.0005, 0.006)


def batida(rng) -> np.ndarray:
    """Tum-tum: duas pancadas graves."""
    n = int(0.5 * TAXA)
    t = np.arange(n) / TAXA
    som = np.zeros(n)
    for inicio, forca in ((0.0, 1.0), (0.17, 0.7)):
        tt = np.clip(t - inicio, 0, None)
        f = 55 + 25 * np.exp(-tt / 0.03)  # a altura cai: o "baque"
        som += forca * np.sin(2 * np.pi * np.cumsum(f) / TAXA) * (t >= inicio) * np.exp(-tt / 0.07)
    return som


def galho(rng) -> np.ndarray:
    """O galho que quebra quando o vulto anda no escuro: estalos secos e um ranger."""
    n = int(0.45 * TAXA)
    som = np.zeros(n)
    for _ in range(4):
        i = int(rng.uniform(0, 0.12) * TAXA)
        m = int(0.02 * TAXA)
        som[i:i + m] += _ruido(m, rng) * _env(m, 0.0003, 0.004) * rng.uniform(0.5, 1.0)
    t = np.arange(n) / TAXA
    ranger = np.sin(2 * np.pi * (180 + 60 * np.sin(2 * np.pi * 7 * t)) * t) * _env(n, 0.05, 0.12)
    return som + 0.25 * ranger * (_passa_baixa(_ruido(n, rng), 0.3) + 0.5)


def pegou(rng) -> np.ndarray:
    n = int(1.4 * TAXA)
    t = np.arange(n) / TAXA
    grito = np.sin(2 * np.pi * (300 + 900 * t) * t) * 0.5 + _ruido(n, rng)
    return np.tanh(3 * grito) * _env(n, 0.002, 0.45) * 0.7


def zumbido(rng) -> np.ndarray:
    """8 s em laco perfeito: dois graves quase iguais (batem) e um vento abafado."""
    n = 8 * TAXA
    t = np.arange(n) / TAXA
    grave = 0.5 * np.sin(2 * np.pi * 41 * t) + 0.4 * np.sin(2 * np.pi * 41.5 * t) + 0.15 * np.sin(2 * np.pi * 82.25 * t)
    vento = _passa_baixa(_ruido(n, rng), 0.02) * 6
    sopro = 0.6 + 0.4 * np.sin(2 * np.pi * t / 8)  # o vento cresce e cai no mesmo laco
    som = 0.5 * grave + 0.5 * vento * sopro
    m = int(0.5 * TAXA)  # emenda: o fim se mistura com o comeco
    som[:m] = som[:m] * np.linspace(0, 1, m) + som[-m:] * np.linspace(1, 0, m)
    return som[:-m]


SONS: Dict[str, Callable] = {"passo": passo, "clique": clique, "batida": batida, "galho": galho,
                             "pegou": pegou, "zumbido": zumbido}


def _salvar(caminho: Path, som: np.ndarray) -> None:
    som = som / (np.abs(som).max() + 1e-9) * 0.9
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes((som * 32767).astype("<i2").tobytes())


def gerar(pasta: Path) -> Dict[str, Path]:
    """Gera (so na primeira vez, ou se `VERSAO` mudar) e devolve id -> caminho do WAV."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminhos = {nome: pasta / f"{nome}_v{VERSAO}.wav" for nome in SONS}
    for nome, f in SONS.items():
        if not caminhos[nome].exists():
            _salvar(caminhos[nome], f(np.random.default_rng(len(nome))))
    return caminhos
