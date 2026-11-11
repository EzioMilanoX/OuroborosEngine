# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""As regras da demo de terror (sem desenho): andar, a pilha da lanterna e o vulto.

E um gosto do blueprint SEN-04 L.A.N.T.E.R.N.: a luz e o que segura o vulto -- iluminado,
ele congela; no escuro, ele chega mais perto. Mas a pilha acaba, e so recarrega apagada.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Sequence, Tuple

ALTURA_OLHOS = 1.55
VELOCIDADE = 2.2  # unidades por segundo
GIRO = 1.9  # radianos por segundo (teclado)
SENSIBILIDADE = 0.0024  # radianos por pixel (mouse)
INCLINA_MAX = 1.2
RAIO_JOGADOR = 0.3
PASSO_SOM = 0.85  # um som de passo a cada tanto andado
LIMITES = (-8.0, 10.0, -18.0, 7.0)  # x min, x max, z min, z max
INICIO = (2.5, 5.5)
VULTO_INICIO = (6.6, -8.5)
CONE_VULTO = math.radians(20)  # o vulto congela dentro deste angulo do feixe
ALCANCE_LUZ = 18.0
PASSO_VULTO = 1.4  # quanto ele anda a cada salto, no escuro
INTERVALO_VULTO = 1.1  # segundos entre saltos
PEGOU = 1.3  # distancia em que ele te alcanca
GASTO_PILHA = 1 / 75  # por segundo acesa (75 s de pilha cheia)
RECARGA_PILHA = 1 / 50  # por segundo apagada (o dinamo)


def direcao(giro: float, inclina: float = 0.0) -> Tuple[float, float, float]:
    """Para onde se olha: giro 0 = para -z (para dentro da cena)."""
    c = math.cos(inclina)
    return (math.sin(giro) * c, math.sin(inclina), -math.cos(giro) * c)


@dataclass
class Estado:
    x: float = INICIO[0]
    z: float = INICIO[1]
    giro: float = 0.0
    inclina: float = -0.05
    passos: float = 0.0  # distancia andada (balanco da camera)
    pilha: float = 1.0
    acesa: bool = True
    vulto: Tuple[float, float] = VULTO_INICIO
    relogio_vulto: float = 0.0
    pego: float = 0.0  # >0: tempo da tela de "ele chegou"
    tempo: float = 0.0
    feixe: Tuple[float, float, float] = field(default_factory=lambda: direcao(0.0, -0.05))
    eventos: List[str] = field(default_factory=list)  # o que aconteceu neste passo (para o som)
    ultimo_passo: float = 0.0

    def olhos(self) -> Tuple[float, float, float]:
        return (self.x, ALTURA_OLHOS + 0.035 * math.sin(self.passos * 5.5), self.z)

    def luz_ligada(self) -> bool:
        return self.acesa and self.pilha > 0.0

    def iluminando(self, ponto: Tuple[float, float, float]) -> bool:
        """O ponto esta dentro do feixe (e perto o bastante)?"""
        if not self.luz_ligada():
            return False
        o = self.olhos()
        d = (ponto[0] - o[0], ponto[1] - o[1], ponto[2] - o[2])
        dist = math.sqrt(sum(c * c for c in d))
        if dist > ALCANCE_LUZ or dist < 1e-6:
            return False
        cos = sum(a * b for a, b in zip(d, self.feixe, strict=True)) / dist
        return cos > math.cos(CONE_VULTO)


def colidir(x: float, z: float, obstaculos: Sequence[Tuple[float, float, float]]) -> Tuple[float, float]:
    """Empurra o jogador (um circulo) para fora de cada obstaculo (circulos x, z, raio)."""
    for ox, oz, r in obstaculos:
        dx, dz = x - ox, z - oz
        d = math.hypot(dx, dz)
        minimo = r + RAIO_JOGADOR
        if d < minimo:
            if d < 1e-6:
                dx, dz, d = 1.0, 0.0, 1.0
            x, z = ox + dx / d * minimo, oz + dz / d * minimo
    x0, x1, z0, z1 = LIMITES
    return min(max(x, x0), x1), min(max(z, z0), z1)


