# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Onde estao os dados -- rodando do repositorio ou de dentro de um executavel.

Os caminhos de um `EngineConfig` (`data/difficulties/...`,
`data/input_bindings/...`) sao relativos, e Python os resolve contra o
DIRETORIO ATUAL. Enquanto o unico jeito de rodar for `python -m produto.main`
a partir da raiz, isso nunca incomoda. No dia em que o produto vira um
executavel, o diretorio atual passa a ser onde quer que a pessoa tenha
clicado -- e o mesmo detalhe vira a UNICA coisa que acontece: o jogo morre no
boot com um erro sobre um arquivo que esta ali do lado.

Todo produto da engine vai encontrar isso ao empacotar o primeiro `.exe`, e
todos resolveriam do mesmo jeito. Entao mora aqui.

A regra e uma so: **nunca depender do diretorio atual**. Tres casos:

* **Repositorio** -- a raiz que o proprio produto declara.
* **PyInstaller onefile** -- `sys._MEIPASS`, a pasta temporaria onde o bundle
  se descompacta.
* **PyInstaller onedir** -- a pasta do proprio executavel.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def is_frozen() -> bool:
    """Rodando de dentro de um executavel empacotado."""
    return bool(getattr(sys, "frozen", False))


def frozen_root() -> Optional[Path]:
    """A raiz dos dados dentro de um bundle, ou `None` fora de um.

    `_MEIPASS` so existe no modo onefile; no onedir os dados ficam ao lado do
    executavel.
    """
    if not is_frozen():
        return None
    bundle = getattr(sys, "_MEIPASS", None)
    return Path(bundle) if bundle else Path(sys.executable).resolve().parent


class ResourceRoot:
    """
    A pasta que contem `data/` (e o que mais o produto empacotar).

    O produto declara a raiz de DESENVOLVIMENTO -- tipicamente
    `Path(__file__).resolve().parent.parent`, a pasta que contem o pacote --
    e esta classe decide, a cada consulta, se e ela que vale ou se o processo
    esta congelado num bundle.

    Nunca o diretorio atual: um jogo que so abre se voce estiver na pasta
    certa nao e um jogo que da pra mandar pra alguem.
    """

    def __init__(self, development_root) -> None:
        self._development_root = Path(development_root)

    @property
    def root(self) -> Path:
        frozen = frozen_root()
        return frozen if frozen is not None else self._development_root

    def __call__(self, *parts: str) -> Path:
        """Um caminho absoluto dentro dos dados empacotados."""
        return self.root.joinpath(*parts)

    def resolve(self, path_like) -> str:
        """Torna absoluto um caminho vindo de um arquivo de configuracao.

        Absolutos passam intactos -- quem apontou para fora do bundle sabia o
        que estava fazendo (uma dificuldade de teste, por exemplo).
        """
        path = Path(path_like)
        return str(path if path.is_absolute() else self.root / path)
