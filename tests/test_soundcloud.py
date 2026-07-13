"""Unit tests for beetsplug.soundcloud (frontend API, no OAuth)."""

from unittest.mock import MagicMock, patch

import pytest


TRACK_DATA = {
    "id": 123456,
    "title": "Some Track",
    "kind": "track",
    "user": {"id": 99, "username": "some_artist"},
    "duration": 210000,  # ms
    "permalink_url": "https://soundcloud.com/some_artist/some-track",
    "release_date": "2024-03-15T00:00:00Z",
    "publisher_metadata": {
        "artist": "Some Artist",
        "isrc": "USAT12345678",
    },
}

PLAYLIST_DATA = {
    "id": 654321,
    "title": "Some Album",
    "kind": "playlist",
    "user": {"id": 99, "username": "some_artist"},
    "permalink_url": "https://soundcloud.com/some_artist/sets/some-album",
    "release_date": "2024-03-01T00:00:00Z",
    "genre": "Electronic",
    "label_name": "Some Label",
    "artwork_url": "https://i1.sndcdn.com/artworks-000.jpg",
    "tracks": [TRACK_DATA],
}


@pytest.fixture()
def plugin():
    """SoundCloudPlugin with beets internals stubbed out."""
    from beetsplug.soundcloud import SoundCloudPlugin

    p = SoundCloudPlugin.__new__(SoundCloudPlugin)
    p._client_id = "fake_client_id"
    p._client_id_fetched_at = 0.0
    p.data_source = "SoundCloud"
    p._log = MagicMock()
    p.config = MagicMock()
    p.config.__getitem__ = MagicMock(return_value=MagicMock(get=MagicMock(return_value=None)))
    p._get = MagicMock(return_value=None)
    return p


class TestStripArtistPrefix:
    def test_strips_matching_prefix(self):
        """
        Given a title with a leading "Artist - Title" prefix matching the artist
        When stripping the artist prefix
        Then the prefix and separator are removed
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        result = SoundCloudPlugin._strip_artist_prefix(
            "Test Artist & Test Artist Two - Track Name (Remixer Remix)", "Test Artist & Test Artist Two"
        )
        assert result == "Track Name (Remixer Remix)"

    def test_case_insensitive(self):
        """
        Given a title whose artist prefix differs only in letter case
        When stripping the artist prefix
        Then the prefix is still recognised and removed
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        result = SoundCloudPlugin._strip_artist_prefix(
            "ARTIST NAME - Track Title", "Artist Name"
        )
        assert result == "Track Title"

    def test_no_strip_when_prefix_differs(self):
        """
        Given a title whose prefix does not match the given artist
        When stripping the artist prefix
        Then the title is returned unchanged
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        title = "Other Artist - Track Title"
        result = SoundCloudPlugin._strip_artist_prefix(title, "Test Artist")
        assert result == title

    def test_no_strip_when_no_dash(self):
        """
        Given a title with no " - " separator
        When stripping the artist prefix
        Then the title is returned unchanged
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        title = "Track Title Without Dash"
        assert SoundCloudPlugin._strip_artist_prefix(title, "Some Artist") == title

    def test_no_strip_when_artist_empty(self):
        """
        Given an empty artist string
        When stripping the artist prefix
        Then the title is returned unchanged
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        title = "Artist - Title"
        assert SoundCloudPlugin._strip_artist_prefix(title, "") == title

    def test_title_with_multiple_dashes_strips_only_first(self):
        """
        Given a title containing more than one " - " separator
        When stripping the artist prefix
        Then only the first separator is used to split off the prefix
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        result = SoundCloudPlugin._strip_artist_prefix(
            "Test Artist - Track Name - Live", "Test Artist"
        )
        assert result == "Track Name - Live"


class TestParseDate:
    @pytest.fixture(autouse=True)
    def _setup(self, plugin):
        self.p = plugin

    def test_full_iso(self):
        """
        Given a full ISO-8601 timestamp
        When parsing the date
        Then year, month, and day are extracted
        """
        assert self.p._parse_date("2024-03-15T00:00:00Z") == (2024, 3, 15)

    def test_date_only(self):
        """
        Given a plain date string with no time component
        When parsing the date
        Then year, month, and day are extracted
        """
        assert self.p._parse_date("2024-03-15") == (2024, 3, 15)

    def test_year_only(self):
        """
        Given a string containing only a year
        When parsing the date
        Then only the year is returned and month/day are None
        """
        assert self.p._parse_date("2024") == (2024, None, None)

    def test_none(self):
        """
        Given no date string
        When parsing the date
        Then all three components are None
        """
        assert self.p._parse_date(None) == (None, None, None)

    def test_invalid(self):
        """
        Given a string that is not a valid date
        When parsing the date
        Then all three components are None
        """
        assert self.p._parse_date("not-a-date") == (None, None, None)


