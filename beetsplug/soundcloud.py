"""Adds SoundCloud track and playlist search support to the beets autotagger.

Uses the SoundCloud web frontend API (api-v2.soundcloud.com) — no account or
paid subscription required. A client_id is extracted automatically from
SoundCloud's public JS bundles and cached locally.

Minimal configuration (no mandatory fields):
    soundcloud:
        source_weight: 0.9

Optional overrides:
    soundcloud:
        client_id: YOUR_CLIENT_ID       # skip auto-extraction
        client_id_cache: soundcloud_client_id.json
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING, ClassVar

import beets.ui
import requests
from beets.autotag import AlbumInfo, TrackInfo
from beets.dbcore import types
from beets.metadata_plugins import IDResponse, SearchApiMetadataSourcePlugin
from beets.ui import UserError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from beets.importer import ImportSession
    from beets.library import Item
    from beets.metadata_plugins import QueryType, SearchParams


API_BASE = "https://api-v2.soundcloud.com"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://soundcloud.com/",
    "Origin": "https://soundcloud.com",
}


def _extract_client_id_from_web() -> str | None:
    """Scrape a valid client_id from SoundCloud's public JS bundles.

    SoundCloud embeds a client_id in their frontend JavaScript. This function
    fetches the homepage, finds the JS bundle URLs, and extracts the client_id
    using a regex. The id changes when SoundCloud deploys a new frontend build.
    """
    try:
        resp = requests.get("https://soundcloud.com", headers=_HEADERS, timeout=15)
        resp.raise_for_status()
    except requests.RequestException:
        return None

    # Find JS bundle URLs embedded as <script src="...">
    script_urls = re.findall(
        r'<script[^>]+src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"',
        resp.text,
    )
    # Try from the end — smaller utility bundles are more likely to carry client_id.
    for url in reversed(script_urls):
        try:
            bundle = requests.get(url, headers=_HEADERS, timeout=15).text
        except requests.RequestException:
            continue
        match = re.search(r'\bclient_id\s*[:=]\s*"([a-zA-Z0-9_-]{20,})"', bundle)
        if match:
            return match.group(1)

    return None


class SoundCloudPlugin(SearchApiMetadataSourcePlugin[IDResponse]):
    """Beets metadata source plugin backed by the SoundCloud frontend API."""

    # data_source is auto-derived from the class name ("SoundCloud") by the
    # base class — no need to override it.

    item_types: ClassVar[dict[str, types.Type]] = {
        "soundcloud_track_id": types.INTEGER,
    }

    # data_source_mismatch_penalty is already provided by MetadataSourcePlugin
    # (default 0.5). Users can override it in their beets config:
    #   soundcloud:
    #     data_source_mismatch_penalty: 0.7
    #
    # min_similarity (0.0–1.0): drop SoundCloud candidates whose beets score
    # is below this threshold before they are shown. Uses beets' own
    # track_distance() internally, so the value matches the % beets displays.
    #   soundcloud:
    #     min_similarity: 0.88
    config_defaults = {
        "client_id": None,
        "client_id_cache": "soundcloud_client_id.json",
        # Filter obviously irrelevant candidates (< 60% raw title+artist match).
        # Do NOT set this too high: SoundCloud titles often have extra descriptors
        # (remix names, mashup credits) that reduce string similarity even for
        # correct matches. Auto-apply protection is handled by beets'
        # strong_rec_thresh + data_source_mismatch_penalty — not by this value.
        "min_similarity": 0.60,
    }

    def __init__(self) -> None:
        super().__init__()
        self.config.add(self.config_defaults)
        self._client_id: str | None = None
        self._client_id_fetched_at: float = 0.0
        self.register_listener("import_begin", self.setup)

    def commands(self):
        cmd = beets.ui.Subcommand(
            "scquery",
            help="Search SoundCloud and print raw results. Usage: beet scquery <query>",
        )
        cmd.func = self._cmd_scquery
        return [cmd]

    def _cmd_scquery(self, lib, opts, args):
        """CLI: beet scquery <query> — show what SoundCloud returns for a query."""
        if not args:
            raise beets.ui.UserError("Usage: beet scquery <query>")

        query = " ".join(args)
        self._ensure_client_id()

        beets.ui.print_(f"client_id : {self._client_id}")
        beets.ui.print_(f"query     : {query!r}")
        beets.ui.print_(f"endpoint  : {API_BASE}/search/tracks\n")

        data = self._get(
            f"{API_BASE}/search/tracks",
            {"q": query, "limit": "10", "linked_partitioning": "1"},
        )
        if data is None:
            beets.ui.print_("API returned None — check client_id and network.")
            return

        collection = data.get("collection", data) if isinstance(data, dict) else data
        beets.ui.print_(f"{len(collection)} result(s):\n")

        for i, t in enumerate(collection, 1):
            pub = t.get("publisher_metadata") or {}
            artist = pub.get("artist") or (t.get("user") or {}).get("username", "?")
            duration_s = (t.get("duration") or 0) // 1000
            beets.ui.print_(
                f"  {i}. {t.get('title', '?')}\n"
                f"     artist   : {artist}\n"
                f"     id       : {t.get('id')}\n"
                f"     duration : {duration_s // 60}:{duration_s % 60:02d}\n"
                f"     url      : {t.get('permalink_url', '?')}\n"
            )

    # ----------------------------------------------------------------- setup

    def setup(self, session: ImportSession | None = None) -> None:
        """Resolve the client_id before import begins."""
        if not self._ensure_client_id():
            raise UserError(
                "soundcloud: could not obtain a client_id. "
                "Set client_id manually in your beets config "
                "(see README for instructions)."
            )

    # --------------------------------------------------------------- client_id

    def _cache_path(self) -> str:
        import confuse

        return self.config["client_id_cache"].get(confuse.Filename(in_app_dir=True))

    def _load_cached_client_id(self) -> str | None:
        try:
            with open(self._cache_path()) as fh:
                data = json.load(fh)
            return data.get("client_id")
        except OSError:
            return None

    def _save_client_id(self, client_id: str) -> None:
        try:
            with open(self._cache_path(), "w") as fh:
                json.dump({"client_id": client_id, "fetched_at": time.time()}, fh)
        except OSError as exc:
            self._log.warning("soundcloud: could not save client_id cache: {}", exc)

    def _ensure_client_id(self) -> str | None:
        """Return a usable client_id, refreshing if necessary."""
        if self._client_id:
            return self._client_id

        # 1. Explicit config value — highest priority, no caching needed.
        configured = self.config["client_id"].get()
        if configured:
            self._client_id = configured
            return self._client_id

        # 2. Disk cache from a previous extraction.
        cached = self._load_cached_client_id()
        if cached:
            self._client_id = cached
            return self._client_id

        # 3. Auto-extract from SoundCloud's public JS bundles.
        self._log.info("soundcloud: extracting client_id from SoundCloud frontend…")
        extracted = _extract_client_id_from_web()
        if extracted:
            self._client_id = extracted
            self._save_client_id(extracted)
            self._log.debug("soundcloud: client_id extracted and cached")
            return self._client_id

        # 4. Interactive fallback.
        beets.ui.print_(
            "soundcloud: automatic client_id extraction failed.\n"
            "To find your client_id manually:\n"
            "  1. Open https://soundcloud.com in a browser\n"
            "  2. Open DevTools → Network tab\n"
            "  3. Play any track, look for a request to api-v2.soundcloud.com\n"
            "  4. Copy the client_id query parameter"
        )
        entered = beets.ui.input_("Enter client_id: ").strip()
        if entered:
            self._client_id = entered
            self._save_client_id(entered)
            return self._client_id

        return None

    def _invalidate_client_id(self) -> None:
        """Clear cached client_id so the next request re-extracts it."""
        self._client_id = None
        try:
            import os

            os.remove(self._cache_path())
        except OSError:
            pass

    # -------------------------------------------------------------- requests

    def _get(self, url: str, params: dict | None = None) -> dict | list | None:
        """GET request with client_id injected; retries once if client_id expired."""
        client_id = self._ensure_client_id()
        if not client_id:
            return None

        all_params = {"client_id": client_id, **(params or {})}

        for attempt in range(2):
            try:
                resp = requests.get(
                    url, headers=_HEADERS, params=all_params, timeout=15
                )
            except requests.RequestException as exc:
                self._log.error("soundcloud: request error for {}: {}", url, exc)
                return None

            if resp.status_code in (401, 403) and attempt == 0:
                # client_id may have been rotated — re-extract and retry.
                self._log.debug(
                    "soundcloud: client_id rejected ({}), re-extracting…",
                    resp.status_code,
                )
                self._invalidate_client_id()
                new_id = _extract_client_id_from_web()
                if new_id:
                    self._client_id = new_id
                    self._save_client_id(new_id)
                    all_params["client_id"] = new_id
                    continue
                return None

            if not resp.ok:
                self._log.debug(
                    "soundcloud: {} {} for {}", resp.status_code, resp.reason, url
                )
                return None

            return resp.json()

        return None

    # ------------------------------------------------- candidate filtering

    def item_candidates(self, item, artist: str, title: str):
        """Return track candidates, filtered by min_similarity if configured."""
        from beets.autotag.match import track_distance

        candidates = list(super().item_candidates(item, artist, title))
        min_sim = self.config["min_similarity"].as_number()
        if min_sim <= 0 or not candidates:
            return candidates

        kept = []
        for info in candidates:
            dist = track_distance(item, info, incl_artist=bool(artist))
            sim = 1.0 - dist.distance
            if sim >= min_sim:
                kept.append(info)
            else:
                self._log.debug(
                    "soundcloud: dropped {!r} — {:.1f}% < min {:.1f}%",
                    info.title,
                    sim * 100,
                    min_sim * 100,
                )
        self._log.debug(
            "soundcloud: {} / {} candidates kept (min_similarity={:.0f}%)",
            len(kept),
            len(candidates),
            min_sim * 100,
        )
        return kept

    # ----------------------------------------- SearchApiMetadataSourcePlugin

    @staticmethod
    def _clean_query(raw: str) -> str:
        """Normalise a raw string into a clean search query.

        Steps applied in order:
        1. Replace underscores with spaces — the most common filename artifact
           (spaces are replaced with underscores by many download tools).
        2. Remove square-bracket content and everything that follows the first
           opening bracket. Square brackets in music filenames are almost always
           download-site watermarks (e.g. [[www.slider.kz]], [ZippyShare.com])
           rather than musically meaningful info.
        3. Remove residual URL tokens (www.*, http*).
        4. Collapse runs of whitespace and strip leading/trailing space.

        Round parentheses are intentionally kept: their content often carries
        important information such as remix names (e.g. "(Club Mix)", "(feat. X)")
        that improve search precision.
        """
        q = raw
        # 1. Underscores → spaces
        q = q.replace("_", " ")
        # 2. Strip square brackets and everything after (handles both [tag] and
        #    unclosed [[www.site fragments at the end of a filename)
        q = re.sub(r"\[.*", "", q)
        # 3. Remove leftover URL-like tokens
        q = re.sub(r"\S*www\.\S*", "", q, flags=re.IGNORECASE)
        q = re.sub(r"https?://\S*", "", q, flags=re.IGNORECASE)
        # 4. Collapse whitespace
        return " ".join(q.split())

    @staticmethod
    def _query_variants(artist: str, name: str) -> list[str]:
        """Build an ordered list of query strings to try, from most to least specific.

        Falls back progressively when the primary query returns no results:
        1. Full  "artist name"
        2. Without featured guests  ("feat. X" / "ft. X" stripped from artist)
        3. First artist only        ("A vs B" → "A";  "A & B" → "A")
        4. Title only               (broadest possible — last resort)
        """
        seen: list[str] = []

        def add(q: str) -> None:
            q = " ".join(q.split())
            if q and q not in seen:
                seen.append(q)

        # 1. Full query
        add(f"{artist} {name}")

        # 2. Strip featured-artist annotations from the artist field
        #    e.g. "ALAIA GALLO Feat BARBATUQUES" → "ALAIA GALLO"
        no_feat = re.sub(
            r"\b(?:feat(?:uring)?|ft)\.?\s+[\w&,\.\s]+",
            "",
            artist,
            flags=re.IGNORECASE,
        ).strip()
        if no_feat != artist:
            add(f"{no_feat} {name}")

        # 3a. "A vs B" → "A"  (mashups — first artist + title)
        first_of_vs = re.split(r"\s+vs\.?\s+", artist, flags=re.IGNORECASE)[0].strip()
        if first_of_vs != artist:
            add(f"{first_of_vs} {name}")

        # 3b. "A & B" / "A , B" → "A"
        first_of_amp = re.split(r"\s*[&,]\s*", artist)[0].strip()
        if first_of_amp not in (artist, first_of_vs):
            add(f"{first_of_amp} {name}")

        # 4. Title only
        add(name)

        return seen

    def get_search_query_with_filters(
        self,
        query_type: QueryType,
        items: Sequence[Item],
        artist: str,
        name: str,
        va_likely: bool,
    ) -> tuple[str, dict[str, str]]:
        # Clean artist and title individually so watermarks in the title
        # don't bleed into the artist portion of the combined query.
        clean_artist = self._clean_query(artist)
        clean_name = self._clean_query(name)

        query = clean_name if va_likely else f"{clean_artist} {clean_name}".strip()

        # When the file has no embedded tags (and fromfilename didn't help),
        # fall back to the filename (without extension) as the search query.
        if not query and items:
            import os

            path = items[0].path
            if isinstance(path, bytes):
                path = path.decode("utf-8", errors="replace")
            raw = os.path.splitext(os.path.basename(path))[0]
            query = self._clean_query(raw)
            self._log.debug(
                "soundcloud: tags empty, filename fallback → query={!r}", query
            )
        else:
            self._log.debug(
                "soundcloud: query built from tags — "
                "artist={!r} name={!r} → query={!r}",
                artist,
                name,
                query,
            )

        # Store context so get_search_response can build fallback variants.
        self._last_clean_artist = clean_artist
        self._last_clean_name = clean_name
        return query, {}

    def _do_search(self, endpoint: str, query: str, limit: int) -> list[IDResponse]:
        """Execute one search request and return the collection list."""
        data = self._get(
            endpoint,
            {
                "q": query,
                "limit": str(limit),
                "offset": "0",
                "linked_partitioning": "1",
            },
        )
        if data is None:
            return []
        return data.get("collection", data) if isinstance(data, dict) else data

    def get_search_response(self, params: SearchParams) -> list[IDResponse]:
        """Search SoundCloud tracks or playlists via the frontend API.

        If the primary query returns no results, progressively simpler fallback
        queries are tried (featured artists stripped, first artist only, title only).
        """
        if not params.query.strip():
            self._log.debug("soundcloud: empty query, skipping search")
            return []

        endpoint = (
            f"{API_BASE}/search/playlists_and_albums"
            if params.query_type == "album"
            else f"{API_BASE}/search/tracks"
        )

        artist = getattr(self, "_last_clean_artist", "")
        name = getattr(self, "_last_clean_name", params.query)
        variants = self._query_variants(artist, name)

        for query in variants:
            self._log.debug(
                "soundcloud: GET {} q={!r} limit={}",
                endpoint.split("/")[-1],
                query,
                params.limit,
            )
            collection = self._do_search(endpoint, query, params.limit)
            if collection:
                self._log.debug(
                    "soundcloud: {} result(s) for q={!r}", len(collection), query
                )
                for i, t in enumerate(collection[:5], 1):
                    self._log.debug(
                        "  {}. {!r} (id={})", i, t.get("title", "?"), t.get("id")
                    )
                return collection
            self._log.debug(
                "soundcloud: 0 results for q={!r}, trying next variant…", query
            )

        self._log.debug("soundcloud: all query variants exhausted, no results")
        return []

    # ------------------------------------------------------- ID-based lookups

    def track_for_id(self, track_id: str) -> TrackInfo | None:
        """Fetch a SoundCloud track by numeric ID or permalink URL."""
        sc_id = self._resolve_id(track_id)
        if sc_id is None:
            return None
        data = self._get(f"{API_BASE}/tracks/{sc_id}")
        if not data:
            return None
        return self._track_info(data)

    def album_for_id(self, album_id: str) -> AlbumInfo | None:
        """Fetch a SoundCloud playlist by numeric ID or permalink URL."""
        sc_id = self._resolve_id(album_id)
        if sc_id is None:
            return None
        data = self._get(f"{API_BASE}/playlists/{sc_id}")
        if not data:
            return None
        return self._album_info(data)

    # ---------------------------------------------------------------- helpers

    def _resolve_id(self, id_str: str) -> str | None:
        """Convert a numeric ID string or a SoundCloud URL into a numeric ID."""
        if str(id_str).isdigit():
            return str(id_str)
        if str(id_str).startswith("http"):
            resolved = self._get(f"{API_BASE}/resolve", {"url": id_str})
            if resolved and "id" in resolved:
                return str(resolved["id"])
        return None

    def _parse_date(
        self, date_str: str | None
    ) -> tuple[int | None, int | None, int | None]:
        if not date_str:
            return None, None, None
        parts = date_str[:10].split("-")
        try:
            year = int(parts[0]) if len(parts) >= 1 else None
            month = int(parts[1]) if len(parts) >= 2 else None
            day = int(parts[2]) if len(parts) >= 3 else None
        except (ValueError, IndexError):
            return None, None, None
        return year, month, day

    @staticmethod
    def _strip_artist_prefix(title: str, artist: str) -> str:
        """Remove a leading 'Artist - ' prefix from a SoundCloud title.

        Many SoundCloud uploaders embed the full 'Artist - Title' string in the
        title field. When we already have the artist separately, stripping this
        prefix produces a cleaner title that matches beets' expectations.
        Only strips when the prefix is an exact case-insensitive match to avoid
        accidentally mangling titles that genuinely start with a dash.
        """
        if artist and " - " in title:
            prefix, rest = title.split(" - ", 1)
            if prefix.strip().lower() == artist.strip().lower():
                return rest.strip()
        return title

    def _track_info(self, data: dict) -> TrackInfo:
        """Convert a SoundCloud track API dict to a beets TrackInfo.

        Artist / title resolution strategy (in priority order):

        1. ``publisher_metadata.artist`` is set → use it as the artist, then
           strip any "Artist - " prefix that may be duplicated in the title.
        2. No publisher metadata but the title follows the "Artist - Title"
           convention (extremely common for user uploads) → split on the first
           " - " and use the left side as the artist.
        3. Fallback: use the SoundCloud uploader username as the artist and
           keep the title unchanged.
        """
        pub = data.get("publisher_metadata") or {}
        raw_title = data["title"]
        artist_id = str((data.get("user") or {}).get("id", ""))
        uploader = (data.get("user") or {}).get("username", "")

        pub_artist = pub.get("artist")
        if pub_artist:
            # Official publisher metadata — most reliable source.
            artist = pub_artist
            title = self._strip_artist_prefix(raw_title, artist)
        elif " - " in raw_title:
            # User upload following "Artist - Title" naming convention.
            prefix, rest = raw_title.split(" - ", 1)
            artist = prefix.strip()
            title = rest.strip()
        else:
            artist = uploader
            title = raw_title

        year, month, day = self._parse_date(
            data.get("release_date") or data.get("display_date")
        )
        return TrackInfo(
            title=title,
            track_id=str(data["id"]),
            soundcloud_track_id=data["id"],
            artist=artist,
            artist_id=artist_id,
            length=(data.get("duration") or 0) / 1000,  # ms → seconds
            isrc=pub.get("isrc"),
            year=year,
            month=month,
            day=day,
            data_source=self.data_source,
            data_url=data.get("permalink_url", ""),
        )

    def _album_info(self, data: dict) -> AlbumInfo | None:
        """Convert a SoundCloud playlist API dict to a beets AlbumInfo."""
        tracks_raw = data.get("tracks") or []
        if not tracks_raw:
            self._log.debug("soundcloud: playlist {} has no tracks", data["id"])
            return None

        tracks: list[TrackInfo] = []
        total = len(tracks_raw)
        for i, t in enumerate(tracks_raw, start=1):
            # Playlist track stubs may only carry the id — fetch full object.
            if not t.get("title"):
                full = self._get(f"{API_BASE}/tracks/{t['id']}")
                if full:
                    t = full
            if not t.get("title"):
                continue
            track = self._track_info(t)
            track.index = i
            track.medium = 1
            track.medium_index = i
            track.medium_total = total
            tracks.append(track)

        if not tracks:
            return None

        user = data.get("user") or {}
        artist = user.get("username", "")
        artist_id = str(user.get("id", ""))
        year, month, day = self._parse_date(
            data.get("release_date") or data.get("display_date")
        )
        return AlbumInfo(
            album=data["title"],
            album_id=str(data["id"]),
            artist=artist,
            artist_id=artist_id,
            tracks=tracks,
            year=year,
            month=month,
            day=day,
            label=data.get("label_name"),
            genre=data.get("genre"),
            mediums=1,
            data_source=self.data_source,
            data_url=data.get("permalink_url", ""),
            cover_art_url=data.get("artwork_url"),
        )
