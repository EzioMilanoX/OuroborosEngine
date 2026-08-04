# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Serializa e grava beatmap.json de forma atomica (tmp + fsync + os.replace)."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict

from ouroboros.rhythm.offline.beatmap_schema import BeatmapValidator


class BeatmapWriteError(Exception):
    """Levantado quando a escrita atomica falha por motivo de I/O (sem
    permissao, disco cheio, diretorio de destino inexistente).
    """


class BeatmapWriter:
    """Serializa e grava `beatmap.json` de forma atomica.

    Invariante de atomicidade: o conteudo e primeiro serializado e
    escrito por completo em um arquivo TEMPORARIO criado no MESMO
    diretorio do destino final (garantindo que o rename seja no mesmo
    filesystem), com `flush` + `os.fsync` explicitos antes do rename;
    so entao `os.replace` (atomico tanto em POSIX quanto em Windows)
    move o temporario para o caminho final. Se o processo for
    interrompido a qualquer momento ANTES do rename, o arquivo de destino
    final permanece no estado anterior (ou inexistente) -- NUNCA fica
    parcialmente escrito.
    """

    def __init__(self, validator: BeatmapValidator) -> None:
        """Guarda o `BeatmapValidator` usado para recusar escrever um
        beatmap invalido em disco.
        """
        self._validator = validator

    def write(self, beatmap_dict: Dict[str, Any], destination_path: Path) -> None:
        """Valida `beatmap_dict` (via `validator.validate`) e entao
        grava atomicamente em `destination_path`.

        Levanta `BeatmapValidationError` se o conteudo for invalido
        (nada e escrito em disco nesse caso). Levanta `BeatmapWriteError`
        se a escrita/rename falhar por motivo de I/O (o arquivo temporario
        orfao, se houver, deve ser removido antes de propagar o erro).
        """
        # Validacao ocorre ANTES de qualquer I/O -- se falhar (levanta
        # BeatmapValidationError), nenhum arquivo (nem temporario) chega
        # a ser criado.
        self._validator.validate(beatmap_dict)

        destination_path = Path(destination_path)
        temp_path = self._write_temp_file(beatmap_dict, destination_path)
        try:
            os.replace(temp_path, destination_path)
        except OSError as exc:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except OSError:
                pass  # limpeza best-effort: nao mascara o erro original
            raise BeatmapWriteError(
                f"failed to atomically finalize beatmap write to {destination_path}: {exc}"
            ) from exc

    def _write_temp_file(self, beatmap_dict: Dict[str, Any], destination_path: Path) -> Path:
        """Serializa `beatmap_dict` como JSON em um arquivo temporario
        criado no mesmo diretorio de `destination_path`, faz
        flush + fsync, e retorna o `Path` do temporario. NAO faz rename.
        """
        destination_dir = destination_path.parent

        try:
            fd, tmp_name = tempfile.mkstemp(
                prefix=f".{destination_path.name}.",
                suffix=".tmp",
                dir=str(destination_dir) if str(destination_dir) else ".",
            )
        except OSError as exc:
            raise BeatmapWriteError(f"failed to create temporary file in {destination_dir}: {exc}") from exc

        temp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as temp_file:
                json.dump(beatmap_dict, temp_file, indent=2, ensure_ascii=False)
                temp_file.flush()
                os.fsync(temp_file.fileno())
        except OSError as exc:
            try:
                temp_path.unlink()
            except OSError:
                pass  # arquivo temporario orfao: melhor esforco, nao mascara o erro original
            raise BeatmapWriteError(f"failed to write temporary beatmap file {temp_path}: {exc}") from exc

        return temp_path
