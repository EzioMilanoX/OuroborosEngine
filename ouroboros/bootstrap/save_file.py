# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Um arquivo de save, e as tres regras que ele nunca pode quebrar.

Todo produto da engine que guarde qualquer coisa entre sessoes -- fases
vencidas, cartas desbloqueadas, recordes, opcoes -- escreve o mesmo par de
funcoes. E todos erram nos mesmos lugares, porque os erros so aparecem em
maquina de outra pessoa: disco cheio, pasta somente-leitura, desligamento no
meio da escrita, save gravado por uma versao anterior do jogo.

As tres regras saem todas da mesma frase -- **um arquivo de save nunca pode
ser o motivo de o jogo nao abrir**:

* **Ler nunca levanta.** Arquivo ausente, JSON corrompido, raiz que nao e um
  objeto: tudo vira `{}`, e o produto comeca do zero em vez de morrer no boot.
* **Escrever e atomico.** Grava num `.tmp` ao lado e renomeia por cima. Um
  desligamento no meio deixa o save ANTERIOR intacto, nunca meio arquivo --
  e meio arquivo e pior que nenhum, porque parece valido ate nao ser.
* **Escrever falhado e silencioso.** Devolve `False` e segue. Uma pasta sem
  permissao custa o progresso daquela sessao; nao pode custar a sessao.

O que NAO esta aqui e o formato: quais campos existem, que tipos tem, o que
fazer com um save de outra versao. Isso e do produto, e cada um responde
diferente -- este modulo entrega e recebe um `dict` e nao opina sobre ele.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional


def default_save_path(app_name: str, file_name: str = "save.json") -> Path:
    """O lugar do save, por plataforma.

    Nao fica ao lado do codigo de proposito: um repositorio e clonavel e
    somente-leitura em muitas maquinas, e um save dentro dele apareceria no
    `git status` a cada partida.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / app_name / file_name
    xdg = os.environ.get("XDG_DATA_HOME")
    base = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return base / app_name / file_name


class SaveFile:
    """Le e escreve um `dict` em disco, sem nunca derrubar o jogo."""

    def __init__(self, path) -> None:
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def read(self) -> dict:
        """O conteudo do save, ou `{}`. Nunca levanta.

        Uma raiz que nao seja objeto conta como ausente: um arquivo que
        contenha `[]` ou `"oi"` nao e um save meio valido, e tratar como se
        fosse so adia o erro para o primeiro campo lido.
        """
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def write(self, payload: dict) -> bool:
        """Grava de forma atomica. Devolve se conseguiu."""
        temporary = self._path.with_suffix(".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, self._path)
            return True
        except (OSError, TypeError, ValueError):
            # `TypeError`/`ValueError` cobrem um payload nao serializavel: e
            # erro de programacao, mas descobri-lo derrubando o jogo de quem
            # esta jogando e a pior hora possivel.
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return False
