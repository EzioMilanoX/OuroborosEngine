# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Testes de SongCatalogLoader (ROADMAP M11.1/M11.2): carga real de data/songs."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ouroboros.rhythm.loaders.song_catalog_loader import SongCatalogError, SongCatalogLoader, SongEntry

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_SONGS_DIR = REPO_ROOT / "data" / "songs"


def test_load_all_reads_the_real_demo_track_entry() -> None:
    loader = SongCatalogLoader(REAL_SONGS_DIR, repo_root=REPO_ROOT)
    songs = loader.load_all()

    assert len(songs) >= 1
    demo = next(song for song in songs if song.track_id == "demo_track")
    assert demo.display_name == "Demo Track"
    assert demo.beatmap_path == REPO_ROOT / "data" / "beatmaps" / "demo_track.beatmap.json"
    assert demo.audio_path == REPO_ROOT / "games" / "rhythm_game" / "assets" / "audio" / "demo_track.wav"
    assert demo.beatmap_path.is_file()
    assert demo.audio_path.is_file()


def test_load_all_reads_the_real_second_track_entry() -> None:
    """ROADMAP M11.2: segunda musica jogavel real, gerada via o pipeline
    offline (perfil hybrid) -- ver games/rhythm_game/tools/generate_second_track.py."""
    loader = SongCatalogLoader(REAL_SONGS_DIR, repo_root=REPO_ROOT)
    songs = loader.load_all()

    assert len(songs) >= 2
    second = next(song for song in songs if song.track_id == "second_track")
    assert second.beatmap_path.is_file()
    assert second.audio_path.is_file()


def test_load_all_returns_song_entry_instances() -> None:
    loader = SongCatalogLoader(REAL_SONGS_DIR, repo_root=REPO_ROOT)
    songs = loader.load_all()

    assert all(isinstance(song, SongEntry) for song in songs)


def _write_song(directory: Path, filename: str, data: dict) -> None:
    (directory / filename).write_text(json.dumps(data), encoding="utf-8")


_VALID_ENTRY = {
    "track_id": "some_track",
    "display_name": "Some Track",
    "beatmap_path": "data/beatmaps/some_track.beatmap.json",
    "audio_path": "assets/audio/some_track.wav",
}


def test_load_all_resolves_relative_paths_against_repo_root(tmp_path) -> None:
    _write_song(tmp_path, "some_track.json", _VALID_ENTRY)
    loader = SongCatalogLoader(tmp_path, repo_root=Path("/repo"))

    songs = loader.load_all()

    assert songs[0].beatmap_path == Path("/repo/data/beatmaps/some_track.beatmap.json")
    assert songs[0].audio_path == Path("/repo/assets/audio/some_track.wav")


def test_load_all_raises_on_missing_required_field(tmp_path) -> None:
    _write_song(tmp_path, "broken.json", {"track_id": "broken", "display_name": "Broken"})
    loader = SongCatalogLoader(tmp_path, repo_root=tmp_path)

    with pytest.raises(SongCatalogError):
        loader.load_all()


def test_load_all_raises_on_malformed_json(tmp_path) -> None:
    (tmp_path / "broken.json").write_text("{not valid json", encoding="utf-8")
    loader = SongCatalogLoader(tmp_path, repo_root=tmp_path)

    with pytest.raises(SongCatalogError):
        loader.load_all()


def test_load_all_raises_on_duplicate_track_id_across_files(tmp_path) -> None:
    _write_song(tmp_path, "a.json", _VALID_ENTRY)
    _write_song(tmp_path, "b.json", _VALID_ENTRY)  # mesmo track_id
    loader = SongCatalogLoader(tmp_path, repo_root=tmp_path)

    with pytest.raises(SongCatalogError):
        loader.load_all()


def test_load_all_raises_when_directory_has_no_songs(tmp_path) -> None:
    loader = SongCatalogLoader(tmp_path, repo_root=tmp_path)

    with pytest.raises(SongCatalogError):
        loader.load_all()
