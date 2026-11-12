# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""As regras da demo de terror (sem desenho): andar, a lanterna, o vulto e o mapa.

Um gosto do blueprint SEN-04 L.A.N.T.E.R.N.: a luz e o que segura o vulto -- iluminado,
ele congela; no escuro, ele chega mais perto. A pilha acaba e so recarrega apagada.
No mapa (`Estado(mapa=...)`): sete amuletos para levar ao santuario, pilhas extras e
armadilhas de urso que prendem, fazem barulho -- e o vulto ouve.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional, Sequence, Tuple

if TYPE_CHECKING:
    from games.terror_ps1.mapa import Mapa

ALTURA_OLHOS = 1.55
VELOCIDADE = 2.2  # unidades por segundo
GIRO = 1.9  # radianos por segundo (teclado)
SENSIBILIDADE = 0.0024  # radianos por pixel (mouse)
INCLINA_MAX = 1.2
RAIO_JOGADOR = 0.3
PASSO_SOM = 0.85  # um som de passo a cada tanto andado
LIMITES = (-8.0, 10.0, -18.0, 7.0)  # sem mapa: x min, x max, z min, z max
INICIO = (2.5, 5.5)
VULTO_INICIO = (6.6, -8.5)
CONE_VULTO = math.radians(20)  # o vulto congela dentro deste angulo do feixe
ALCANCE_LUZ = 18.0
PASSO_VULTO = 1.4  # quanto ele anda a cada salto, no escuro
INTERVALO_VULTO = 1.1  # segundos entre saltos
PEGOU = 1.3  # distancia em que ele te alcanca
LONGE_DEMAIS = 24.0  # no mapa: mais longe que isso, ele reaparece atras de voce
GASTO_PILHA = 1 / 75  # por segundo acesa (75 s de pilha cheia)
RECARGA_PILHA = 1 / 50  # por segundo apagada (o dinamo)
PEGAR_ITEM = 1.0  # distancia para pegar amuleto ou pilha
CARGA_PILHA = 0.5
ARMADILHA = 0.45  # distancia em que a armadilha fecha
PRESO = 3.0  # segundos presos (cada aperto de "soltar" tira um pouco)
FORCA_SOLTAR = 0.35
MANCANDO = 8.0  # segundos andando devagar depois de se soltar
CHEGOU_SANTUARIO = 2.5


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
    mapa: Optional["Mapa"] = None
    amuletos: List[Tuple[float, float, float]] = field(default_factory=list)  # os que faltam
    pilhas: List[Tuple[float, float]] = field(default_factory=list)
    armadilhas: List[List[float]] = field(default_factory=list)  # [x, z, fechada (0/1)]
    coletados: int = 0
    preso: float = 0.0
    mancando: float = 0.0
    venceu: bool = False

    def __post_init__(self) -> None:
        if self.mapa is not None and not self.amuletos and not self.coletados:
            from games.terror_ps1 import mapa as m
            self.x, self.z = m.INICIO
            self.vulto = (m.SANTUARIO[0], m.SANTUARIO[1] + 12.0)
            self.amuletos = list(self.mapa.amuletos)
            self.pilhas = list(self.mapa.pilhas)
            self.armadilhas = [[x, z, 0.0] for x, z in self.mapa.armadilhas]

    @property
    def total_amuletos(self) -> int:
        return self.coletados + len(self.amuletos)

    def olhos(self) -> Tuple[float, float, float]:
        manca = 0.06 * abs(math.sin(self.passos * 2.75)) if self.mancando > 0 else 0.0
        return (self.x, ALTURA_OLHOS - 0.35 * (self.preso > 0) - manca + 0.035 * math.sin(self.passos * 5.5), self.z)

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


