# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Le um manifesto de texturas (JSON) e registra cada entrada num IRenderer."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, FrozenSet

from ouroboros.core.stable_id import stable_id_from_name
from ouroboros.interfaces.renderer import SHAPE_MAX, IRenderer


def load_texture_manifest(renderer: IRenderer, manifest_path: str, textures_root: Path) -> FrozenSet[str]:
    """Le o manifesto de texturas `manifest_path` (dict JSON `nome ->
    caminho relativo`) e registra cada entrada em `renderer`, fora do
    loop de gameplay (chamado pelo script de composicao de um produto,
    nunca de dentro de `ISystem.update()`).

    Cada `nome` vira um `texture_id` inteiro via
    `ouroboros.core.stable_id.stable_id_from_name` -- valida que dois
    nomes DIFERENTES nunca colidem no mesmo id (incluindo uma chave
    duplicada literal no proprio JSON, que o `json.load` colapsaria
    silenciosamente) ANTES de registrar qualquer textura, levantando
    `ValueError` se achar uma colisao. Sem essa guarda, duas texturas
    colidindo fariam uma sobrescrever a outra silenciosamente em
    `renderer.load_texture` -- a mesma classe de "valor errado
    silencioso" que `WeaponLoader.load_all_definitions` ja evita para
    `weapon_def_id` (mesma formula de id, mesma guarda).

    Tambem valida que nenhum `texture_id` gerado caia no intervalo
    `[0, SHAPE_MAX]` reservado as formas primitivas (`SHAPE_RECT`/
    `SHAPE_CIRCLE`/`SHAPE_RING`, ver `ouroboros.interfaces.renderer`) --
    `PygameRenderer._draw_shape` consulta a tabela de texturas carregadas
    ANTES de cair no fallback de forma primitiva, entao uma colisao
    (astronomicamente improvavel, mas nao impossivel: `stable_id_from_name`
    e um CRC32 sem exclusao de intervalo) sequestraria silenciosamente o
    desenho de uma forma primitiva em QUALQUER produto, nao so o dono
    deste manifesto.

    Retorna o `frozenset` dos nomes efetivamente registrados.
    """
    with open(manifest_path, "r", encoding="utf-8") as handle:
        raw: Dict[str, str] = json.load(handle)

    ids_by_name: Dict[str, int] = {}
    name_by_id: Dict[int, str] = {}
    for name in raw:
        texture_id = stable_id_from_name(name)
        if texture_id <= SHAPE_MAX:
            raise ValueError(
                f"texture_id de '{name}' ({texture_id}) colidiu com o intervalo "
                f"reservado a formas primitivas (0..{SHAPE_MAX}) em {manifest_path}"
            )
        if texture_id in name_by_id:
            raise ValueError(
                f"texture_id colidiu entre '{name}' e '{name_by_id[texture_id]}' em {manifest_path}"
            )
        ids_by_name[name] = texture_id
        name_by_id[texture_id] = name

    for name, relative_path in raw.items():
        renderer.load_texture(ids_by_name[name], str(textures_root / relative_path))

    return frozenset(raw.keys())