class TestTrackInfo:
    @pytest.fixture(autouse=True)
    def _setup(self, plugin):
        self.p = plugin

    def test_title_and_id(self):
        """
        Given a SoundCloud track payload
        When converting it to TrackInfo
        Then the title and track_id are mapped correctly
        """
        info = self.p._track_info(TRACK_DATA)
        assert info.title == "Some Track"
        assert info.track_id == "123456"

    def test_duration_converted_to_seconds(self):
        """
        Given a track duration expressed in milliseconds
        When converting it to TrackInfo
        Then the length is converted to seconds
        """
        info = self.p._track_info(TRACK_DATA)
        assert info.length == pytest.approx(210.0)

    def test_artist_from_publisher_metadata(self):
        """
        Given a track with publisher_metadata.artist set
        When converting it to TrackInfo
        Then the artist is taken from publisher_metadata
        """
        info = self.p._track_info(TRACK_DATA)
        assert info.artist == "Some Artist"

    def test_publisher_artist_strips_prefix_from_title(self):
        """
        Given publisher_metadata.artist set and the title repeating that artist as a prefix
        When converting it to TrackInfo
        Then the artist comes from publisher_metadata and the prefix is stripped from the title
        """
        data = {
            **TRACK_DATA,
            "title": "Some Artist - Some Track",
            "publisher_metadata": {"artist": "Some Artist"},
        }
        info = self.p._track_info(data)
        assert info.artist == "Some Artist"
        assert info.title == "Some Track"

    def test_artist_extracted_from_title_convention(self):
        """
        Given no publisher metadata but a title following the "Artist - Title" convention
        When converting it to TrackInfo
        Then the artist is extracted from the title prefix and removed from the title
        """
        data = {
            **TRACK_DATA,
            "title": "Test Artist - Test Track (Official Version)",
            "publisher_metadata": {},
        }
        info = self.p._track_info(data)
        assert info.artist == "Test Artist"
        assert info.title == "Test Track (Official Version)"

    def test_artist_fallback_to_username_when_no_dash_in_title(self):
        """
        Given no publisher metadata and a title with no "Artist - Title" separator
        When converting it to TrackInfo
        Then the artist falls back to the uploader's username
        """
        data = {**TRACK_DATA, "title": "No Dash Here", "publisher_metadata": {}}
        info = self.p._track_info(data)
        assert info.artist == "some_artist"
        assert info.title == "No Dash Here"

    def test_artist_no_user(self):
        """
        Given no publisher metadata, no dash in the title, and no user object
        When converting it to TrackInfo
        Then the artist is an empty string
        """
        data = {**TRACK_DATA, "title": "No Dash", "publisher_metadata": {}, "user": None}
        info = self.p._track_info(data)
        assert info.artist == ""

    def test_isrc(self):
        """
        Given a track with publisher_metadata.isrc set
        When converting it to TrackInfo
        Then the isrc is mapped correctly
        """
        assert self.p._track_info(TRACK_DATA).isrc == "USAT12345678"

    def test_release_date(self):
        """
        Given a track with a release_date
        When converting it to TrackInfo
        Then year, month, and day are populated from it
        """
        info = self.p._track_info(TRACK_DATA)
        assert (info.year, info.month, info.day) == (2024, 3, 15)

    def test_soundcloud_track_id_field(self):
        """
        Given a track payload with a numeric id
        When converting it to TrackInfo
        Then the raw numeric id is exposed as soundcloud_track_id
        """
        assert self.p._track_info(TRACK_DATA).soundcloud_track_id == 123456

    def test_data_source(self):
        """
        Given the plugin's data_source is "SoundCloud"
        When converting a track to TrackInfo
        Then the resulting TrackInfo carries that data_source
        """
        assert self.p._track_info(TRACK_DATA).data_source == "SoundCloud"


