"""Navidrome client using Subsonic API for managing playlists."""

import hashlib
import logging
import os
import re
import secrets
import unicodedata
import httpx
from typing import List, Optional, Dict, Any, Set
from .config import settings

logger = logging.getLogger(__name__)


def _normalize(s: str) -> str:
    """Normalize string for fuzzy comparison: lowercase, strip accents/punctuation, collapse whitespace."""
    s = unicodedata.normalize('NFKD', s.lower())
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _fuzzy_match(a: str, b: str) -> bool:
    """Fuzzy match two normalised strings.

    Rules (in priority order):
    1. Exact match — always OK.
    2. ``a in b`` — OK (our target string is a substring of the Navidrome value,
       e.g. target="sp 73" found inside "sp 73 remastered").
    3. ``b in a`` — only OK when ``b`` is at least 70 % of ``len(a)``; this
       prevents a short Navidrome value like "20" or "la" from matching long
       target strings such as "la vida era mas corta" or "the 20 greatest…".
    """
    if a == b:
        return True
    if a in b:
        return True
    if b in a and len(a) > 0 and len(b) / len(a) >= 0.7:
        return True
    return False


class NavidromeClient:
    """Client for interacting with Navidrome via Subsonic API."""
    
    def __init__(self):
        self.base_url = settings.navidrome_url.rstrip('/') if settings.navidrome_url else ""
        self.username = settings.navidrome_user
        self.password = settings.navidrome_password
        self.api_version = "1.16.1"
        self.client_name = "OrpheusPollDownloader"
    
    def _get_auth_params(self) -> Dict[str, str]:
        """Get Subsonic API authentication parameters using salted password."""
        salt = secrets.token_hex(8)
        token = hashlib.md5(f"{self.password}{salt}".encode()).hexdigest()
        
        return {
            "u": self.username,
            "t": token,
            "s": salt,
            "v": self.api_version,
            "c": self.client_name,
            "f": "json"
        }
    
    def _check_response(self, data: Dict) -> bool:
        """Check if Subsonic API response is successful."""
        subsonic_response = data.get("subsonic-response", {})
        return subsonic_response.get("status") == "ok"
    
    def _extract_search_terms(self, folder_name: str) -> List[str]:
        """Extract searchable terms from folder name.
        
        Folder format: "Artist - Album (Year) {...} [Format]"
        Returns list of search terms to try.
        """
        import re
        
        # Normalize dashes
        clean = re.sub(r'[–—‒―]', '-', folder_name)
        
        # Remove format tags [...] and catalog {...}
        clean = re.sub(r'\s*\{[^}]*\}', '', clean)
        clean = re.sub(r'\s*\[[^\]]*\]', '', clean)
        
        # Remove year (YYYY)
        clean = re.sub(r'\s*\(\d{4}\)', '', clean).strip()
        
        terms = []
        
        # Try to split by " - " for artist/album
        if " - " in clean:
            parts = clean.split(" - ", 1)
            artist = parts[0].strip()
            album = parts[1].strip()
            
            # Strip trailing format/media descriptors from album name
            # e.g. "The Sun Still Rises - WEB FLAC" → "The Sun Still Rises"
            album = re.sub(
                r'\s*-\s*(WEB|CD|VINYL|FLAC|MP3|AAC|WAV|OPUS|DSD|DIGITAL|LOSSLESS)(\s+.*)?$',
                '', album, flags=re.IGNORECASE
            ).strip()
            
            if artist:
                terms.append(artist)
            if album:
                terms.append(album)
        else:
            terms.append(clean)
        
        return terms
    
    async def find_songs_by_albums(self, albums: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        """Find songs in Navidrome for a list of albums using known artist/album names.
        
        This is more reliable than path-based matching because it uses clean metadata
        from the poll/AoTM data rather than parsing torrent folder names.
        
        Args:
            albums: List of dicts with 'artist' and 'album' keys
            
        Returns:
            List of song dicts with 'id', 'title', 'artist', 'album', 'track', 'path'
        """
        if not self.base_url or not albums:
            return []
        
        songs = []
        found_song_ids: Set[str] = set()
        found_count = 0
        
        logger.info("Searching Navidrome for %d albums by metadata", len(albums))
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for album_info in albums:
                    artist = album_info["artist"]
                    album_name = album_info["album"]
                    
                    target_artist = _normalize(artist)
                    target_album = _normalize(album_name)
                    
                    album_id = None
                    
                    for query in [f"{artist} {album_name}", album_name]:
                        if album_id:
                            break
                        
                        params = self._get_auth_params()
                        params["query"] = query
                        params["songCount"] = 0
                        params["albumCount"] = 20
                        params["artistCount"] = 0
                        
                        response = await client.get(
                            f"{self.base_url}/rest/search3",
                            params=params
                        )
                        
                        if response.status_code != 200:
                            continue
                        
                        data = response.json()
                        if not self._check_response(data):
                            continue
                        
                        search_result = data.get("subsonic-response", {}).get("searchResult3", {})
                        album_list = search_result.get("album", [])
                        
                        if isinstance(album_list, dict):
                            album_list = [album_list]
                        
                        for nav_album in album_list:
                            nav_artist = _normalize(nav_album.get("artist", ""))
                            nav_name = _normalize(nav_album.get("name", ""))

                            artist_ok = _fuzzy_match(target_artist, nav_artist)
                            album_ok = _fuzzy_match(target_album, nav_name)

                            if artist_ok and album_ok:
                                album_id = nav_album.get("id")
                                logger.info("Matched: %s - %s → %s - %s (id=%s)",
                                           artist, album_name,
                                           nav_album.get("artist"), nav_album.get("name"),
                                           album_id)
                                break
                    
                    if album_id:
                        album_songs = await self._get_album_songs(client, album_id)
                        for song in album_songs:
                            if song["id"] not in found_song_ids:
                                found_song_ids.add(song["id"])
                                songs.append(song)
                        found_count += 1
                    else:
                        logger.warning("Album not found in Navidrome: %s - %s", artist, album_name)
            
            songs.sort(key=lambda s: (s.get("album", ""), s.get("track", 0)))
            logger.info("Total: %d songs from %d/%d albums", len(songs), found_count, len(albums))
            
        except Exception as e:
            logger.exception("Error finding songs by album metadata: %s", e)
        
        return songs

    async def find_songs_by_paths(self, file_paths: List[str], navidrome_music_folder: str = "") -> List[Dict[str, Any]]:
        """Find songs in Navidrome based on file paths from qBittorrent.
        
        Uses two strategies:
        1. Match albums by folder name metadata, then validate songs by path prefix.
        2. For unmatched folders, search by track filename → albumId, then validate.
        
        Args:
            file_paths: List of file paths from qBittorrent (e.g., ["Artist - Album/01 - Track.flac"])
            navidrome_music_folder: Navidrome's music root (e.g. "/music"). When set, found
                album songs are filtered to only those whose path lives inside the expected
                folder, preventing false matches from the existing library.
            
        Returns:
            List of song dictionaries with 'id', 'title', 'artist', 'album', 'track', 'path'
        """
        music_root = navidrome_music_folder.rstrip("/")
        if not self.base_url or not file_paths:
            return []
        
        songs = []
        found_song_ids = set()
        found_album_ids = set()
        
        # Extract unique folder names from paths
        folder_names = set()
        paths_by_folder: Dict[str, List[str]] = {}
        for path in file_paths:
            parts = path.replace('\\', '/').split('/')
            if len(parts) > 1:
                folder = parts[0]
                folder_names.add(folder)
                if folder not in paths_by_folder:
                    paths_by_folder[folder] = []
                paths_by_folder[folder].append(path)
        
        logger.info("Searching Navidrome for songs in %d folders", len(folder_names))
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                # Strategy 1: Search by album metadata, validate by path prefix
                for folder_name in folder_names:
                    search_terms = self._extract_search_terms(folder_name)
                    artist = search_terms[0] if search_terms else ""
                    album = search_terms[1] if len(search_terms) > 1 else search_terms[0] if search_terms else ""
                    
                    album_id = await self._find_album_by_metadata(client, artist, album, folder_name)
                    
                    if album_id and album_id not in found_album_ids:
                        album_songs = await self._get_album_songs(client, album_id)
                        
                        # Filter songs to those that live in the expected torrent folder
                        # Navidrome stores paths relative to its music root, so just use folder_name/
                        expected_prefix = f"{folder_name}/"
                        if album_songs:
                            matched = [s for s in album_songs if s.get("path", "").startswith(expected_prefix)]
                            if not matched:
                                logger.warning(
                                    "Album found by metadata but no songs matched path prefix '%s' "
                                    "(got paths like '%s') — skipping",
                                    expected_prefix,
                                    album_songs[0].get("path", "") if album_songs else "(none)"
                                )
                                continue
                            album_songs = matched
                        
                        found_album_ids.add(album_id)
                        for song in album_songs:
                            if song["id"] not in found_song_ids:
                                found_song_ids.add(song["id"])
                                songs.append(song)
                        logger.info("Found %d songs from album metadata (folder: %s)", len(album_songs), folder_name)
                
                # Strategy 2: For unfound folders, search by track filename → albumId
                found_folders = {s.get("path", "").split("/")[-2] for s in songs if "/" in s.get("path", "")}
                unfound_folders = [f for f in folder_names if f not in found_folders]
                
                if unfound_folders:
                    logger.info("Trying track-by-track search for %d unfound folders", len(unfound_folders))
                    
                    for folder in unfound_folders:
                        folder_paths = paths_by_folder.get(folder, [])
                        # Navidrome stores relative paths, so prefix is just folder_name/
                        expected_prefix = f"{folder}/"
                        for path in folder_paths[:3]:  # Sample first 3 tracks
                            track_songs = await self._search_by_track_filename(client, path)
                            # Validate track result lives in the right folder
                            track_songs = [s for s in track_songs if s.get("path", "").startswith(expected_prefix)]
                            if track_songs:
                                album_id = track_songs[0].get("albumId")
                                if album_id and album_id not in found_album_ids:
                                    found_album_ids.add(album_id)
                                    album_songs = await self._get_album_songs(client, album_id)
                                    album_songs = [s for s in album_songs if s.get("path", "").startswith(expected_prefix)]
                                    for song in album_songs:
                                        if song["id"] not in found_song_ids:
                                            found_song_ids.add(song["id"])
                                            songs.append(song)
                                    logger.info("Found %d songs by track search (folder: %s)", len(album_songs), folder)
                                    break
                
                # Sort by album then track
                songs.sort(key=lambda s: (s.get("album", ""), s.get("track", 0)))
                
                logger.info("Total songs found: %d from %d albums", len(songs), len(found_album_ids))
                
        except Exception as e:
            logger.exception("Error finding songs by path: %s", e)
        
        return songs
    
    async def _search_by_track_filename(self, client: httpx.AsyncClient, file_path: str) -> List[Dict[str, Any]]:
        """Search for a track by its filename."""
        import re
        
        # Extract filename without extension
        parts = file_path.replace('\\', '/').split('/')
        filename = parts[-1] if parts else file_path
        
        # Remove extension
        filename_no_ext = re.sub(r'\.[^.]+$', '', filename)
        
        # Remove track number prefix (e.g., "01 - ", "01. ", "1-")
        clean_name = re.sub(r'^[\d]+[\s.\-_]+', '', filename_no_ext).strip()
        
        # Also try without common suffixes
        clean_name = re.sub(r'\s*\([^)]*\)$', '', clean_name).strip()
        
        if not clean_name or len(clean_name) < 3:
            return []
        
        try:
            params = self._get_auth_params()
            params["query"] = clean_name
            params["songCount"] = 20
            params["albumCount"] = 0
            params["artistCount"] = 0
            
            response = await client.get(
                f"{self.base_url}/rest/search3",
                params=params
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            if not self._check_response(data):
                return []
            
            search_result = data.get("subsonic-response", {}).get("searchResult3", {})
            song_list = search_result.get("song", [])
            
            if isinstance(song_list, dict):
                song_list = [song_list]
            
            results = []
            for song in song_list:
                results.append({
                    "id": song.get("id"),
                    "title": song.get("title"),
                    "artist": song.get("artist"),
                    "album": song.get("album"),
                    "albumId": song.get("albumId"),
                    "track": song.get("track", 0),
                    "path": song.get("path", "")
                })
            
            return results
            
        except Exception as e:
            logger.warning("Error searching by track filename '%s': %s", clean_name, e)
            return []
    
    async def _find_album_by_metadata(self, client: httpx.AsyncClient, artist: str, album: str, folder_name: str) -> Optional[str]:
        """Find album ID by artist/album metadata.
        
        Tries multiple search strategies and returns the best matching album ID.
        """
        import re
        
        # Extract year from folder name for validation
        year_match = re.search(r'\((\d{4})\)', folder_name)
        folder_year = int(year_match.group(1)) if year_match else None
        
        # Build search queries to try
        search_queries = []
        if artist and album:
            search_queries.append((f"{artist} {album}", "both"))
        if album:
            search_queries.append((album, "album"))
        if artist:
            search_queries.append((artist, "artist"))
        
        for query, search_type in search_queries:
            params = self._get_auth_params()
            params["query"] = query
            params["songCount"] = 0
            params["albumCount"] = 30
            params["artistCount"] = 0
            
            response = await client.get(
                f"{self.base_url}/rest/search3",
                params=params
            )
            
            if response.status_code != 200:
                continue
            
            data = response.json()
            if not self._check_response(data):
                continue
            
            search_result = data.get("subsonic-response", {}).get("searchResult3", {})
            album_list = search_result.get("album", [])
            
            if isinstance(album_list, dict):
                album_list = [album_list]
            
            if not album_list:
                continue
            
            # Find best matching album
            album_lower = album.lower() if album else ""
            artist_lower = artist.lower() if artist else ""
            
            for nav_album in album_list:
                nav_album_name = nav_album.get("name", "").lower()
                nav_artist_name = nav_album.get("artist", "").lower()
                nav_year = nav_album.get("year")
                
                # Check album name match (exact or contains)
                album_match = _fuzzy_match(album_lower, nav_album_name)

                # Check artist match
                artist_match = _fuzzy_match(artist_lower, nav_artist_name)
                
                # Year validation
                year_exact_match = folder_year and nav_year and folder_year == nav_year
                
                # Accept matches based on search type:
                # 1. Album name match with year match
                # 2. Artist match with exact year match (for localized album names)
                if album_match and (not folder_year or year_exact_match):
                    logger.info("Found album by name: %s - %s (id=%s)", 
                               nav_album.get("artist"), nav_album.get("name"), nav_album.get("id"))
                    return nav_album.get("id")
                
                # For artist-only search: match by artist + exact year (handles localized album names)
                if search_type == "artist" and artist_match and year_exact_match:
                    logger.info("Found album by artist+year: %s - %s (id=%s)", 
                               nav_album.get("artist"), nav_album.get("name"), nav_album.get("id"))
                    return nav_album.get("id")
        
        return None
    
    async def start_scan(self, full: bool = False, targets: Optional[List[str]] = None) -> bool:
        """Trigger a library scan in Navidrome.
        
        Args:
            full: If True, forces a complete rescan of all files.
                  If False (default), performs a quick incremental scan.
        """
        if not self.base_url:
            return False
        
        try:
            param_pairs = list(self._get_auth_params().items())
            param_pairs.append(("fullScan", "true" if full else "false"))
            if targets:
                for t in targets:
                    param_pairs.append(("target", t))
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/rest/startScan",
                    params=param_pairs
                )
                
                if response.status_code == 200:
                    data = response.json()
                    success = self._check_response(data)
                    if success:
                        scan_type = "full" if full else "quick"
                        target_info = f" ({len(targets)} targets)" if targets else ""
                        logger.info("Navidrome %s scan triggered%s", scan_type, target_info)
                    return success
        except Exception as e:
            logger.error("Error triggering Navidrome scan: %s", e)
        
        return False
    
    async def get_scan_status(self) -> Dict[str, Any]:
        """Get current scan status from Navidrome."""
        if not self.base_url:
            return {"scanning": False, "count": 0}
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/rest/getScanStatus",
                    params=self._get_auth_params()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if self._check_response(data):
                        scan_status = data.get("subsonic-response", {}).get("scanStatus", {})
                        return {
                            "scanning": scan_status.get("scanning", False),
                            "count": scan_status.get("count", 0)
                        }
        except Exception as e:
            logger.warning("Error getting Navidrome scan status: %s", e)
        
        return {"scanning": False, "count": 0}
    
    async def get_playlists(self) -> List[Dict[str, Any]]:
        """Get all playlists from Navidrome."""
        if not self.base_url:
            return []
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.base_url}/rest/getPlaylists",
                    params=self._get_auth_params()
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if self._check_response(data):
                        playlists = data.get("subsonic-response", {}).get("playlists", {}).get("playlist", [])
                        # Handle both single playlist and list
                        if isinstance(playlists, dict):
                            playlists = [playlists]
                        return playlists
        except Exception as e:
            logger.warning("Error getting Navidrome playlists: %s", e)
        
        return []
    
    async def get_playlist_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a playlist by name."""
        playlists = await self.get_playlists()
        for playlist in playlists:
            if playlist.get("name") == name:
                return playlist
        return None
    
    async def create_playlist(self, name: str, song_ids: List[str]) -> Optional[str]:
        """Create a new playlist with the given songs.
        
        Args:
            name: Playlist name
            song_ids: List of Subsonic song IDs
            
        Returns:
            Playlist ID if successful, None otherwise
        """
        if not self.base_url or not song_ids:
            return None
        
        try:
            params = self._get_auth_params()
            params["name"] = name
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Create empty playlist first
                response = await client.get(
                    f"{self.base_url}/rest/createPlaylist",
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if self._check_response(data):
                        # Get the created playlist
                        playlist = data.get("subsonic-response", {}).get("playlist", {})
                        playlist_id = playlist.get("id")
                        
                        if playlist_id:
                            # Add songs to playlist
                            success = await self.add_songs_to_playlist(playlist_id, song_ids)
                            if success:
                                logger.info("Created playlist '%s' with %d tracks", name, len(song_ids))
                                return playlist_id
                            else:
                                logger.warning("Created playlist but failed to add songs")
                                return playlist_id
        except Exception as e:
            logger.exception("Error creating Navidrome playlist: %s", e)
        
        return None
    
    async def add_songs_to_playlist(self, playlist_id: str, song_ids: List[str]) -> bool:
        """Add songs to an existing playlist.
        
        Args:
            playlist_id: Playlist ID
            song_ids: List of Subsonic song IDs to add
            
        Returns:
            True if successful, False otherwise
        """
        if not self.base_url or not song_ids:
            return False
        
        try:
            params = self._get_auth_params()
            params["playlistId"] = playlist_id
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Add songs one batch at a time (Subsonic API can take multiple songIdToAdd params)
                # We'll use form data with multiple values
                url = f"{self.base_url}/rest/updatePlaylist"
                
                # Build params with multiple songIdToAdd
                full_params = {**params}
                
                # For httpx, we need to pass lists for repeated params
                response = await client.get(
                    url,
                    params=[
                        *[(k, v) for k, v in full_params.items()],
                        *[("songIdToAdd", sid) for sid in song_ids]
                    ]
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._check_response(data)
        except Exception as e:
            logger.exception("Error adding songs to Navidrome playlist: %s", e)
        
        return False
    
    async def clear_playlist(self, playlist_id: str, song_indexes: List[int]) -> bool:
        """Remove songs from playlist by index.
        
        Args:
            playlist_id: Playlist ID
            song_indexes: List of song indexes to remove (0-based)
            
        Returns:
            True if successful
        """
        if not self.base_url:
            return False
        
        try:
            params = self._get_auth_params()
            params["playlistId"] = playlist_id
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.get(
                    f"{self.base_url}/rest/updatePlaylist",
                    params=[
                        *[(k, v) for k, v in params.items()],
                        *[("songIndexToRemove", str(idx)) for idx in sorted(song_indexes, reverse=True)]
                    ]
                )
                
                if response.status_code == 200:
                    data = response.json()
                    return self._check_response(data)
        except Exception as e:
            logger.warning("Error clearing Navidrome playlist: %s", e)
        
        return False
    
    async def update_playlist(self, playlist_id: str, song_ids: List[str]) -> bool:
        """Update a playlist by replacing all songs.
        
        Args:
            playlist_id: Playlist ID
            song_ids: New list of song IDs
            
        Returns:
            True if successful
        """
        if not self.base_url:
            return False
        
        try:
            # First, get current playlist to know how many songs to remove
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = self._get_auth_params()
                params["id"] = playlist_id
                
                response = await client.get(
                    f"{self.base_url}/rest/getPlaylist",
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if self._check_response(data):
                        playlist = data.get("subsonic-response", {}).get("playlist", {})
                        entries = playlist.get("entry", [])
                        if isinstance(entries, dict):
                            entries = [entries]
                        
                        # Clear existing songs
                        if entries:
                            await self.clear_playlist(playlist_id, list(range(len(entries))))
            
            # Add new songs
            return await self.add_songs_to_playlist(playlist_id, song_ids)
            
        except Exception as e:
            logger.warning("Error updating Navidrome playlist: %s", e)
        
        return False
    
    async def _get_album_songs(self, client: httpx.AsyncClient, album_id: str) -> List[Dict[str, Any]]:
        """Get all songs from an album by ID."""
        songs = []
        
        params = self._get_auth_params()
        params["id"] = album_id
        
        response = await client.get(
            f"{self.base_url}/rest/getAlbum",
            params=params
        )
        
        if response.status_code == 200:
            data = response.json()
            if self._check_response(data):
                album_detail = data.get("subsonic-response", {}).get("album", {})
                song_list = album_detail.get("song", [])
                
                if isinstance(song_list, dict):
                    song_list = [song_list]
                
                for song in song_list:
                    songs.append({
                        "id": song.get("id"),
                        "title": song.get("title"),
                        "artist": song.get("artist"),
                        "album": song.get("album"),
                        "track": song.get("track", 0),
                        "path": song.get("path", "")
                    })
        
        return songs


# Global client instance
navidrome_client = NavidromeClient()