def colidir(x: float, z: float, obstaculos: Sequence[Tuple[float, float, float]],
            caixas: Sequence[Tuple[float, float, float, float]] = (),
            limites: Tuple[float, float, float, float] = LIMITES) -> Tuple[float, float]:
    """Empurra o jogador (um circulo) para fora de cada obstaculo: circulos (x, z, raio) e
    caixas (x0, z0, x1, z1)."""
    for ox, oz, r in obstaculos:
        dx, dz = x - ox, z - oz
        d = math.hypot(dx, dz)
        minimo = r + RAIO_JOGADOR
        if d < minimo:
            if d < 1e-6:
                dx, dz, d = 1.0, 0.0, 1.0
            x, z = ox + dx / d * minimo, oz + dz / d * minimo
    for x0, z0, x1, z1 in caixas:
        px, pz = min(max(x, x0), x1), min(max(z, z0), z1)  # o ponto da caixa mais perto
        dx, dz = x - px, z - pz
        d = math.hypot(dx, dz)
        if d >= RAIO_JOGADOR:
            continue
        if d > 1e-6:
            x, z = px + dx / d * RAIO_JOGADOR, pz + dz / d * RAIO_JOGADOR
        else:  # o centro entrou na caixa: sai pela borda mais perto
            saidas = [(x - x0, x0 - RAIO_JOGADOR, z), (x1 - x, x1 + RAIO_JOGADOR, z),
                      (z - z0, x, z0 - RAIO_JOGADOR), (z1 - z, x, z1 + RAIO_JOGADOR)]
            _, x, z = min(saidas)
    lx0, lx1, lz0, lz1 = limites
    return min(max(x, lx0), lx1), min(max(z, lz0), lz1)


def atualizar(e: Estado, dt: float, frente: float, lado: float, girar: float, alternar_luz: bool,
              olhar: Tuple[float, float] = (0.0, 0.0), obstaculos: Sequence[Tuple[float, float, float]] = (),
              soltar: bool = False) -> None:
    """Um passo das regras. `frente`/`lado`/`girar` em -1..1; `olhar` = quanto o mouse andou
    (pixels); `obstaculos` = circulos extras que nao se atravessam (o mapa traz os seus);
    `soltar` = apertou o botao de se soltar da armadilha. Os eventos do passo (para o som)
    ficam em `e.eventos`."""
    e.tempo += dt
    e.eventos.clear()
    if e.pego > 0:
        e.pego -= dt
        if e.pego <= 0:
            reiniciar(e)
        return
    if e.venceu:
        return
    e.giro += girar * GIRO * dt + olhar[0] * SENSIBILIDADE
    e.inclina = min(max(e.inclina - olhar[1] * SENSIBILIDADE, -INCLINA_MAX), INCLINA_MAX)
    _andar(e, dt, frente, lado, soltar, obstaculos)

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

    if e.mapa is not None:
        _itens(e)
    _vulto(e, dt)


def _andar(e: Estado, dt: float, frente: float, lado: float, soltar: bool, obstaculos) -> None:
    if e.preso > 0:  # na armadilha: so sai com o tempo, mais rapido apertando "soltar"
        e.preso -= dt + (FORCA_SOLTAR if soltar else 0.0)
        if soltar:
            e.eventos.append("forca")
        if e.preso <= 0:
            e.preso = 0.0
            e.mancando = MANCANDO
        return
    e.mancando = max(0.0, e.mancando - dt)
    vel = VELOCIDADE * (0.45 if e.mancando > 0 else 1.0)
    fx, _, fz = direcao(e.giro)
    dx = (fx * frente - fz * lado) * vel * dt
    dz = (fz * frente + fx * lado) * vel * dt
    if e.mapa is not None:
        from games.terror_ps1.mapa import LIMITE
        x, z = colidir(e.x + dx, e.z + dz, list(obstaculos) + e.mapa.circulos_perto(e.x, e.z), e.mapa.caixas,
                       (-LIMITE, LIMITE, -LIMITE, LIMITE))
    else:
        x, z = colidir(e.x + dx, e.z + dz, obstaculos)
    e.passos += math.hypot(x - e.x, z - e.z)
    e.x, e.z = x, z
    if e.passos - e.ultimo_passo > PASSO_SOM:
        e.ultimo_passo = e.passos
        e.eventos.append("passo")


