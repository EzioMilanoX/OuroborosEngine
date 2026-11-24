# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""`MundoColisao3D`: o cenario solido de um jogo 3D e as consultas contra ele.

O que mora aqui e o cenario que fica parado (ou quase): paredes, troncos, pedras, pilares,
o chao por mapa de alturas (`Relevo`). As formas ficam em arrays pre-alocados (SoA, NumPy)
e numa grade espacial uniforme em x/z (broadphase): cada consulta so testa as formas das
celulas que toca. Personagem, raio de visao e camera consultam isso a cada quadro.

Caminho quente sem lixo (Zero-GC): as consultas nao criam lista, tupla nem objeto por forma
testada -- candidatos vao para um buffer pre-alocado, e o resultado vai para um
`ResultadoRaio`/`ResultadoMovimento` que o chamador pode reaproveitar entre quadros.

Mudar o cenario (`adicionar`, `atualizar`, `remover`) marca a grade como suja; a proxima
consulta a reconstroi (O(formas), aloca). Por isso, o que se move todo quadro (o monstro, um
projetil) NAO entra aqui: teste-o direto com `primitivas.contato`/`sobrepoe`.

Movimento (`mover_capsula`/`mover_esfera`): desliza contra o mundo. O deslocamento e
dividido em passos de no maximo meio raio (nao atravessa parede fina), e em cada passo o
corpo e empurrado para fora de tudo o que invade, algumas vezes ate assentar. Contato com
normal para cima (ate `rampa_max_graus`) e chao; o resto e parede -- e rampa ingreme demais
empurra so na horizontal, para ninguem subir uma parede inclinada so andando contra ela.
O `Relevo` e sempre chao (empurra para cima). Fora de escopo: degraus (subir um meio-fio
automaticamente), atrito e corpos dinamicos empurrando uns aos outros.
"""
from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

import numpy as np

from ouroboros.core.colisao3d.primitivas import (
    AABB,
    INF,
    Capsula,
    Esfera,
    Forma,
    Vec3,
    _k_contato_esfera_aabb,
    _k_contato_esferas,
    _k_param_segmento,
    _k_param_segmento_aabb,
    _k_params_segmentos,
    _k_raio_aabb,
    _k_raio_capsula,
    _k_raio_esfera,
)
from ouroboros.core.colisao3d.relevo import Relevo

TIPO_CAIXA, TIPO_ESFERA, TIPO_CAPSULA = 0, 1, 2
TODAS_CAMADAS = 0xFFFFFFFF
NENHUMA = -1  # `ResultadoRaio.forma` quando o raio nao acertou nada
RELEVO = -2  # `ResultadoRaio.forma` quando o que o raio acertou foi o chao do `Relevo`

_MAX_NORMAIS = 8
_MAX_PASSOS = 64
_ITERACOES = 4
_FOLGA = 1e-5  # empurra um fio alem do contato, para o proximo teste nao reencontrar o mesmo


class ResultadoRaio:
    """Preenchido por `MundoColisao3D.raycast`. Reaproveitavel entre quadros."""

    __slots__ = ("acertou", "distancia", "ponto", "normal", "forma")

    def __init__(self) -> None:
        self.acertou = False
        self.distancia = INF
        self.ponto = [0.0, 0.0, 0.0]
        self.normal = [0.0, 0.0, 0.0]
        self.forma = NENHUMA  # id da forma, `RELEVO` ou `NENHUMA`


class ResultadoMovimento:
    """Preenchido por `MundoColisao3D.mover_*`. Reaproveitavel entre quadros.

    `posicao`: onde o corpo parou (o mesmo ponto de referencia que entrou: o pe da capsula,
    o centro da esfera). `no_chao`: encostou em chao (contato ate a rampa maxima, ou o
    relevo). `bateu`: encostou em parede/teto. `normais`: as normais de contato, para
    `ajustar_velocidade`."""

    __slots__ = ("posicao", "no_chao", "normal_chao", "bateu", "_normais", "_n")

    def __init__(self) -> None:
        self.posicao = [0.0, 0.0, 0.0]
        self.no_chao = False
        self.normal_chao = [0.0, 1.0, 0.0]
        self.bateu = False
        self._normais = [0.0] * (3 * _MAX_NORMAIS)
        self._n = 0

    def _limpar(self) -> None:
        self.no_chao = False
        self.bateu = False
        self.normal_chao[0], self.normal_chao[1], self.normal_chao[2] = 0.0, 1.0, 0.0
        self._n = 0

    def _anotar(self, nx: float, ny: float, nz: float) -> None:
        if self._n < _MAX_NORMAIS:
            k = 3 * self._n
            self._normais[k], self._normais[k + 1], self._normais[k + 2] = nx, ny, nz
            self._n += 1

    @property
    def contatos(self) -> int:
        return self._n

    def ajustar_velocidade(self, vx: float, vy: float, vz: float) -> Vec3:
        """Tira da velocidade o que entra nas superficies tocadas (desliza na parede, para de
        cair no chao) -- chame com a velocidade do quadro depois do `mover_*`."""
        ns = self._normais
        for k in range(0, 3 * self._n, 3):
            d = vx * ns[k] + vy * ns[k + 1] + vz * ns[k + 2]
            if d < 0.0:
                vx, vy, vz = vx - d * ns[k], vy - d * ns[k + 1], vz - d * ns[k + 2]
        return (vx, vy, vz)


class MundoColisao3D:
    """O cenario solido. `limites_xz` = (x0, z0, x1, z1) da grade; formas fora dela continuam
    valendo nas consultas de sobreposicao e no movimento (caem nas celulas da borda), mas o
    raio so percorre a grade -- deixe a grade cobrir o mapa. `tamanho_celula`: de 1 a 4 vezes
    o tamanho tipico das formas costuma ser bom (TerrorPS1 usava 4 m para troncos de ~0,4 m)."""

    def __init__(self, limites_xz: Tuple[float, float, float, float], tamanho_celula: float = 4.0,
                 max_formas: int = 4096, rampa_max_graus: float = 50.0) -> None:
        x0, z0, x1, z1 = (float(v) for v in limites_xz)
        if x1 <= x0 or z1 <= z0:
            raise ValueError("limites_xz precisa ser (x0, z0, x1, z1) com x1 > x0 e z1 > z0")
        if tamanho_celula <= 0:
            raise ValueError("tamanho_celula precisa ser positivo")
        self._gx0, self._gz0 = x0, z0
        self._cel = float(tamanho_celula)
        self._cols = max(1, math.ceil((x1 - x0) / self._cel))
        self._rows = max(1, math.ceil((z1 - z0) / self._cel))
        self._max = int(max_formas)
        self._cos_rampa = math.cos(math.radians(rampa_max_graus))
        # SoA: a fonte da verdade (vetorizavel por quem quiser ler)
        self._dados = np.zeros((self._max, 7), dtype=np.float64)
        self._tipo = np.zeros(self._max, dtype=np.int8)
        self._camada = np.zeros(self._max, dtype=np.uint32)
        self._ativo = np.zeros(self._max, dtype=np.bool_)
        self._topo = 0  # ids [0, _topo) ja usados alguma vez
        self._livres: List[int] = []
        self.relevo: Optional[Relevo] = None
        # espelhos em listas Python (leitura escalar rapida), refeitos em `construir`
        self._sujo = True
        self._L_dados: List[List[float]] = []
        self._L_tipo: List[int] = []
        self._L_camada: List[int] = []
        self._off: List[int] = [0] * (self._cols * self._rows + 1)
        self._ent: List[int] = []
        # buffers de consulta, pre-alocados
        self._marca = [0] * self._max
        self._carimbo = 0
        self._cand = [0] * self._max
        self._s = [0.0, 0.0, 0.0]
        self._st = [0.0, 0.0]
        self._res_raio = ResultadoRaio()
        self._res_mov = ResultadoMovimento()

    # ================================================================== cenario
    def definir_relevo(self, relevo: Optional[Relevo]) -> None:
        """O chao por mapa de alturas (ou None para tirar)."""
        self.relevo = relevo

    def _novo_id(self) -> int:
        if self._livres:
            return self._livres.pop()
        if self._topo >= self._max:
            raise OverflowError(f"MundoColisao3D cheio ({self._max} formas): aumente max_formas")
        self._topo += 1
        return self._topo - 1

    def _gravar(self, fid: int, forma: Forma) -> None:
        d = self._dados[fid]
        d[:] = 0.0
        if isinstance(forma, AABB):
            mn, mx = forma.minimo, forma.maximo
            if mn[0] > mx[0] or mn[1] > mx[1] or mn[2] > mx[2]:
                raise ValueError("AABB com minimo maior que maximo")
            d[0:3], d[3:6] = mn, mx
            self._tipo[fid] = TIPO_CAIXA
        elif isinstance(forma, Esfera):
            d[0:3], d[3] = forma.centro, forma.raio
            self._tipo[fid] = TIPO_ESFERA
        elif isinstance(forma, Capsula):
            d[0:3], d[3:6], d[6] = forma.a, forma.b, forma.raio
            self._tipo[fid] = TIPO_CAPSULA
        else:
            raise TypeError(f"forma desconhecida: {type(forma).__name__}")
        self._sujo = True

    def adicionar(self, forma: Forma, camada: int = 1) -> int:
        """Poe uma forma solida no mundo. `camada`: bits que as consultas filtram pela
        `mascara` (ex.: 1 = cenario, 2 = vidro que deixa a visao passar). Devolve o id."""
        fid = self._novo_id()
        try:
            self._gravar(fid, forma)
        except (TypeError, ValueError):
            self._livres.append(fid)
            raise
        self._camada[fid] = camada
        self._ativo[fid] = True
        return fid

    def adicionar_caixa(self, minimo: Vec3, maximo: Vec3, camada: int = 1) -> int:
        return self.adicionar(AABB(tuple(minimo), tuple(maximo)), camada)

    def adicionar_esfera(self, centro: Vec3, raio: float, camada: int = 1) -> int:
        return self.adicionar(Esfera(tuple(centro), float(raio)), camada)

    def adicionar_capsula(self, a: Vec3, b: Vec3, raio: float, camada: int = 1) -> int:
        return self.adicionar(Capsula(tuple(a), tuple(b), float(raio)), camada)

    def atualizar(self, forma_id: int, forma: Forma) -> None:
        """Troca a forma de um id (uma porta que abre, uma ponte que cai)."""
        if not self._valido(forma_id):
            raise KeyError(forma_id)
        self._gravar(forma_id, forma)

    def remover(self, forma_id: int) -> None:
        if not self._valido(forma_id):
            raise KeyError(forma_id)
        self._ativo[forma_id] = False
        self._livres.append(forma_id)
        self._sujo = True

    def _valido(self, forma_id: int) -> bool:
        return 0 <= forma_id < self._topo and bool(self._ativo[forma_id])

    def forma(self, forma_id: int) -> Forma:
        """A forma guardada sob este id (uma dataclass nova: fora do caminho quente)."""
        if not self._valido(forma_id):
            raise KeyError(forma_id)
        d = self._dados[forma_id].tolist()
        tipo = int(self._tipo[forma_id])
        if tipo == TIPO_CAIXA:
            return AABB(tuple(d[0:3]), tuple(d[3:6]))
        if tipo == TIPO_ESFERA:
            return Esfera(tuple(d[0:3]), d[3])
        return Capsula(tuple(d[0:3]), tuple(d[3:6]), d[6])

    def __len__(self) -> int:
        return int(np.count_nonzero(self._ativo[: self._topo]))

    # ================================================================== broadphase
    def _extensao_xz(self, d: List[float], tipo: int) -> Tuple[float, float, float, float]:
        if tipo == TIPO_CAIXA:
            return d[0], d[2], d[3], d[5]
        if tipo == TIPO_ESFERA:
            r = d[3]
            return d[0] - r, d[2] - r, d[0] + r, d[2] + r
        r = d[6]
        return min(d[0], d[3]) - r, min(d[2], d[5]) - r, max(d[0], d[3]) + r, max(d[2], d[5]) + r

    def _col(self, x: float) -> int:
        c = int(math.floor((x - self._gx0) / self._cel))
        return 0 if c < 0 else (self._cols - 1 if c >= self._cols else c)

    def _row(self, z: float) -> int:
        r = int(math.floor((z - self._gz0) / self._cel))
        return 0 if r < 0 else (self._rows - 1 if r >= self._rows else r)

    def construir(self) -> None:
        """(Re)monta a grade e os espelhos de leitura. Chamado sozinho pela primeira consulta
        depois de uma mudanca no cenario; chame na carga do mapa para nao pagar no 1o quadro."""
        n = self._topo
        self._L_dados = self._dados[:n].tolist()
        self._L_tipo = self._tipo[:n].tolist()
        self._L_camada = self._camada[:n].tolist()
        ativos = self._ativo[:n].tolist()
        ncel = self._cols * self._rows
        contagem = [0] * ncel
        faixas = []
        for g in range(n):
            if not ativos[g]:
                continue
            xa, za, xb, zb = self._extensao_xz(self._L_dados[g], self._L_tipo[g])
            c0, c1, r0, r1 = self._col(xa), self._col(xb), self._row(za), self._row(zb)
            faixas.append((g, c0, c1, r0, r1))
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    contagem[r * self._cols + c] += 1
        off = [0] * (ncel + 1)
        for k in range(ncel):
            off[k + 1] = off[k] + contagem[k]
        ent = [0] * off[ncel]
        cursor = off[:-1]
        for g, c0, c1, r0, r1 in faixas:
            for r in range(r0, r1 + 1):
                for c in range(c0, c1 + 1):
                    k = r * self._cols + c
                    ent[cursor[k]] = g
                    cursor[k] += 1
        self._off, self._ent = off, ent
        self._sujo = False

    def _candidatos(self, xa: float, za: float, xb: float, zb: float, mascara: int) -> int:
        """Ids (sem repetir) das formas nas celulas que o retangulo toca, filtrados pela
        mascara, em `self._cand[:n]`. Devolve n."""
        if self._sujo:
            self.construir()
        self._carimbo += 1
        car = self._carimbo
        marca, cand, off, ent, cam = self._marca, self._cand, self._off, self._ent, self._L_camada
        c0, c1, r0, r1 = self._col(xa), self._col(xb), self._row(za), self._row(zb)
        n = 0
        for r in range(r0, r1 + 1):
            base = r * self._cols
            for c in range(c0, c1 + 1):
                k = base + c
                for e in range(off[k], off[k + 1]):
                    g = ent[e]
                    if marca[g] != car:
                        marca[g] = car
                        if cam[g] & mascara:
                            cand[n] = g
                            n += 1
        return n

    # ================================================================== narrowphase
    def _k_contato_corpo(self, ax: float, ay: float, az: float, bx: float, by: float, bz: float, r: float,
                         g: int, s: List[float]) -> float:
        """Profundidade (> 0 = invade) do corpo (segmento ab engordado por r; esfera se a == b)
        contra a forma g, com a normal que empurra o corpo em s."""
        d = self._L_dados[g]
        tipo = self._L_tipo[g]
        if tipo == TIPO_CAIXA:
            t = _k_param_segmento_aabb(ax, ay, az, bx, by, bz, d[0], d[1], d[2], d[3], d[4], d[5])
            return _k_contato_esfera_aabb(ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t, r,
                                          d[0], d[1], d[2], d[3], d[4], d[5], s)
        if tipo == TIPO_ESFERA:
            t = _k_param_segmento(d[0], d[1], d[2], ax, ay, az, bx, by, bz)
            return _k_contato_esferas(ax + (bx - ax) * t, ay + (by - ay) * t, az + (bz - az) * t, r,
                                      d[0], d[1], d[2], d[3], s)
        st = self._st
        _k_params_segmentos(ax, ay, az, bx, by, bz, d[0], d[1], d[2], d[3], d[4], d[5], st)
        u, v = st[0], st[1]
        return _k_contato_esferas(ax + (bx - ax) * u, ay + (by - ay) * u, az + (bz - az) * u, r,
                                  d[0] + (d[3] - d[0]) * v, d[1] + (d[4] - d[1]) * v, d[2] + (d[5] - d[2]) * v,
                                  d[6], s)

    def _k_raio_forma(self, g: int, ox: float, oy: float, oz: float, dx: float, dy: float, dz: float,
                      tmax: float, s: List[float]) -> float:
        d = self._L_dados[g]
        tipo = self._L_tipo[g]
        if tipo == TIPO_CAIXA:
            return _k_raio_aabb(ox, oy, oz, dx, dy, dz, tmax, d[0], d[1], d[2], d[3], d[4], d[5], s)
        if tipo == TIPO_ESFERA:
            return _k_raio_esfera(ox, oy, oz, dx, dy, dz, tmax, d[0], d[1], d[2], d[3], s)
        return _k_raio_capsula(ox, oy, oz, dx, dy, dz, tmax, d[0], d[1], d[2], d[3], d[4], d[5], d[6], s)

    # ================================================================== sobreposicao
    def _sobrepoe_corpo(self, ax: float, ay: float, az: float, bx: float, by: float, bz: float, r: float,
                        mascara: int, saida: Optional[Sequence] = None) -> int:
        n = self._candidatos(min(ax, bx) - r, min(az, bz) - r, max(ax, bx) + r, max(az, bz) + r, mascara)
        achou = 0
        cap = len(saida) if saida is not None else 0
        for k in range(n):
            g = self._cand[k]
            if self._k_contato_corpo(ax, ay, az, bx, by, bz, r, g, self._s) > 0.0:
                if saida is None:
                    return 1
                if achou < cap:
                    saida[achou] = g
                achou += 1
        return min(achou, cap) if saida is not None else achou

    def sobrepoe_esfera(self, centro: Vec3, raio: float, mascara: int = TODAS_CAMADAS) -> bool:
        """Alguma forma do mundo (nao o relevo) toca esta esfera?"""
        x, y, z = centro
        return self._sobrepoe_corpo(x, y, z, x, y, z, raio, mascara) > 0

    def sobrepoe_capsula(self, capsula: Capsula, mascara: int = TODAS_CAMADAS) -> bool:
        a, b = capsula.a, capsula.b
        return self._sobrepoe_corpo(a[0], a[1], a[2], b[0], b[1], b[2], capsula.raio, mascara) > 0

    def consultar(self, forma: Forma, saida, mascara: int = TODAS_CAMADAS) -> int:
        """Escreve em `saida` (lista ou array de inteiros, pre-alocado) os ids das formas que
        tocam `forma`; devolve quantos couberam."""
        if isinstance(forma, Esfera):
            x, y, z = forma.centro
            return self._sobrepoe_corpo(x, y, z, x, y, z, forma.raio, mascara, saida)
        if isinstance(forma, Capsula):
            a, b = forma.a, forma.b
            return self._sobrepoe_corpo(a[0], a[1], a[2], b[0], b[1], b[2], forma.raio, mascara, saida)
        mn, mx = forma.minimo, forma.maximo
        n = self._candidatos(mn[0], mn[2], mx[0], mx[2], mascara)
        cap, achou, s = len(saida), 0, self._s
        for k in range(n):
            g = self._cand[k]
            d, tipo = self._L_dados[g], self._L_tipo[g]
            if tipo == TIPO_CAIXA:
                toca = (mn[0] <= d[3] and d[0] <= mx[0] and mn[1] <= d[4] and d[1] <= mx[1]
                        and mn[2] <= d[5] and d[2] <= mx[2])
            elif tipo == TIPO_ESFERA:
                toca = _k_contato_esfera_aabb(d[0], d[1], d[2], d[3], *mn, *mx, s) > 0.0
            else:
                t = _k_param_segmento_aabb(d[0], d[1], d[2], d[3], d[4], d[5], *mn, *mx)
                toca = _k_contato_esfera_aabb(d[0] + (d[3] - d[0]) * t, d[1] + (d[4] - d[1]) * t,
                                              d[2] + (d[5] - d[2]) * t, d[6], *mn, *mx, s) > 0.0
            if toca and achou < cap:
                saida[achou] = g
                achou += 1
        return achou

    # ================================================================== raio
    def raycast(self, origem: Vec3, direcao: Vec3, dist_max: float = INF, mascara: int = TODAS_CAMADAS,
                resultado: Optional[ResultadoRaio] = None, relevo: bool = True) -> ResultadoRaio:
        """O primeiro toque do raio (formas e, se `relevo`, o chao) ate `dist_max`. Percorre a
        grade celula a celula (DDA) e para assim que o melhor acerto fica antes da proxima
        celula. `direcao` nao precisa ser unitaria. Devolve `resultado` (ou um interno, que o
        proximo raycast sobrescreve)."""
        res = resultado if resultado is not None else self._res_raio
        res.acertou, res.distancia, res.forma = False, INF, NENHUMA
        ox, oy, oz = origem
        dx, dy, dz = direcao
        n = math.sqrt(dx * dx + dy * dy + dz * dz)
        if n < 1e-12:
            return res
        dx, dy, dz = dx / n, dy / n, dz / n
        s = self._s
        melhor, qual = dist_max, NENHUMA
        nx = ny = nz = 0.0
        if relevo and self.relevo is not None:
            t = self.relevo._k_raycast(ox, oy, oz, dx, dy, dz, melhor, s)
            if t <= melhor and t != INF:
                melhor, qual, nx, ny, nz = t, RELEVO, s[0], s[1], s[2]
        if self._sujo:
            self.construir()
        if self._topo:
            t, g, a, b, c = self._dda(ox, oy, oz, dx, dy, dz, melhor, mascara)
            if g != NENHUMA:
                melhor, qual, nx, ny, nz = t, g, a, b, c
        if qual != NENHUMA:
            res.acertou, res.distancia, res.forma = True, melhor, qual
            res.ponto[0], res.ponto[1], res.ponto[2] = ox + dx * melhor, oy + dy * melhor, oz + dz * melhor
            res.normal[0], res.normal[1], res.normal[2] = nx, ny, nz
        return res

    def _dda(self, ox: float, oy: float, oz: float, dx: float, dy: float, dz: float, tmax: float,
             mascara: int) -> Tuple[float, int, float, float, float]:
        cel, gx0, gz0 = self._cel, self._gx0, self._gz0
        gx1, gz1 = gx0 + self._cols * cel, gz0 + self._rows * cel
        t0, t1 = 0.0, tmax
        for o, d, lo, hi in ((ox, dx, gx0, gx1), (oz, dz, gz0, gz1)):
            if abs(d) < 1e-12:
                if o < lo or o > hi:
                    return INF, NENHUMA, 0.0, 0.0, 0.0
                continue
            ta, tb = (lo - o) / d, (hi - o) / d
            if ta > tb:
                ta, tb = tb, ta
            t0, t1 = max(t0, ta), min(t1, tb)
            if t0 > t1:
                return INF, NENHUMA, 0.0, 0.0, 0.0
        i, j = self._col(ox + dx * t0), self._row(oz + dz * t0)
        si = 1 if dx > 0 else -1
        sj = 1 if dz > 0 else -1
        tx = (gx0 + (i + (si > 0)) * cel - ox) / dx if abs(dx) > 1e-12 else INF
        tz = (gz0 + (j + (sj > 0)) * cel - oz) / dz if abs(dz) > 1e-12 else INF
        ddx = cel / abs(dx) if abs(dx) > 1e-12 else INF
        ddz = cel / abs(dz) if abs(dz) > 1e-12 else INF
        self._carimbo += 1
        car = self._carimbo
        marca, off, ent, cam, s = self._marca, self._off, self._ent, self._L_camada, self._s
        melhor, qual = tmax, NENHUMA
        nx = ny = nz = 0.0
        while True:
            k = j * self._cols + i
            for e in range(off[k], off[k + 1]):
                g = ent[e]
                if marca[g] == car:
                    continue
                marca[g] = car
                if not cam[g] & mascara:
                    continue
                t = self._k_raio_forma(g, ox, oy, oz, dx, dy, dz, melhor, s)
                if t <= melhor and t != INF:
                    melhor, qual, nx, ny, nz = t, g, s[0], s[1], s[2]
            saida = tx if tx < tz else tz
            if saida == INF or (qual != NENHUMA and melhor <= saida) or saida > t1:
                break
            if tx < tz:
                i += si
                tx += ddx
            else:
                j += sj
                tz += ddz
            if i < 0 or j < 0 or i >= self._cols or j >= self._rows:
                break
        return melhor, qual, nx, ny, nz

    def tem_visao(self, de: Vec3, para: Vec3, mascara: int = TODAS_CAMADAS, relevo: bool = True) -> bool:
        """Nada solido entre os dois pontos (linha de visao)?"""
        dx, dy, dz = para[0] - de[0], para[1] - de[1], para[2] - de[2]
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        if dist < 1e-9:
            return True
        r = self.raycast(de, (dx, dy, dz), dist - 1e-6, mascara, self._res_raio, relevo)
        return not r.acertou

    # ================================================================== movimento
    def mover_capsula(self, pe: Vec3, altura: float, raio: float, deslocamento: Vec3,
                      mascara: int = TODAS_CAMADAS, resultado: Optional[ResultadoMovimento] = None,
                      sonda_chao: float = 0.05) -> ResultadoMovimento:
        """Anda um personagem (capsula em pe, sola em `pe`, `altura` total) por
        `deslocamento`, deslizando nas paredes e assentando no chao. `sonda_chao`: ate essa
        distancia abaixo da sola ainda conta como `no_chao` (sem puxar o corpo para baixo)."""
        meio = altura - 2.0 * raio
        if meio < 0.0:
            meio = 0.0
        return self._mover(pe[0], pe[1], pe[2], raio, raio + meio, raio, deslocamento, mascara,
                           resultado if resultado is not None else self._res_mov, sonda_chao)

    def mover_esfera(self, centro: Vec3, raio: float, deslocamento: Vec3, mascara: int = TODAS_CAMADAS,
                     resultado: Optional[ResultadoMovimento] = None,
                     sonda_chao: float = 0.05) -> ResultadoMovimento:
        """Como `mover_capsula`, para uma esfera (uma bola, uma camera que nao entra na parede)."""
        return self._mover(centro[0], centro[1], centro[2], 0.0, 0.0, raio, deslocamento, mascara,
                           resultado if resultado is not None else self._res_mov, sonda_chao)

    def _mover(self, x: float, y: float, z: float, oa: float, ob: float, r: float, desl: Vec3, mascara: int,
               res: ResultadoMovimento, sonda: float) -> ResultadoMovimento:
        """O corpo e o segmento (x, y + oa, z)-(x, y + ob, z) engordado por r; a sola fica em
        y + oa - r. Ver a docstring do modulo para o metodo."""
        res._limpar()
        dx, dy, dz = desl
        dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        passos = 1 if r <= 0.0 else min(_MAX_PASSOS, max(1, math.ceil(dist / (0.5 * r))))
        sx, sy, sz = dx / passos, dy / passos, dz / passos
        cos_rampa, s, cand = self._cos_rampa, self._s, self._cand
        rel = self.relevo
        sola_rel = oa - r
        for _ in range(passos):
            x, y, z = x + sx, y + sy, z + sz
            for _it in range(_ITERACOES):
                mexeu = False
                n = self._candidatos(x - r, z - r, x + r, z + r, mascara)
                for k in range(n):
                    prof = self._k_contato_corpo(x, y + oa, z, x, y + ob, z, r, cand[k], s)
                    if prof <= 0.0:
                        continue
                    nx, ny, nz = s[0], s[1], s[2]
                    if ny >= cos_rampa:
                        res.no_chao = True
                        res.normal_chao[0], res.normal_chao[1], res.normal_chao[2] = nx, ny, nz
                    else:
                        res.bateu = True
                        if ny > 0.0:  # rampa ingreme: so na horizontal (nao se sobe parede andando)
                            h = math.sqrt(nx * nx + nz * nz)
                            if h > 1e-9:
                                nx, ny, nz, prof = nx / h, 0.0, nz / h, prof / h
                    prof += _FOLGA
                    x, y, z = x + nx * prof, y + ny * prof, z + nz * prof
                    res._anotar(nx, ny, nz)
                    mexeu = True
                if rel is not None:
                    chao = rel.altura(x, z)
                    if y + sola_rel < chao:
                        y = chao - sola_rel
                        rel._k_normal(x, z, s)
                        res.no_chao = True
                        res.normal_chao[0], res.normal_chao[1], res.normal_chao[2] = s[0], s[1], s[2]
                        res._anotar(s[0], s[1], s[2])
                if not mexeu:
                    break
        if not res.no_chao and sonda > 0.0:
            self._sondar_chao(x, y, z, oa, ob, r, sonda, mascara, res)
        res.posicao[0], res.posicao[1], res.posicao[2] = x, y, z
        return res

    def _sondar_chao(self, x: float, y: float, z: float, oa: float, ob: float, r: float, sonda: float,
                     mascara: int, res: ResultadoMovimento) -> None:
        s = self._s
        yb = y - sonda
        n = self._candidatos(x - r, z - r, x + r, z + r, mascara)
        for k in range(n):
            if self._k_contato_corpo(x, yb + oa, z, x, yb + ob, z, r, self._cand[k], s) > 0.0 \
                    and s[1] >= self._cos_rampa:
                res.no_chao = True
                res.normal_chao[0], res.normal_chao[1], res.normal_chao[2] = s[0], s[1], s[2]
                return
        rel = self.relevo
        if rel is not None and y + oa - r - rel.altura(x, z) <= sonda:
            rel._k_normal(x, z, s)
            res.no_chao = True
            res.normal_chao[0], res.normal_chao[1], res.normal_chao[2] = s[0], s[1], s[2]
