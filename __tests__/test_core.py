import asyncio
import json
import subprocess
import sys
from unittest import mock

import pytest
from mopidy.models import Album, Artist, Image, Track
from mopidy.types import DurationMs, ReleaseDate, Uri

from mopidy_iris import core as core_lib

CONFIG = {
    "iris": {
        "snapcast_ssl": False,
        "snapcast_host": "localhost",
        "snapcast_port": "1780",
        "snapcast_stream": "Default",
        "verify_certificates": True,
    }
}

TRACK_URI = Uri(
    "local:track:flac/10%2C000_maniacs/"
    "mtv_unplugged_%28expanded_edition%29/01_-_these_are_days.flac"
)
ARTIST_URI = Uri("local:artist:md5:6ec7c3ea99066873f56b934898833252")
ALBUM_URI = Uri("local:album:md5:8fecdcd0b82e56b8da13f15802be071f")
IMAGE_URI = Uri("/local/d62765b1670faf4e2456e9e62bf071e3-1200x1200.jpeg")


def _fresh_interpreter(code):
    """Run code in a clean interpreter, isolated from this process's imports"""
    return subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )


def test_get_version_resolves_packaging_version():
    result = _fresh_interpreter(
        "import mopidy_iris.core, packaging; packaging.version.parse('3.70.0')"
    )

    assert result.returncode == 0, result.stderr


def test_update_snapcast_meta_serializes_mopidy4_models_to_json():
    if not core_lib.MOPIDY_V4:
        pytest.skip("requires Mopidy 4 pydantic models")

    track = Track(
        uri=TRACK_URI,
        name="These Are Days",
        artists=frozenset({Artist(uri=ARTIST_URI, name="10,000 Maniacs")}),
        album=Album(
            uri=ALBUM_URI,
            name="MTV Unplugged (Expanded Edition)",
            artists=frozenset({Artist(uri=ARTIST_URI, name="10,000 Maniacs")}),
            num_tracks=17,
            num_discs=1,
            date=ReleaseDate("1993-10-26"),
        ),
        composers=frozenset(),
        performers=frozenset(),
        genre="Pop Rock",
        track_no=1,
        disc_no=1,
        date=ReleaseDate("1993-10-26"),
        length=DurationMs(293406),
    )
    playback = mock.Mock()
    playback.get_current_track.return_value.get.return_value = track
    library = mock.Mock()
    library.get_images.return_value.get.return_value = {
        TRACK_URI: (Image(uri=IMAGE_URI, width=1200, height=1200),)
    }

    unit = core_lib.IrisCore()
    unit.core = mock.Mock(playback=playback, library=library)
    unit.config = CONFIG

    client = mock.MagicMock()
    client.fetch = mock.AsyncMock(return_value=mock.Mock())

    with mock.patch("mopidy_iris.core.AsyncHTTPClient") as client_factory:
        client_factory.return_value = client
        asyncio.run(
            unit.update_snapcast_meta(ioloop=None, data={}, callback=None)
        )

    (url,) = client.fetch.call_args.args
    kwargs = client.fetch.call_args.kwargs
    assert url == "http://localhost:1780/jsonrpc"
    assert kwargs["method"] == "POST"

    meta = json.loads(kwargs["body"])["params"]["meta"]
    assert meta["name"] == "These Are Days"
    assert meta["uri"] == TRACK_URI
    assert isinstance(meta["artists"], list)
    assert meta["artists"][0]["name"] == "10,000 Maniacs"
    assert isinstance(meta["album"], dict)
    assert meta["album"]["name"] == "MTV Unplugged (Expanded Edition)"
    assert meta["images"][0]["uri"] == IMAGE_URI
    assert meta["images"][0]["width"] == 1200
