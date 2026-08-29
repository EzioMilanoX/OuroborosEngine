# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le data/songs/*.json e expoe o catalogo de musicas jogaveis como dados puros."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Set, Tuple

_REQUIRED_FIELDS = ("track_id", "display_name", "beatmap_path", "audio_path")


class SongCatalogError(Exception):
    """Levantado quando `data/songs/*.json` esta vazio, malformado, ou tem
    um `track_id` duplicado entre dois arquivos.
    """


@dataclass(frozen=True)
class SongEntry:
    """Uma musica jogavel do catalogo (ROADMAP M11.1/M11.2).

    `beatmap_path`/`audio_path` ja vem RESOLVIDOS (absolutos, contra o
    `repo_root` passado a `SongCatalogLoader`) -- o chamador nunca precisa
    saber que esses campos comecaram como strings relativas no JSON.
    """

    track_id: str
    display_name: str
    beatmap_path: Path
    audio_path: Path


class SongCatalogLoader:
    """Le `data/songs/*.json` e expoe o catalogo de musicas jogaveis como
    dados puros (nunca uma faixa hardcoded em Python -- ver ROADMAP M11.1,
    que introduz a primeira selecao de musica real do Jogo Musical).

    Roda fora do loop de gameplay (montagem do menu).
    """

    def __init__(self, songs_directory: Path, repo_root: Path) -> None:
        """`songs_directory`: onde os arquivos `*.json` do catalogo vivem.
        `repo_root`: base contra a qual `beatmap_path`/`audio_path` (strings
        relativas no JSON, mesma convencao de `EngineConfig`) sao resolvidos.
        """
        self._songs_directory = Path(songs_directory)
        self._repo_root = Path(repo_root)

    def load_all(self) -> Tuple[SongEntry, ...]:
        """Le e valida todos os `*.json` do diretorio (ordem alfabetica de
        arquivo), retorna o catalogo completo.

        Levanta `SongCatalogError` se um arquivo estiver malformado, faltando
        campo obrigatorio, se dois arquivos declararem o mesmo `track_id`, ou
        se o diretorio nao tiver nenhuma musica.
        """
        entries = []
        seen_track_ids: Set[str] = set()
        for path in sorted(self._songs_directory.glob("*.json")):
            with path.open("r", encoding="utf-8") as handle:
                try:
                    data = json.load(handle)
                except json.JSONDecodeError as exc:
                    raise SongCatalogError(f"JSON invalido em {path}: {exc}") from exc

            for field in _REQUIRED_FIELDS:
                if field not in data:
                    raise SongCatalogError(f"arquivo {path} sem campo obrigatorio '{field}'")

            track_id = str(data["track_id"])
            if track_id in seen_track_ids:
                raise SongCatalogError(f"track_id duplicado '{track_id}' em {path}")
            seen_track_ids.add(track_id)

            entries.append(
                SongEntry(
                    track_id=track_id,
                    display_name=str(data["display_name"]),
                    beatmap_path=self._repo_root / str(data["beatmap_path"]),
                    audio_path=self._repo_root / str(data["audio_path"]),
                )
            )

        if not entries:
            raise SongCatalogError(f"nenhuma musica encontrada em {self._songs_directory}")
        return tuple(entries)