class TestAlbumInfo:
    @pytest.fixture(autouse=True)
    def _setup(self, plugin):
        self.p = plugin

    def test_basic_fields(self):
        """
        Given a SoundCloud playlist payload
        When converting it to AlbumInfo
        Then album, album_id, and artist are mapped correctly
        """
        info = self.p._album_info(PLAYLIST_DATA)
        assert info.album == "Some Album"
        assert info.album_id == "654321"
        assert info.artist == "some_artist"

    def test_genre_and_label(self):
        """
        Given a playlist with genre and label_name set
        When converting it to AlbumInfo
        Then genre and label are mapped correctly
        """
        info = self.p._album_info(PLAYLIST_DATA)
        assert info.genre == "Electronic"
        assert info.label == "Some Label"

    def test_tracks_count_and_title(self):
        """
        Given a playlist with one track
        When converting it to AlbumInfo
        Then the album has exactly one track with the expected title
        """
        info = self.p._album_info(PLAYLIST_DATA)
        assert len(info.tracks) == 1
        assert info.tracks[0].title == "Some Track"

    def test_track_index_and_medium(self):
        """
        Given a playlist with a single track
        When converting it to AlbumInfo
        Then that track is assigned index 1 on medium 1 of 1
        """
        info = self.p._album_info(PLAYLIST_DATA)
        t = info.tracks[0]
        assert t.index == 1
        assert t.medium == 1
        assert t.medium_total == 1

    def test_empty_tracks_returns_none(self):
        """
        Given a playlist with an empty tracks list
        When converting it to AlbumInfo
        Then None is returned
        """
        assert self.p._album_info({**PLAYLIST_DATA, "tracks": []}) is None

    def test_stub_track_fetched(self):
        """
        Given a playlist whose track entries are stubs without a title
        When converting it to AlbumInfo
        Then the full track is fetched via _get and its title is used
        """
        stub_playlist = {**PLAYLIST_DATA, "tracks": [{"id": 123456}]}
        self.p._get.return_value = TRACK_DATA
        info = self.p._album_info(stub_playlist)
        self.p._get.assert_called_once()
        assert info.tracks[0].title == "Some Track"

    def test_cover_art_url(self):
        """
        Given a playlist with an artwork_url
        When converting it to AlbumInfo
        Then cover_art_url is mapped correctly
        """
        info = self.p._album_info(PLAYLIST_DATA)
        assert info.cover_art_url == "https://i1.sndcdn.com/artworks-000.jpg"


class TestResolveId:
    @pytest.fixture(autouse=True)
    def _setup(self, plugin):
        self.p = plugin

    def test_numeric_passthrough(self):
        """
        Given a numeric id string
        When resolving the id
        Then it is returned unchanged
        """
        assert self.p._resolve_id("123456") == "123456"

    def test_url_resolved_via_api(self):
        """
        Given a SoundCloud URL
        When resolving the id
        Then the API is queried and the resolved numeric id is returned
        """
        self.p._get.return_value = {"id": 789}
        assert self.p._resolve_id("https://soundcloud.com/artist/track") == "789"

    def test_unresolvable_non_url_returns_none(self):
        """
        Given a string that is neither numeric nor a URL and the API returns nothing
        When resolving the id
        Then None is returned
        """
        self.p._get.return_value = None
        assert self.p._resolve_id("not-an-id") is None


class TestExtractClientId:
    def test_extracts_from_bundle(self):
        """
        Given a homepage response with a JS bundle URL and a bundle containing a client_id
        When extracting the client_id from the web
        Then the client_id is returned
        """
        from beetsplug.soundcloud import _extract_client_id_from_web

        homepage_html = (
            '<script src="https://a-v2.sndcdn.com/assets/app-abc123.js"></script>'
        )
        bundle_js = 'var x={client_id:"AbCdEfGhIjKlMnOpQrSt",other:1}'

        mock_home = MagicMock(ok=True, text=homepage_html)
        mock_bundle = MagicMock(ok=True, text=bundle_js)

        with patch("beetsplug.soundcloud.requests.get") as mock_get:
            mock_get.side_effect = [mock_home, mock_bundle]
            result = _extract_client_id_from_web()

        assert result == "AbCdEfGhIjKlMnOpQrSt"

    def test_returns_none_on_network_error(self):
        """
        Given the network request raises a RequestException
        When extracting the client_id from the web
        Then None is returned
        """
        import requests as req
        from beetsplug.soundcloud import _extract_client_id_from_web

        with patch("beetsplug.soundcloud.requests.get", side_effect=req.RequestException):
            assert _extract_client_id_from_web() is None

    def test_returns_none_when_no_match(self):
        """
        Given a bundle that does not contain a client_id
        When extracting the client_id from the web
        Then None is returned
        """
        from beetsplug.soundcloud import _extract_client_id_from_web

        homepage_html = '<script src="https://a-v2.sndcdn.com/assets/app-abc123.js"></script>'
        bundle_js = "no client id here"

        mock_home = MagicMock(ok=True, text=homepage_html)
        mock_bundle = MagicMock(ok=True, text=bundle_js)

        with patch("beetsplug.soundcloud.requests.get") as mock_get:
            mock_get.side_effect = [mock_home, mock_bundle]
            assert _extract_client_id_from_web() is None


