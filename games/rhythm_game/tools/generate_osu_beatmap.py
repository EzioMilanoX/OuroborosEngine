# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""
Gera o beatmap de modo Osu! de demonstracao (ROADMAP M15), derivando
x/y/sliders DETERMINISTICAMENTE a partir dos onsets JA extraidos de
data/beatmaps/demo_track.beatmap.json -- nunca reanalisa audio (o
pipeline offline de IA, `ouroboros.rhythm.offline.*`, ja rodou uma vez
pra produzir aquele arquivo; este script so posiciona os mesmos eventos
no espaco).

Roda uma vez (resultado vai commitado); nao faz parte do jogo em si.
Uso (SEMPRE como modulo, a partir da raiz do repositorio -- importa
`ouroboros.rhythm.offline.*`, que exige a raiz em `sys.path`):

    python -m games.rhythm_game.tools.generate_osu_beatmap
"""
from __future__ import annotations

import json
from pathlib import Path

from ouroboros.rhythm.offline.osu_beatmap_schema import OsuBeatmapValidator
from ouroboros.rhythm.offline.osu_beatmap_writer import OsuBeatmapWriter
from ouroboros.rhythm.offline.osu_placement import place_hit_objects

_TOOLS_DIR = Path(__file__).resolve().parent
_GAME_DIR = _TOOLS_DIR.parent
_REPO_ROOT = _GAME_DIR.parent.parent

SOURCE_BEATMAP_PATH = _REPO_ROOT / "data" / "beatmaps" / "demo_track.beatmap.json"
OUTPUT_BEATMAP_PATH = _REPO_ROOT / "data" / "beatmaps" / "demo_track_osu.beatmap.json"
TRACK_ID = "demo_track_osu"

# Mesma resolucao logica de games/rhythm_game/config.json -- nao lida de
# la de volta pra manter este script executavel isoladamente, sem
# depender de EngineConfig/CompositionRoot.
PLAYFIELD_WIDTH = 800.0
PLAYFIELD_HEIGHT = 600.0


def main() -> int:
    with SOURCE_BEATMAP_PATH.open("r", encoding="utf-8") as handle:
        source = json.load(handle)

    hit_objects = place_hit_objects(
        threats=tuple(source["threats"]),
        track_id=TRACK_ID,
        bpm=source["bpm"],
        playfield_width=PLAYFIELD_WIDTH,
        playfield_height=PLAYFIELD_HEIGHT,
    )

    validator = OsuBeatmapValidator()
    beatmap_dict = validator.build_beatmap_dict(track_id=TRACK_ID, bpm=source["bpm"], hit_objects=hit_objects)
    OsuBeatmapWriter(validator).write(beatmap_dict, OUTPUT_BEATMAP_PATH)

    slider_count = sum(1 for h in hit_objects if h.threat_type == "osu_slider")
    print(
        f"Beatmap Osu! gerado: {OUTPUT_BEATMAP_PATH} "
        f"({len(hit_objects)} hit-objects, {slider_count} sliders)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
