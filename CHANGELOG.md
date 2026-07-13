# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-06-07

### Added
- Initial release
- SoundCloud track search via `/tracks` endpoint
- SoundCloud playlist search (as albums) via `/playlists` endpoint
- OAuth 2.1 Client Credentials flow with automatic token refresh
- Interactive credential prompt on first run when config is missing
- Token cache at `~/.config/beets/soundcloud_token.json`
- `publisher_metadata` support for accurate artist name and ISRC
- Playlist track stub expansion (fetches full track data when playlists return stubs)
- `--search-id` support for numeric IDs and SoundCloud permalink URLs
- `soundcloud_track_id` custom flexible field
- `source_weight` config option to tune candidate ranking