class TestCleanQuery:
    """Tests for the static _clean_query helper."""

    @pytest.fixture(autouse=True)
    def _setup(self, plugin):
        self.p = plugin

    def test_underscores_become_spaces(self):
        """
        Given a raw string with underscores
        When cleaning the query
        Then underscores are replaced with spaces
        """
        assert self.p._clean_query("Test_Track_Name") == "Test Track Name"

    def test_whitespace_collapsed(self):
        """
        Given a raw string with repeated and surrounding whitespace
        When cleaning the query
        Then whitespace runs are collapsed to single spaces
        """
        assert self.p._clean_query("  Test   Artist   Name  ") == "Test Artist Name"

    def test_parentheses_kept(self):
        """
        Given a raw string with remix info in round parentheses
        When cleaning the query
        Then the parenthesised content is preserved
        """
        result = self.p._clean_query("Test Track (Remixer's Remix Name)")
        assert "Remixer" in result
        assert "Remix Name" in result

    def test_square_brackets_removed(self):
        """
        Given a raw string with a square-bracket download-site watermark
        When cleaning the query
        Then the bracketed content is removed and the rest is kept
        """
        result = self.p._clean_query("Test Artist - Test Track [www.example-site.kz]")
        assert "www" not in result
        assert "example-site" not in result
        assert "Test Artist" in result
        assert "Test Track" in result

    def test_unclosed_bracket_watermark_removed(self):
        """
        Given a raw string with an unclosed bracket watermark at the end
        When cleaning the query
        Then everything from the opening bracket onward is removed
        """
        result = self.p._clean_query(
            "Test Artist, Other Artist - Test Track (Club Mix) [[www.example-site"
        )
        assert "www" not in result
        assert "example-site" not in result
        assert "Test Track" in result
        assert "Club Mix" in result

    def test_www_token_removed(self):
        """
        Given a raw string containing a bare "www." token
        When cleaning the query
        Then the token is removed
        """
        result = self.p._clean_query("Track Title www.example.com")
        assert "www" not in result
        assert "Track Title" in result

    def test_http_url_removed(self):
        """
        Given a raw string containing an http(s) URL
        When cleaning the query
        Then the URL is removed
        """
        result = self.p._clean_query("Track Title https://example.com/dl")
        assert "http" not in result
        assert "Track Title" in result

    def test_underscores_inside_parens_become_spaces(self):
        """
        Given a raw string with underscores both inside and outside parentheses
        When cleaning the query
        Then all underscores are replaced with spaces
        """
        raw = "Test Artist - Test Track (Remixer_s _Remix Name_"
        result = self.p._clean_query(raw)
        assert "_" not in result
        assert "Test Artist" in result
        assert "Test Track" in result
        assert "Remixer" in result


