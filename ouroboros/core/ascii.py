# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Modo ASCII (ROADMAP M22): uma tela de caracteres em arrays NumPy pre-alocados, primitivas de
desenho, sprites em arte ASCII (varias linhas, caractere transparente, quadros de animacao,
espelho) e a conversao de cores por celula em caracteres por luminancia (o filtro ASCII).

Logica pura, sem pygame (Regra 2): o adapter desenha a `TelaAscii` com uma fonte monoespacada
(`IRenderer.draw_ascii`) e aplica o filtro num quadro ja renderizado
(`IRenderer.set_ascii_filter`). As primitivas nao alocam objetos Python por chamada (Zero-GC):
escrevem direto nos arrays.

Coordenadas em celulas: x = coluna (0 a esquerda), y = linha (0 no topo).
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass
from typing import Dict, Mapping, Optional, Sequence, Tuple, Union

import numpy as np

Cor = Tuple[int, int, int]

RAMPA_PADRAO = " .:-=+*#%@"
"""Do escuro para o claro: quanto mais tinta o caractere tem, mais luz a celula tinha."""

PARES_ESPELHO: Tuple[Tuple[str, str], ...] = (
    ("/", "\\"), ("(", ")"), ("<", ">"), ("[", "]"), ("{", "}"), ("d", "b"), ("p", "q"),
)
"""O que troca de lugar ao espelhar na horizontal (alem de inverter a ordem das colunas)."""

ESPACO = 32
BRANCO: Cor = (220, 220, 220)


def _tabela_espelho(pares: Sequence[Tuple[str, str]]) -> Dict[int, int]:
    tabela: Dict[int, int] = {}
    for a, b in pares:
        tabela[ord(a)] = ord(b)
        tabela[ord(b)] = ord(a)
    return tabela


def espelhar_linha(linha: str, pares: Sequence[Tuple[str, str]] = PARES_ESPELHO) -> str:
    """A linha de arte vista no espelho: ordem invertida e `/`<->`\\`, `(`<->`)`..."""
    tabela = _tabela_espelho(pares)
    return "".join(chr(tabela.get(ord(c), ord(c))) for c in reversed(linha))


@dataclass(frozen=True)
class FiltroAscii:
    """
    Configuracao do filtro ASCII (`IRenderer.set_ascii_filter`): o quadro ja renderizado e
    dividido em celulas do tamanho de um caractere da fonte `tamanho_fonte`; cada celula vira
    o caractere da `rampa` pela luminancia da cor media, pintado com essa cor.

    - `realce` (0..1): puxa a cor do caractere para o brilho maximo mantendo o matiz (um
      caractere cobre pouco da celula; sem realce a imagem fica apagada).
    - `fundo` (0..1): a celula ganha um fundo com a cor media vezes `fundo` (0 = preto).
    - `niveis_cor`: niveis por canal da cor do caractere (o adapter guarda um glifo por
      caractere+cor; poucos niveis = cache pequeno).
    - `area`: (x, y, largura, altura) em pixels a converter; None = a tela toda (deixe o HUD
      de fora para continuar legivel).
    """

    tamanho_fonte: int = 12
    rampa: str = RAMPA_PADRAO
    realce: float = 0.6
    fundo: float = 0.18
    niveis_cor: int = 8
    area: Optional[Tuple[int, int, int, int]] = None

    def __post_init__(self) -> None:
        if len(self.rampa) < 2:
            raise ValueError("a rampa precisa de pelo menos 2 caracteres")
        if not (2 <= self.niveis_cor <= 256):
            raise ValueError("niveis_cor entre 2 e 256")
        if self.tamanho_fonte <= 0:
            raise ValueError("tamanho_fonte precisa ser positivo")