def atualizar(e: Estado, dt: float, frente: float, lado: float, girar: float, alternar_luz: bool,
              olhar: Tuple[float, float] = (0.0, 0.0), obstaculos: Sequence[Tuple[float, float, float]] = ()) -> None:
    """Um passo das regras. `frente`/`lado`/`girar` em -1..1; `olhar` = quanto o mouse andou
    (pixels); `obstaculos` = circulos que nao se atravessam. Os eventos do passo (para o som)
    ficam em `e.eventos`."""
    e.tempo += dt
    e.eventos.clear()
    if e.pego > 0:
        e.pego -= dt
        if e.pego <= 0:
            reiniciar(e)
        return
    e.giro += girar * GIRO * dt + olhar[0] * SENSIBILIDADE
    e.inclina = min(max(e.inclina - olhar[1] * SENSIBILIDADE, -INCLINA_MAX), INCLINA_MAX)
    fx, _, fz = direcao(e.giro)
    dx = (fx * frente - fz * lado) * VELOCIDADE * dt
    dz = (fz * frente + fx * lado) * VELOCIDADE * dt
    x, z = colidir(e.x + dx, e.z + dz, obstaculos)
    e.passos += math.hypot(x - e.x, z - e.z)
    e.x, e.z = x, z
    if e.passos - e.ultimo_passo > PASSO_SOM:
        e.ultimo_passo = e.passos
        e.eventos.append("passo")

    k = 1 - math.exp(-8 * dt)  # o feixe segue o olhar com um pouco de atraso (a mao)
    alvo = direcao(e.giro, e.inclina)
    f = tuple(a + (b - a) * k for a, b in zip(e.feixe, alvo, strict=True))
    n = math.sqrt(sum(c * c for c in f))
    e.feixe = tuple(c / n for c in f)

    if alternar_luz:
        e.acesa = not e.acesa
        e.eventos.append("clique")
    if e.luz_ligada():
        e.pilha = max(0.0, e.pilha - GASTO_PILHA * dt)
    elif not e.acesa:
        e.pilha = min(1.0, e.pilha + RECARGA_PILHA * dt)

    e.relogio_vulto += dt
    if e.relogio_vulto >= INTERVALO_VULTO:
        e.relogio_vulto = 0.0
        vx, vz = e.vulto
        if not e.iluminando((vx, 1.6, vz)):  # no escuro, ele chega mais perto
            d = math.hypot(e.x - vx, e.z - vz)
            passo = min(PASSO_VULTO, max(0.0, d - 0.5))
            if passo > 0:
                e.vulto = (vx + (e.x - vx) / d * passo, vz + (e.z - vz) / d * passo)
                e.eventos.append("vulto")
    if math.hypot(e.x - e.vulto[0], e.z - e.vulto[1]) < PEGOU:
        e.pego = 2.0
        e.eventos.append("pegou")


def lado_do_vulto(e: Estado) -> float:
    """De que lado o vulto esta, para o som: -1 esquerda, 1 direita, 0 na frente ou atras."""
    vx, vz = e.vulto[0] - e.x, e.vulto[1] - e.z
    d = math.hypot(vx, vz) or 1.0
    return (vx * math.cos(e.giro) + vz * math.sin(e.giro)) / d


def batimento(e: Estado) -> float:
    """Segundos entre batidas do coracao: 0 = nao bate (longe); mais perto, mais rapido."""
    d = math.hypot(e.x - e.vulto[0], e.z - e.vulto[1])
    return 0.0 if d > 9.0 else 0.38 + 0.07 * d


def reiniciar(e: Estado) -> None:
    novo = Estado()
    for nome in ("x", "z", "giro", "inclina", "passos", "pilha", "acesa", "vulto", "relogio_vulto", "pego", "feixe",
                 "ultimo_passo"):
        setattr(e, nome, getattr(novo, nome))


def forca_da_luz(e: Estado) -> float:
    """1 com pilha boa; com menos de 25%, a lanterna falha (pisca) cada vez mais."""
    if not e.luz_ligada():
        return 0.0
    if e.pilha > 0.25:
        return 1.0
    falha = math.sin(e.tempo * 31.0) * math.sin(e.tempo * 7.3) > e.pilha * 3.2 - 0.2
    return (0.15 if falha else 0.85) * (0.4 + 0.6 * e.pilha / 0.25)