class TestQueryVariants:
    """Tests for the fallback query variant generator."""

    def test_full_query_is_first(self):
        """
        Given an artist and a title
        When generating query variants
        Then the first variant is the full "artist title" combination
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        variants = SoundCloudPlugin._query_variants("Test Artist", "Test Title")
        assert variants[0] == "Test Artist Test Title"

    def test_feat_stripped(self):
        """
        Given an artist string containing a "Feat" credit
        When generating query variants
        Then a variant with the featured artist stripped appears before the title-only variant
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        variants = SoundCloudPlugin._query_variants("Primary Artist Feat Featured Artist", "Track Title")
        assert "Primary Artist Track Title" in variants
        # feat variant comes before title-only
        feat_idx = next(i for i, v in enumerate(variants) if "Primary Artist" in v and "Featured Artist" not in v)
        title_idx = variants.index("Track Title")
        assert feat_idx < title_idx

    def test_vs_split(self):
        """
        Given an artist string in "A vs B" form
        When generating query variants
        Then a variant using only the first artist appears before the title-only variant
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        variants = SoundCloudPlugin._query_variants("First Artist vs Second Artist", "Track Title")
        assert "First Artist Track Title" in variants
        # vs variant before title-only
        vs_idx = next(i for i, v in enumerate(variants) if v == "First Artist Track Title")
        title_idx = variants.index("Track Title")
        assert vs_idx < title_idx

    def test_title_only_is_last(self):
        """
        Given an artist and a title with no special separators
        When generating query variants
        Then the title-only variant is last
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        variants = SoundCloudPlugin._query_variants("Some Artist", "Track Title")
        assert variants[-1] == "Track Title"

    def test_no_duplicates(self):
        """
        Given an artist and title with no special separators to expand
        When generating query variants
        Then no variant is repeated
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        variants = SoundCloudPlugin._query_variants("Simple Artist", "Simple Title")
        assert len(variants) == len(set(variants))

    def test_ft_dot_stripped(self):
        """
        Given an artist string using the "ft." abbreviation
        When generating query variants
        Then a variant with the featured artist stripped is produced
        """
        from beetsplug.soundcloud import SoundCloudPlugin
        variants = SoundCloudPlugin._query_variants("Primary Artist ft. Featured Artist", "Track Title")
        assert "Primary Artist Track Title" in variants


class TestSearchQuery:
    @pytest.fixture(autouse=True)
    def _setup(self, plugin):
        self.p = plugin

    def _make_item(self, path: str):
        item = MagicMock()
        item.path = path.encode()
        return item

    def test_normal_artist_and_name(self):
        """
        Given a plain artist and track name
        When building the search query with filters
        Then the query is the artist and name joined by a space
        """
        query, _ = self.p.get_search_query_with_filters(
            "track", [], "Test Artist", "Test Track", False
        )
        assert query == "Test Artist Test Track"

    def test_va_likely_uses_name_only(self):
        """
        Given a likely various-artists album
        When building the search query with filters
        Then the query uses only the album name, not the artist
        """
        query, _ = self.p.get_search_query_with_filters(
            "album", [], "Various", "Compilation", True
        )
        assert query == "Compilation"

    def test_empty_tags_fallback_to_filename_and_cleaned(self):
        """
        Given empty artist/title tags but an item with a filename
        When building the search query with filters
        Then the query falls back to the cleaned filename
        """
        item = self._make_item(
            "/Music/Test Artist - Test Track (Remixer_s _Remix Name_.mp3"
        )
        query, _ = self.p.get_search_query_with_filters("track", [item], "", "", False)
        assert "_" not in query
        assert "Test Artist" in query
        assert "Test Track" in query

    def test_empty_tags_no_items_returns_empty(self):
        """
        Given empty artist/title tags and no items to fall back to
        When building the search query with filters
        Then the query is empty
        """
        query, _ = self.p.get_search_query_with_filters("track", [], "", "", False)
        assert query == ""

    def test_whitespace_is_collapsed(self):
        """
        Given artist and title values with surrounding whitespace
        When building the search query with filters
        Then the resulting query has whitespace collapsed
        """
        query, _ = self.p.get_search_query_with_filters(
            "track", [], "  Test Artist  ", "  Test Track  ", False
        )
        assert query == "Test Artist Test Track"


class TestSearchResponse:
    @pytest.fixture(autouse=True)
    def _setup(self, plugin):
        self.p = plugin

    def test_empty_query_returns_empty_list(self):
        """
        Given a search query that is blank
        When getting the search response
        Then an empty list is returned and the API is not called
        """
        params = MagicMock()
        params.query = "   "
        assert self.p.get_search_response(params) == []
        self.p._get.assert_not_called()

    def test_valid_query_calls_api(self):
        """
        Given a non-empty search query
        When getting the search response
        Then the API is called once and its collection is returned
        """
        params = MagicMock()
        params.query = "Test Artist Test Track"
        params.query_type = "track"
        params.limit = 5
        self.p._get.return_value = {"collection": [TRACK_DATA]}
        result = self.p.get_search_response(params)
        assert result == [TRACK_DATA]
        self.p._get.assert_called_once()