def _itens(e: Estado) -> None:
    from games.terror_ps1.mapa import SANTUARIO
    for a in list(e.amuletos):
        if math.hypot(e.x - a[0], e.z - a[1]) < PEGAR_ITEM:
            e.amuletos.remove(a)
            e.coletados += 1
            e.eventos.append("amuleto")
    for p in list(e.pilhas):
        if math.hypot(e.x - p[0], e.z - p[1]) < PEGAR_ITEM:
            e.pilhas.remove(p)
            e.pilha = min(1.0, e.pilha + CARGA_PILHA)
            e.eventos.append("pilha")
    for arm in e.armadilhas:
        if not arm[2] and e.preso <= 0 and math.hypot(e.x - arm[0], e.z - arm[1]) < ARMADILHA:
            arm[2] = 1.0
            e.preso = PRESO
            e.eventos.append("armadilha")
            _vulto_ouviu(e)
    if not e.amuletos and math.hypot(e.x - SANTUARIO[0], e.z - SANTUARIO[1]) < CHEGOU_SANTUARIO:
        e.venceu = True
        e.eventos.append("venceu")


def _vulto_ouviu(e: Estado) -> None:
    """O estalo de metal se ouve longe: o vulto corre metade do caminho ate o barulho."""
    vx, vz = e.vulto
    d = math.hypot(e.x - vx, e.z - vz)
    if d > 6.0:
        k = (d - max(6.0, d * 0.5)) / d
        e.vulto = (vx + (e.x - vx) * k, vz + (e.z - vz) * k)


def _vulto(e: Estado, dt: float) -> None:
    e.relogio_vulto += dt
    intervalo = INTERVALO_VULTO - 0.08 * e.coletados  # cada amuleto o deixa mais inquieto
    if e.relogio_vulto >= intervalo:
        e.relogio_vulto = 0.0
        vx, vz = e.vulto
        d = math.hypot(e.x - vx, e.z - vz)
        if e.mapa is not None and d > LONGE_DEMAIS:  # nunca longe demais: reaparece atras de voce
            fx, _, fz = direcao(e.giro)
            e.vulto = (e.x - fx * 16.0, e.z - fz * 16.0)
        elif not e.iluminando((vx, 1.6, vz)):  # no escuro, ele chega mais perto
            passo = min(PASSO_VULTO + 0.1 * e.coletados, max(0.0, d - 0.5))
            if passo > 0:
                e.vulto = (vx + (e.x - vx) / d * passo, vz + (e.z - vz) / d * passo)
                e.eventos.append("vulto")
    if math.hypot(e.x - e.vulto[0], e.z - e.vulto[1]) < PEGOU:
        e.pego = 2.0
        e.eventos.append("pegou")


def lado_de(e: Estado, x: float, z: float) -> float:
    """De que lado (x, z) esta, para o som: -1 esquerda, 1 direita, 0 na frente ou atras."""
    vx, vz = x - e.x, z - e.z
    d = math.hypot(vx, vz) or 1.0
    return (vx * math.cos(e.giro) + vz * math.sin(e.giro)) / d


def lado_do_vulto(e: Estado) -> float:
    return lado_de(e, *e.vulto)


def batimento(e: Estado) -> float:
    """Segundos entre batidas do coracao: 0 = nao bate (longe); mais perto, mais rapido."""
    d = math.hypot(e.x - e.vulto[0], e.z - e.vulto[1])
    return 0.0 if d > 9.0 else 0.38 + 0.07 * d


def amuleto_mais_perto(e: Estado) -> Optional[Tuple[float, float, float]]:
    if not e.amuletos:
        return None
    return min(e.amuletos, key=lambda a: math.hypot(e.x - a[0], e.z - a[1]))


def reiniciar(e: Estado) -> None:
    novo = Estado(mapa=e.mapa)
    for nome in ("x", "z", "giro", "inclina", "passos", "pilha", "acesa", "vulto", "relogio_vulto", "pego", "feixe",
                 "ultimo_passo", "amuletos", "pilhas", "armadilhas", "coletados", "preso", "mancando", "venceu"):
        setattr(e, nome, getattr(novo, nome))


def forca_da_luz(e: Estado) -> float:
    """1 com pilha boa; com menos de 25%, a lanterna falha (pisca) cada vez mais."""
    if not e.luz_ligada():
        return 0.0
    if e.pilha > 0.25:
        return 1.0
    falha = math.sin(e.tempo * 31.0) * math.sin(e.tempo * 7.3) > e.pilha * 3.2 - 0.2
    return (0.15 if falha else 0.85) * (0.4 + 0.6 * e.pilha / 0.25)