class SpriteAscii:
    """
    Uma figura em arte ASCII de varias linhas. O caractere `transparente` (default espaco)
    nao apaga o que esta atras. Cores, em ordem de prioridade: `mapa_cores` (um texto do mesmo
    formato da arte, cada letra uma chave de `paleta`), `cor_por_caractere` (ex.: `{"#": vermelho}`)
    e `cor`. `ancora` (coluna, linha) e o ponto que cai na posicao pedida: o default e o meio
    da ultima linha (os pes). Arte em texto perde a indentacao comum e as linhas vazias das
    pontas (`textwrap.dedent`); um `mapa_cores` em texto passa pelo mesmo tratamento, entao
    precisa ter a mesma indentacao -- ou passe listas de linhas, que entram como estao.

    A versao espelhada (`/` vira `\\`, `(` vira `)`...) e montada aqui, uma vez: desenhar
    virado para o outro lado custa o mesmo que desenhar normal.
    """

    def __init__(self, arte: Union[str, Sequence[str]], *, cor: Cor = BRANCO,
                 cor_por_caractere: Optional[Mapping[str, Cor]] = None,
                 mapa_cores: Optional[Union[str, Sequence[str]]] = None,
                 paleta: Optional[Mapping[str, Cor]] = None,
                 transparente: str = " ", ancora: Optional[Tuple[int, int]] = None,
                 pares: Sequence[Tuple[str, str]] = PARES_ESPELHO) -> None:
        linhas = _linhas(arte)
        if not linhas:
            raise ValueError("arte vazia")
        if len(transparente) != 1:
            raise ValueError("transparente e um caractere so")
        h, w = len(linhas), max(len(linha) for linha in linhas)
        self.altura, self.largura = h, w
        self.caracteres = np.full((h, w), ord(transparente), np.uint32)
        for y, linha in enumerate(linhas):
            for x, c in enumerate(linha):
                self.caracteres[y, x] = ord(c)
        self.opaco = self.caracteres != ord(transparente)
        self.cores = np.empty((h, w, 3), np.uint8)
        self.cores[:, :] = cor
        if cor_por_caractere:
            for c, rgb in cor_por_caractere.items():
                self.cores[self.caracteres == ord(c)] = rgb
        if mapa_cores is not None:
            if not paleta:
                raise ValueError("mapa_cores precisa de paleta")
            for y, linha in enumerate(_linhas(mapa_cores)):
                for x, chave in enumerate(linha[:w]):
                    if y < h and chave in paleta:
                        self.cores[y, x] = paleta[chave]
        self.ancora = ancora if ancora is not None else (w // 2, h - 1)
        # o espelho, pronto
        tabela = _tabela_espelho(pares)
        esp = self.caracteres[:, ::-1].copy()
        troca = esp.copy()
        for a, b in tabela.items():
            troca[esp == a] = b
        self.caracteres_esp = troca
        self.opaco_esp = self.opaco[:, ::-1].copy()
        self.cores_esp = self.cores[:, ::-1].copy()
        self.ancora_esp = (w - 1 - self.ancora[0], self.ancora[1])

    def linhas(self, espelhado: bool = False) -> list:
        """A arte como texto (para inspecao/teste; aloca)."""
        car = self.caracteres_esp if espelhado else self.caracteres
        return ["".join(chr(int(c)) for c in linha) for linha in car]


class AnimacaoAscii:
    """Uma sequencia de `SpriteAscii` a `fps` quadros por segundo, em laco ou nao."""

    def __init__(self, quadros: Sequence[SpriteAscii], fps: float = 8.0, laco: bool = True) -> None:
        if not quadros:
            raise ValueError("animacao sem quadros")
        if fps <= 0:
            raise ValueError("fps precisa ser positivo")
        self.quadros = tuple(quadros)
        self.fps = float(fps)
        self.laco = laco

    @property
    def duracao(self) -> float:
        return len(self.quadros) / self.fps

    def indice(self, t: float) -> int:
        i = int(max(t, 0.0) * self.fps)
        n = len(self.quadros)
        return i % n if self.laco else min(i, n - 1)

    def quadro(self, t: float) -> SpriteAscii:
        """O quadro no tempo `t` (segundos desde o inicio)."""
        return self.quadros[self.indice(t)]

    def acabou(self, t: float) -> bool:
        return not self.laco and t >= self.duracao


def _linhas(arte: Union[str, Sequence[str]], dedent: bool = True) -> list:
    if isinstance(arte, str):
        texto = textwrap.dedent(arte) if dedent else arte
        linhas = texto.split("\n")
        while linhas and not linhas[0].strip():
            linhas.pop(0)
        while linhas and not linhas[-1].strip():
            linhas.pop()
        return [linha.rstrip("\r") for linha in linhas]
    return list(arte)


class TelaAscii:
    """
    Uma grade `colunas` x `linhas` de caracteres (`caracteres`, uint32 com o codigo), cor de
    frente (`cores`, uint8 RGB) e, se `fundo` nao for None, cor de fundo (`fundos`). Tudo
    alocado aqui; as primitivas so escrevem (Zero-GC). O que sai da grade e cortado.
    """

    def __init__(self, colunas: int, linhas: int, *, cor: Cor = BRANCO,
                 fundo: Optional[Cor] = (0, 0, 0)) -> None:
        if colunas <= 0 or linhas <= 0:
            raise ValueError("a tela precisa de pelo menos 1x1 celula")
        self.colunas, self.linhas = int(colunas), int(linhas)
        self.cor_padrao = tuple(cor)
        self.fundo_padrao = tuple(fundo) if fundo is not None else None
        self.caracteres = np.full((self.linhas, self.colunas), ESPACO, np.uint32)
        self.cores = np.empty((self.linhas, self.colunas, 3), np.uint8)
        self.cores[:, :] = self.cor_padrao
        self.fundos = None
        if fundo is not None:
            self.fundos = np.empty((self.linhas, self.colunas, 3), np.uint8)
            self.fundos[:, :] = fundo
        self._cor = np.zeros(3, np.uint8)  # rascunho para nao criar array por chamada
        self._lum = np.zeros((self.linhas, self.colunas), np.float32)
        self._tmp = np.zeros((self.linhas, self.colunas), np.float32)
        self._idx = np.zeros((self.linhas, self.colunas), np.intp)
        self._f = np.zeros((self.linhas, self.colunas, 3), np.float32)
        self._ff = np.zeros((self.linhas, self.colunas, 3), np.float32)
        self._rampa_txt = ""
        self._rampa = np.zeros(0, np.uint32)

    # ------------------------------------------------------------ basico

    def limpar(self, caractere: str = " ", cor: Optional[Cor] = None, fundo: Optional[Cor] = None) -> None:
        self.caracteres.fill(ord(caractere))
        self.cores[:, :] = cor if cor is not None else self.cor_padrao
        if self.fundos is not None:
            self.fundos[:, :] = fundo if fundo is not None else self.fundo_padrao

    def dentro(self, x: int, y: int) -> bool:
        return 0 <= x < self.colunas and 0 <= y < self.linhas

    def por(self, x: int, y: int, caractere: str, cor: Optional[Cor] = None,
            fundo: Optional[Cor] = None) -> None:
        """Um caractere na celula (x, y); fora da grade nao faz nada."""
        x, y = int(x), int(y)
        if not (0 <= x < self.colunas and 0 <= y < self.linhas):
            return
        self.caracteres[y, x] = ord(caractere)
        if cor is not None:
            self.cores[y, x] = cor
        if fundo is not None and self.fundos is not None:
            self.fundos[y, x] = fundo

    def texto(self, x: int, y: int, texto: str, cor: Optional[Cor] = None,
              fundo: Optional[Cor] = None) -> None:
        """Escreve `texto` na linha y a partir da coluna x (uma linha so; corta nas bordas)."""
        x, y = int(x), int(y)
        if not (0 <= y < self.linhas):
            return
        car = self.caracteres
        for c in texto:
            if 0 <= x < self.colunas:
                car[y, x] = ord(c)
                if cor is not None:
                    self.cores[y, x] = cor
                if fundo is not None and self.fundos is not None:
                    self.fundos[y, x] = fundo
            x += 1

    def ler(self, x: int, y: int) -> str:
        return chr(int(self.caracteres[y, x]))

    def linha_texto(self, y: int) -> str:
        """A linha y como texto (para teste/depuracao; aloca)."""
        return "".join(chr(int(c)) for c in self.caracteres[y])

    def texto_completo(self) -> str:
        return "\n".join(self.linha_texto(y) for y in range(self.linhas))

    # ------------------------------------------------------------ formas

    def linha(self, x0: int, y0: int, x1: int, y1: int, caractere: Optional[str] = None,
              cor: Optional[Cor] = None) -> None:
        """Segmento de (x0, y0) a (x1, y1) (Bresenham). Sem `caractere`, escolhe pela
        inclinacao: `-`, `|`, `/` ou `\\`."""
        x0, y0, x1, y1 = int(x0), int(y0), int(x1), int(y1)
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        if caractere is not None:
            codigo = ord(caractere)
        elif dx == 0:
            codigo = ord("|")
        elif -dy * 2 < dx:  # mais deitada que 1:2 (a celula e mais alta que larga)
            codigo = ord("-")
        elif -dy > dx * 2:
            codigo = ord("|")
        else:
            codigo = ord("\\") if (x1 - x0) * (y1 - y0) > 0 else ord("/")
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            if 0 <= x0 < self.colunas and 0 <= y0 < self.linhas:
                self.caracteres[y0, x0] = codigo
                if cor is not None:
                    self.cores[y0, x0] = cor
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def _faixa(self, y: int, xa: int, xb: int, codigo: int, cor: Optional[Cor],
               fundo: Optional[Cor]) -> None:
        """Preenche a linha y de xa a xb (inclusive), cortando nas bordas."""
        if not (0 <= y < self.linhas):
            return
        xa, xb = max(xa, 0), min(xb, self.colunas - 1)
        if xa > xb:
            return
        if codigo >= 0:
            self.caracteres[y, xa:xb + 1] = codigo
        if cor is not None:
            self.cores[y, xa:xb + 1] = cor
        if fundo is not None and self.fundos is not None:
            self.fundos[y, xa:xb + 1] = fundo

    def retangulo(self, x: int, y: int, largura: int, altura: int, caractere: Optional[str] = None,
                  cor: Optional[Cor] = None, *, preenchido: bool = False,
                  fundo: Optional[Cor] = None) -> None:
        """Retangulo com canto em (x, y). Contorno: sem `caractere` usa `+`, `-` e `|`.
        `preenchido`: tudo com `caractere` (default espaco), util com `fundo`."""
        x, y, largura, altura = int(x), int(y), int(largura), int(altura)
        if largura <= 0 or altura <= 0:
            return
        x1, y1 = x + largura - 1, y + altura - 1
        if preenchido:
            codigo = ord(caractere) if caractere is not None else ESPACO
            for yy in range(y, y1 + 1):
                self._faixa(yy, x, x1, codigo, cor, fundo)
            return
        h = ord(caractere) if caractere is not None else ord("-")
        v = ord(caractere) if caractere is not None else ord("|")
        canto = ord(caractere) if caractere is not None else ord("+")
        self._faixa(y, x, x1, h, cor, fundo)
        self._faixa(y1, x, x1, h, cor, fundo)
        for yy in range(y + 1, y1):
            self._faixa(yy, x, x, v, cor, fundo)
            self._faixa(yy, x1, x1, v, cor, fundo)
        for cx, cy in ((x, y), (x1, y), (x, y1), (x1, y1)):
            if 0 <= cx < self.colunas and 0 <= cy < self.linhas:
                self.caracteres[cy, cx] = canto

    def _meia_largura(self, dy: int, rx: float, ry: float) -> int:
        """Meia largura (em colunas) da elipse na linha dy do centro; -1 se fora."""
        if ry <= 0:
            return int(rx + 0.5) if dy == 0 else -1
        t = 1.0 - (dy / (ry + 0.5)) ** 2
        if t < 0.0:
            return -1
        return int(rx * t ** 0.5 + 0.5)

    def elipse(self, cx: int, cy: int, rx: float, ry: float, caractere: str = "o",
               cor: Optional[Cor] = None, *, preenchido: bool = True,
               fundo: Optional[Cor] = None) -> None:
        """Elipse com centro (cx, cy) e semi-eixos `rx` colunas x `ry` linhas (as celulas sao
        mais altas que largas: um circulo na tela tem rx ~ 2*ry). `preenchido=False` desenha
        so a borda (celulas dentro com algum vizinho fora)."""
        cx, cy = int(round(cx)), int(round(cy))
        codigo = ord(caractere)
        alcance = int(ry + 0.5)
        for dy in range(-alcance, alcance + 1):
            hw = self._meia_largura(dy, rx, ry)
            if hw < 0:
                continue
            y = cy + dy
            if preenchido:
                self._faixa(y, cx - hw, cx + hw, codigo, cor, fundo)
                continue
            dentro = min(self._meia_largura(dy - 1, rx, ry), self._meia_largura(dy + 1, rx, ry))
            if dentro < 0:  # vizinho de cima ou de baixo fora: a linha toda e borda
                self._faixa(y, cx - hw, cx + hw, codigo, cor, fundo)
                continue
            dentro = min(dentro, hw - 1)
            self._faixa(y, cx - hw, cx - dentro - 1, codigo, cor, fundo)
            self._faixa(y, cx + dentro + 1, cx + hw, codigo, cor, fundo)

    # ------------------------------------------------------------ sprites

    def sprite(self, spr: SpriteAscii, x: int, y: int, *, espelhado: bool = False,
               cor: Optional[Cor] = None) -> None:
        """Desenha `spr` com a ancora em (x, y). `espelhado` vira para o outro lado; `cor`
        pinta a figura toda de uma cor (um piscar de dano, uma silhueta)."""
        if espelhado:
            car, opaco, cores, ax, ay = spr.caracteres_esp, spr.opaco_esp, spr.cores_esp, *spr.ancora_esp
        else:
            car, opaco, cores, ax, ay = spr.caracteres, spr.opaco, spr.cores, *spr.ancora
        x0, y0 = int(x) - ax, int(y) - ay
        # recorte na grade
        sx0, sy0 = max(0, -x0), max(0, -y0)
        sx1 = min(spr.largura, self.colunas - x0)
        sy1 = min(spr.altura, self.linhas - y0)
        if sx0 >= sx1 or sy0 >= sy1:
            return
        dx0, dy0 = x0 + sx0, y0 + sy0
        dx1, dy1 = x0 + sx1, y0 + sy1
        mascara = opaco[sy0:sy1, sx0:sx1]
        np.copyto(self.caracteres[dy0:dy1, dx0:dx1], car[sy0:sy1, sx0:sx1], where=mascara)
        destino = self.cores[dy0:dy1, dx0:dx1]
        m3 = mascara[:, :, None]
        if cor is None:
            np.copyto(destino, cores[sy0:sy1, sx0:sx1], where=m3)
        else:
            self._cor[0], self._cor[1], self._cor[2] = cor[0], cor[1], cor[2]
            np.copyto(destino, self._cor, where=m3)

    # ------------------------------------------------------------ filtro

    def _preparar_rampa(self, rampa: str) -> None:
        if rampa != self._rampa_txt:  # muda raramente: fora do regime
            self._rampa = np.array([ord(c) for c in rampa], np.uint32)
            self._rampa_txt = rampa

    def preencher_por_luminancia(self, rgb: np.ndarray, rampa: str = RAMPA_PADRAO,
                                 realce: float = 0.0, fundo: float = 0.0,
                                 niveis_cor: int = 256) -> None:
        """
        O coracao do filtro ASCII: `rgb` (linhas, colunas, 3) uint8 e a cor media de cada
        celula; cada celula vira o caractere da `rampa` pela luminancia (Rec. 709), com a cor
        media (puxada para o brilho maximo por `realce`, 0..1, e quantizada em `niveis_cor`
        por canal) e, se a tela tem fundo, fundo = cor media * `fundo`. Sem alocar.
        """
        if rgb.shape[0] != self.linhas or rgb.shape[1] != self.colunas:
            raise ValueError("rgb precisa ter o tamanho da tela")
        self._preparar_rampa(rampa)
        n = self._rampa.shape[0]
        f, lum, tmp, idx = self._f, self._lum, self._tmp, self._idx
        np.copyto(f, rgb, casting="unsafe")
        # luminancia 0..255
        np.multiply(f[:, :, 0], 0.2126, out=lum)
        np.multiply(f[:, :, 1], 0.7152, out=tmp)
        lum += tmp
        np.multiply(f[:, :, 2], 0.0722, out=tmp)
        lum += tmp
        # caractere: lum * n / 256, arredondado para baixo
        np.multiply(lum, n / 256.0, out=tmp)
        np.floor(tmp, out=tmp)
        np.clip(tmp, 0, n - 1, out=tmp)
        np.copyto(idx, tmp, casting="unsafe")
        np.take(self._rampa, idx, out=self.caracteres)
        # fundo antes do realce: a cor media de verdade, escurecida
        if self.fundos is not None:
            if fundo > 0.0:
                np.multiply(f, fundo, out=self._ff)
                np.copyto(self.fundos, self._ff, casting="unsafe")
            else:
                self.fundos.fill(0)
        # realce: c + (c * 255 / max(c) - c) * realce = c * (1 + (255/max - 1) * realce)
        if realce > 0.0:
            np.max(f, axis=2, out=tmp)
            np.maximum(tmp, 1.0, out=tmp)
            np.divide(255.0, tmp, out=tmp)
            tmp -= 1.0
            tmp *= realce
            tmp += 1.0
            f *= tmp[:, :, None]
        if niveis_cor < 256:
            passo = 256.0 / niveis_cor
            f /= passo
            np.floor(f, out=f)
            f *= passo
            f += passo * 0.5  # o meio do degrau, nao o fundo dele
        np.clip(f, 0.0, 255.0, out=f)
        np.copyto(self.cores, f, casting="unsafe")
