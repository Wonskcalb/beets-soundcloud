# beets-soundcloud

[![PyPI](https://img.shields.io/pypi/v/beets-soundcloud)](https://pypi.org/project/beets-soundcloud/)
[![Python](https://img.shields.io/pypi/pyversions/beets-soundcloud)](https://pypi.org/project/beets-soundcloud/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/YOUR_USERNAME/beets-soundcloud/actions/workflows/ci.yml/badge.svg)](https://github.com/YOUR_USERNAME/beets-soundcloud/actions/workflows/ci.yml)

A [beets](https://beets.io) plugin that adds **SoundCloud** as an autotagger metadata source. Useful for tracks that MusicBrainz, Discogs, or Spotify don't cover — electronic releases, DJ sets, self-released material, demos.

> **Note on API access**
>
> This plugin uses the **SoundCloud web frontend API** (`api-v2.soundcloud.com`) — the same API the SoundCloud website uses in your browser. No account or subscription is required.
>
> SoundCloud does offer an [official public API](https://developers.soundcloud.com/), but registering an application currently requires an **Artist Pro paid subscription**. If you have one and prefer to use the official API, the configuration section below explains how.

---

## Features

- Works out of the box — no account, no API key, no subscription
- `client_id` auto-extracted from SoundCloud's public JS bundles and cached locally
- Searches SoundCloud **tracks** and **playlists** (treated as albums) during `beet import`
- Extracts artist, title, ISRC, genre, label, release date, and cover art URL
- Uses `publisher_metadata` for accurate artist name and ISRC when available
- Automatic `client_id` refresh if SoundCloud rotates it
- `--search-id` support for direct SoundCloud URLs and numeric IDs

---

## Requirements

- Python ≥ 3.13
- beets ≥ 2.0

---

## Installation

### From PyPI (once published)

```bash
pip install beets-soundcloud
```

### From source with uv

```bash
git clone https://github.com/YOUR_USERNAME/beets-soundcloud
cd beets-soundcloud
uv pip install -e .
```

### From source with pip

```bash
pip install -e .
```

---

## Configuration

The plugin works with zero configuration. Add it to your plugins list and you're done:

```yaml
plugins:
  - soundcloud
```

### Optional settings

```yaml
soundcloud:
  source_weight: 0.9        # lower = preferred over other sources (default 0.9)
  client_id_cache: soundcloud_client_id.json  # cache filename in beets config dir
```

### Setting a client_id manually

If auto-extraction fails (e.g. SoundCloud changes their JS structure), you can provide a `client_id` directly:

1. Open [soundcloud.com](https://soundcloud.com) in a browser
2. Open DevTools → Network tab
3. Play any track, look for a request to `api-v2.soundcloud.com`
4. Copy the `client_id` query parameter from that request

Then add it to your config:

```yaml
soundcloud:
  client_id: YOUR_CLIENT_ID
```

The plugin will also prompt you interactively if auto-extraction fails and no `client_id` is set.

---

## Usage

### Standard import

Enable the plugin, then run `beet import` as usual. SoundCloud candidates appear alongside MusicBrainz results:

```
$ beet import ~/Music/downloads
Tagging:
    Artist - Track Title
(Similarity: 94.3%) (SoundCloud, https://soundcloud.com/artist/track)
```

### Search by SoundCloud URL or ID

```bash
# by permalink URL
beet import --search-id https://soundcloud.com/artist/track-slug

# by numeric SoundCloud ID
beet import --search-id 1234567890
```

---

## Metadata fetched

| beets field | SoundCloud source |
|---|---|
| `title` | `track.title` |
| `artist` | `publisher_metadata.artist` → `user.username` |
| `album` | `playlist.title` |
| `year` / `month` / `day` | `release_date` |
| `length` | `duration` (ms → s) |
| `isrc` | `publisher_metadata.isrc` |
| `genre` | `track.genre` / `playlist.genre` |
| `label` | `label_name` |
| `cover_art_url` | `artwork_url` |

Custom flexible field `soundcloud_track_id` is also stored on each imported track.

---

## client_id caching

On first use, the plugin fetches `soundcloud.com`, locates the JS bundle URLs embedded in the page, and extracts the `client_id` with a regex. The result is saved to `~/.config/beets/soundcloud_client_id.json`.

If a subsequent request returns `401` or `403`, the plugin assumes SoundCloud has rotated the `client_id`, re-extracts it automatically, and retries.

To force a fresh extraction, delete the cache file:

```bash
rm ~/.config/beets/soundcloud_client_id.json
```

---

## Troubleshooting

**`could not obtain a client_id`**
Auto-extraction failed and no manual `client_id` was entered. Check your internet connection, or obtain a `client_id` manually from browser DevTools (see above).

**No SoundCloud candidates shown**
SoundCloud only indexes public tracks. Private tracks and geo-restricted content won't appear. Try `--search-id` with a direct URL.

**Results look stale or incorrect**
The cached `client_id` may be invalid. Delete `~/.config/beets/soundcloud_client_id.json` and retry.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

---

## License

[MIT](LICENSE)
