# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deriva um id inteiro estavel a partir de um nome textual, via CRC32."""
from __future__ import annotations

import zlib


def stable_id_from_name(name: str) -> int:
    """Deriva um id inteiro (int32 positivo) estavel a partir de `name`,
    via CRC32 -- puro e deterministico entre execucoes (ao contrario de
    `hash()` nativo, que e aleatorizado por processo). Usado para caber
    um nome textual (ex.: id de arma, nome de textura) num campo de
    dtype NumPy estruturado, que precisa de um inteiro de largura fixa.

    Nao protege contra colisao entre dois nomes diferentes (raro, mas
    possivel com CRC32) -- cada chamador que usa isto como chave e
    responsavel por validar unicidade antes de registrar qualquer
    coisa (ver `WeaponLoader.load_all_definitions`/
    `ouroboros.bootstrap.texture_manifest_loader.load_texture_manifest`).
    """
    return zlib.crc32(name.encode("utf-8")) & 0x7FFFFFFF
