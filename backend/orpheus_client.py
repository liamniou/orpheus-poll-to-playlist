"""Orpheus Network API client for fetching poll data and torrents."""

import httpx
import json
import logging
import re
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Any
from .database import PollAlbum, TorrentInfo, AoTMWinner
from .config import settings
from . import __version__

logger = logging.getLogger(__name__)


class OrpheusClient:
    """Client for interacting with Orpheus Network."""
    
    BASE_URL = "https://orpheus.network"
    API_URL = f"{BASE_URL}/ajax.php"
    
    def __init__(self):
        self.session_cookie = settings.orpheus_session_cookie
        self.api_key = settings.orpheus_api_key
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for requests."""
        headers = {
            "User-Agent": f"OrpheusPollToPlaylist/{__version__}",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
        if self.session_cookie:
            # Handle both formats: just the value, or "session=value"
            cookie_value = self.session_cookie
            if cookie_value.startswith("session="):
                headers["Cookie"] = cookie_value
            else:
                headers["Cookie"] = f"session={cookie_value}"
        return headers
    
    def _get_api_params(self) -> Dict[str, str]:
        """Get base API parameters."""
        return {"api_token": self.api_key} if self.api_key else {}
    
    async def fetch_latest_poll(self) -> tuple[List[PollAlbum], Optional[str]]:
        """Fetch the latest poll from Orpheus index page and forum thread.
        
        Returns:
            Tuple of (albums, poll_title)
        """
        if not self.session_cookie:
            raise ValueError("ORPHEUS_SESSION_COOKIE environment variable is not set. Please set it in your .env file or docker-compose environment.")
        
        poll_title = None
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            # Step 1: Get index page to find poll thread ID
            response = await client.get(
                f"{self.BASE_URL}/index.php",
                headers=self._get_headers()
            )
            
            # Check if we were redirected to login page
            if "login.php" in str(response.url) or "/login" in str(response.url):
                raise ValueError("Session cookie is invalid or expired. Please update ORPHEUS_SESSION_COOKIE with a fresh session cookie from your browser.")
            
            response.raise_for_status()
            
            # Parse index page to get poll entries and thread ID
            albums, thread_id = self._parse_poll_html(response.text)
            
            if not albums:
                return albums, poll_title
            
            # Step 2: If we have a thread ID, fetch forum thread to get direct torrent links
            if thread_id:
                thread_response = await client.get(
                    f"{self.BASE_URL}/forums.php?action=viewthread&threadid={thread_id}",
                    headers=self._get_headers()
                )
                thread_response.raise_for_status()
                
                # Extract torrent group IDs from forum thread and poll title
                group_id_map, poll_title = self._parse_forum_thread_for_links(thread_response.text)
                
                # Match albums with their group IDs
                for album in albums:
                    album_key = f"{album.artist} - {album.album}".lower()
                    # Try to find matching group ID
                    for link_text, group_id in group_id_map.items():
                        if self._texts_match(album_key, link_text):
                            album.orpheus_group_id = group_id
                            break
            
            return albums, poll_title
    
    def _parse_forum_thread_for_links(self, html: str) -> tuple[Dict[str, int], Optional[str]]:
        """Parse forum thread to extract torrent links and thread title."""
        soup = BeautifulSoup(html, 'lxml')
        group_id_map = {}
        
        # Extract thread title from breadcrumb h2
        thread_title = None
        h2_elem = soup.find('h2')
        if h2_elem:
            # Text is like "Forums›Album of the Month› AoTM January Round 1 Voting"
            full_text = h2_elem.get_text(strip=True)
            # Split by › and get the last part
            parts = [p.strip() for p in full_text.split('›')]
            if parts:
                thread_title = parts[-1]
                # Remove " Voting" suffix if present
                if thread_title.endswith(' Voting'):
                    thread_title = thread_title[:-7].strip()
        
        # Find all torrent page links
        torrent_links = soup.find_all('a', href=re.compile(r'torrents\.php\?id=(\d+)'))
        
        for link in torrent_links:
            href = link.get('href', '')
            text = link.get_text(strip=True).lower()
            
            # Extract group ID from href
            match = re.search(r'torrents\.php\?id=(\d+)', href)
            if match and text:
                group_id = int(match.group(1))
                group_id_map[text] = group_id
        
        return group_id_map, thread_title
    
    def _texts_match(self, album_text: str, link_text: str) -> bool:
        """Check if album text matches link text (accounting for variations)."""
        # Normalize texts
        album_text = album_text.lower().strip()
        link_text = link_text.lower().strip()
        
        # Normalize dashes (en-dash, em-dash, hyphen all to hyphen)
        album_text = re.sub(r'[–—−]', '-', album_text)
        link_text = re.sub(r'[–—−]', '-', link_text)
        
        # Remove non-ASCII characters from link text for comparison
        link_text_ascii = re.sub(r'[^\x00-\x7F]+', '', link_text).strip()
        
        # Direct match
        if album_text in link_text or link_text in album_text:
            return True
        
        # Try with ASCII-only version of link
        if album_text in link_text_ascii:
            return True
        
        # Extract just artist - album from link (remove year and extra info in parens)
        link_clean = re.sub(r'\s*\([^)]*\)', '', link_text).strip()
        link_clean_ascii = re.sub(r'\s*\([^)]*\)', '', link_text_ascii).strip()
        
        if album_text in link_clean or link_clean in album_text:
            return True
        if album_text in link_clean_ascii or link_clean_ascii in album_text:
            return True
        
        # Check if all words from album are in link (ASCII version)
        album_words = set(album_text.split())
        link_words = set(link_clean_ascii.split())
        if album_words and album_words.issubset(link_words):
            return True
        
        return False
    
    def _parse_poll_html(self, html: str) -> tuple[List[PollAlbum], Optional[int]]:
        """Parse poll data from HTML response. Returns (albums, thread_id)."""
        soup = BeautifulSoup(html, 'lxml')
        albums = []
        thread_id = None
        
        # Look for poll section - typically in a box on the index page
        poll_section = None
        
        # Try finding by looking for "Poll" in header
        for box in soup.find_all('div', class_='box'):
            header = box.find(['h3', 'h4', 'div'], class_=['head', 'box_header', 'colhead_dark'])
            if header and 'poll' in header.get_text().lower():
                poll_section = box
                # Try to extract thread ID from the header link
                header_link = header.find('a', href=re.compile(r'threadid=(\d+)'))
                if header_link:
                    match = re.search(r'threadid=(\d+)', header_link.get('href', ''))
                    if match:
                        thread_id = int(match.group(1))
                break
        
        # Fallback selectors
        if not poll_section:
            poll_section = soup.find('div', class_='box poll') or \
                           soup.find('div', id='poll') or \
                           soup.find('form', id='poll') or \
                           soup.find('div', id='poll_container')
        
        # Also try to get thread ID from form input
        if not thread_id and poll_section:
            thread_input = poll_section.find('input', {'name': 'threadid'})
            if thread_input:
                try:
                    thread_id = int(thread_input.get('value', 0))
                except (ValueError, TypeError):
                    pass
        
        if not poll_section:
            return albums, thread_id
        
        # Extract poll options
        position = 1
        
        # First try: look for label elements (common Orpheus poll format)
        labels = poll_section.find_all('label')
        for label in labels:
            text = label.get_text(strip=True)
            
            # Skip "Blank" or "Show results" options
            if not text or len(text) < 3 or 'blank' in text.lower() or 'show' in text.lower():
                continue
            
            album_info = self._parse_album_string(text)
            if album_info:
                albums.append(PollAlbum(
                    artist=album_info['artist'],
                    album=album_info['album'],
                    year=album_info.get('year'),
                    poll_position=position,
                    votes=None
                ))
                position += 1
        
        # If no labels found, try other patterns (including voted poll results)
        if not albums:
            poll_entries = poll_section.find_all('tr') or \
                           poll_section.find_all('li') or \
                           poll_section.find_all('div', class_='poll_option')
            
            for entry in poll_entries:
                if entry.find('th'):
                    continue
                
                # Skip graph/progress bar elements (used when poll results are shown)
                if 'graph' in entry.get('class', []):
                    continue
                    
                text = entry.get_text(strip=True)
                if not text or len(text) < 3:
                    continue
                
                # Clean up voted indicator arrow (➔) that appears when user has voted
                text = re.sub(r'^➔\s*', '', text)
                
                album_info = self._parse_album_string(text)
                if album_info:
                    votes = None
                    vote_match = re.search(r'\((\d+)\s*votes?\)', text, re.IGNORECASE) or \
                                 re.search(r'(\d+)\s*votes?', text, re.IGNORECASE) or \
                                 re.search(r'(\d+)%', text)
                    if vote_match:
                        votes = int(vote_match.group(1))
                    
                    albums.append(PollAlbum(
                        artist=album_info['artist'],
                        album=album_info['album'],
                        year=album_info.get('year'),
                        poll_position=position,
                        votes=votes
                    ))
                    position += 1
        
        return albums, thread_id
    
    def _parse_album_string(self, text: str) -> Optional[Dict[str, str]]:
        """Parse artist and album from a string."""
        # Remove vote counts and percentages
        clean_text = re.sub(r'\s*\(?\d+\s*votes?\)?', '', text, flags=re.IGNORECASE)
        clean_text = re.sub(r'\s*\d+%', '', clean_text)
        clean_text = clean_text.strip()
        
        # Try different separators
        for sep in [' - ', ' – ', ' — ', ': ']:
            if sep in clean_text:
                parts = clean_text.split(sep, 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    album = parts[1].strip()
                    
                    # Extract year if present
                    year_match = re.search(r'\((\d{4})\)', album)
                    year = year_match.group(1) if year_match else None
                    if year:
                        album = re.sub(r'\s*\(\d{4}\)', '', album).strip()
                    
                    if artist and album:
                        return {'artist': artist, 'album': album, 'year': year}
        
        return None
    
    async def search_album(self, artist: str, album: str) -> Optional[Dict[str, Any]]:
        """Search for an album on Orpheus with multiple strategies."""
        
        # Strategy 1: Search with artist + album
        result = await self._do_search(f"{artist} {album}", artist, album)
        if result:
            return result
        
        # Strategy 2: Search with just album name (useful for non-English artist names)
        result = await self._do_search(album, artist, album)
        if result:
            return result
        
        # Strategy 3: Search with just artist name and look for album match
        result = await self._do_search(artist, artist, album, match_album_only=True)
        if result:
            return result
        
        return None
    
    async def _do_search(self, search_str: str, artist: str, album: str, match_album_only: bool = False) -> Optional[Dict[str, Any]]:
        """Perform a single search query."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                **self._get_api_params(),
                "action": "browse",
                "searchstr": search_str,
            }
            
            response = await client.get(
                self.API_URL,
                params=params,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'success' and data.get('response', {}).get('results'):
                results = data['response']['results']
                
                # Find best match - prioritize exact album name matches
                for result in results:
                    result_artist = (result.get('artist') or '').lower()
                    result_album = (result.get('groupName') or '').lower()
                    
                    # Check album match (handle albums with translations in parentheses)
                    album_lower = album.lower()
                    album_matches = (album_lower in result_album or 
                                    result_album.startswith(album_lower) or
                                    album_lower == result_album.split('(')[0].strip())
                    
                    if match_album_only:
                        # For album-only matching, require exact or very close album match
                        if album_matches and self._is_good_album_match(album, result_album):
                            return result
                    else:
                        # Check both artist and album
                        artist_matches = (artist.lower() in result_artist or 
                                         result_artist in artist.lower() or
                                         self._artist_name_matches(artist, result_artist))
                        if artist_matches and album_matches:
                            return result
                
                # Second pass: look for exact album name match at start of groupName
                for result in results:
                    result_album = (result.get('groupName') or '').lower()
                    if result_album.startswith(album.lower()):
                        return result
            
            return None
    
    def _artist_name_matches(self, search_artist: str, result_artist: str) -> bool:
        """Check if artist names match, accounting for romanization variations."""
        # Common word variations that might indicate same artist
        search_words = set(search_artist.lower().split())
        result_words = set(result_artist.lower().split())
        
        # If any significant word matches, consider it a potential match
        common = search_words & result_words
        return len(common) > 0
    
    def _is_good_album_match(self, search_album: str, result_album: str) -> bool:
        """Check if the album is a good match (not just a partial word match)."""
        search_lower = search_album.lower()
        result_lower = result_album.lower()
        
        # Exact match
        if search_lower == result_lower:
            return True
        
        # Result starts with search term and next char is space, paren, or end
        if result_lower.startswith(search_lower):
            if len(result_lower) == len(search_lower):
                return True
            next_char = result_lower[len(search_lower)]
            if next_char in ' ([':
                return True
        
        return False
    
    async def get_torrent_group(self, group_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed torrent group information."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            params = {
                **self._get_api_params(),
                "action": "torrentgroup",
                "id": group_id,
            }
            
            response = await client.get(
                self.API_URL,
                params=params,
                headers=self._get_headers()
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get('status') == 'success':
                return data.get('response')
            
            return None
    
    async def get_available_formats(self, group_id: int) -> List[TorrentInfo]:
        """Get available torrent formats for a group."""
        group_data = await self.get_torrent_group(group_id)
        
        if not group_data or 'torrents' not in group_data:
            return []
        
        torrents = []
        for t in group_data['torrents']:
            torrents.append(TorrentInfo(
                id=t['id'],
                group_id=group_id,
                format=t.get('format', 'Unknown'),
                encoding=t.get('encoding', 'Unknown'),
                media=t.get('media', 'Unknown'),
                size=t.get('size', 0),
                seeders=t.get('seeders', 0),
                leechers=t.get('leechers', 0),
                snatched=t.get('snatched', 0),
                has_log=t.get('hasLog', False),
                log_score=t.get('logScore'),
                has_cue=t.get('hasCue', False),
                scene=t.get('scene', False),
                remaster_year=t.get('remasterYear'),
                remaster_title=t.get('remasterTitle'),
            ))
        
        return torrents
    
    async def download_torrent(self, torrent_id: int) -> bytes:
        """Download a torrent file."""
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            params = {"id": torrent_id}
            if self.api_key:
                params["torrent_pass"] = self.api_key
            
            response = await client.get(
                f"{self.BASE_URL}/torrents.php",
                params={"action": "download", **params},
                headers=self._get_headers()
            )
            response.raise_for_status()
            
            return response.content
    
    def format_quality_string(self, torrent: TorrentInfo) -> str:
        """Format a human-readable quality string."""
        parts = [torrent.format]
        
        if torrent.encoding and torrent.encoding != 'Unknown':
            parts.append(torrent.encoding)
        
        if torrent.media and torrent.media != 'Unknown':
            parts.append(torrent.media)
        
        if torrent.has_log and torrent.log_score:
            parts.append(f"Log {torrent.log_score}%")
        
        if torrent.has_cue:
            parts.append("Cue")
        
        return " / ".join(parts)
    
    async def fetch_aotm_winners(self, max_pages: int = 10) -> List[AoTMWinner]:
        """Fetch AoTM winners from the forum with direct torrent links.
        
        For each winner thread, fetches the thread page to extract direct torrent links
        (torrents.php?id=XXXXX), which is more reliable than name matching.
        
        Args:
            max_pages: Maximum number of pages to fetch (default 10 to get ~2 years of history)
            
        Returns:
            List of AoTMWinner entries with orpheus_group_id populated
        """
        if not self.session_cookie:
            raise ValueError("ORPHEUS_SESSION_COOKIE environment variable is not set.")
        
        winners = []
        forum_id = 51  # Album of the Month forum
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            # Step 1: Collect all winner thread IDs from forum listing
            thread_infos = []  # List of (thread_id, thread_title, artist, album)
            
            logger.info("Fetching AoTM winner threads from %d forum pages...", max_pages)
            
            for page in range(1, max_pages + 1):
                url = f"{self.BASE_URL}/forums.php?action=viewforum&forumid={forum_id}"
                if page > 1:
                    url += f"&page={page}"
                
                response = await client.get(url, headers=self._get_headers())
                
                if "login.php" in str(response.url) or "/login" in str(response.url):
                    raise ValueError("Session cookie is invalid or expired.")
                
                response.raise_for_status()
                
                # Parse forum page for winner thread info
                page_threads = self._parse_forum_listing_for_winner_threads(response.text)
                thread_infos.extend(page_threads)
                logger.debug("Page %d: found %d winner threads", page, len(page_threads))
            
            logger.info("Found %d total winner threads, fetching torrent links...", len(thread_infos))
            
            # Step 2: Fetch each winner thread to get direct torrent links
            for i, (thread_id, thread_title, artist, album) in enumerate(thread_infos):
                try:
                    thread_url = f"{self.BASE_URL}/forums.php?action=viewthread&threadid={thread_id}"
                    thread_response = await client.get(thread_url, headers=self._get_headers())
                    thread_response.raise_for_status()
                    
                    # Extract torrent group ID from the thread
                    group_id = self._extract_torrent_link_from_thread(thread_response.text)
                    
                    winners.append(AoTMWinner(
                        artist=artist,
                        album=album,
                        year=None,
                        thread_id=thread_id,
                        thread_title=thread_title,
                        orpheus_group_id=group_id
                    ))
                    
                    if (i + 1) % 10 == 0:
                        logger.info("Processed %d/%d winner threads...", i + 1, len(thread_infos))
                        
                except Exception as e:
                    logger.warning("Error fetching thread %d (%s - %s): %s", thread_id, artist, album, e)
                    # Still add the winner even if we couldn't fetch the thread
                    winners.append(AoTMWinner(
                        artist=artist,
                        album=album,
                        year=None,
                        thread_id=thread_id,
                        thread_title=thread_title,
                        orpheus_group_id=None
                    ))
            
            linked_count = sum(1 for w in winners if w.orpheus_group_id)
            logger.info("Completed: %d winners, %d with direct torrent links", len(winners), linked_count)
        
        return winners
    
    def _parse_forum_listing_for_winner_threads(self, html: str) -> List[tuple]:
        """Parse forum listing page for winner thread info.
        
        Returns list of (thread_id, thread_title, artist, album) tuples.
        """
        soup = BeautifulSoup(html, 'lxml')
        results = []
        
        thread_links = soup.find_all('a', href=re.compile(r'forums\.php\?action=viewthread&threadid=(\d+)'))
        
        for link in thread_links:
            text = link.get_text(strip=True)
            
            if 'winner' not in text.lower():
                continue
            
            href = link.get('href', '')
            thread_match = re.search(r'threadid=(\d+)', href)
            if not thread_match:
                continue
            
            thread_id = int(thread_match.group(1))
            
            # Parse: "AoTM January Round 1 Winner - Artist - Album"
            winner_match = re.match(
                r'^(.*?Winner)\s*[-–—]\s*(.+?)\s*[-–—]\s*(.+)$',
                text,
                re.IGNORECASE
            )
            
            if winner_match:
                thread_title = winner_match.group(1).strip()
                artist = winner_match.group(2).strip()
                album = winner_match.group(3).strip()
                
                # Clean up year from album if present
                album = re.sub(r'\s*\(\d{4}\)', '', album).strip()
                
                results.append((thread_id, thread_title, artist, album))
        
        return results
    
    def _extract_torrent_link_from_thread(self, html: str) -> Optional[int]:
        """Extract the first torrent group ID from a forum thread.
        
        Looks for links like: torrents.php?id=78543
        """
        soup = BeautifulSoup(html, 'lxml')
        
        # Find the first post content (usually contains the winner announcement)
        # Look for torrent links in the thread
        torrent_links = soup.find_all('a', href=re.compile(r'torrents\.php\?id=(\d+)'))
        
        for link in torrent_links:
            href = link.get('href', '')
            match = re.search(r'torrents\.php\?id=(\d+)', href)
            if match:
                return int(match.group(1))
        
        return None
    
    def _parse_forum_for_winners(self, html: str) -> List[AoTMWinner]:
        """Parse forum page for AoTM winner threads (legacy method for compatibility)."""
        soup = BeautifulSoup(html, 'lxml')
        winners = []
        
        thread_links = soup.find_all('a', href=re.compile(r'forums\.php\?action=viewthread&threadid=(\d+)'))
        
        for link in thread_links:
            text = link.get_text(strip=True)
            
            if 'winner' not in text.lower():
                continue
            
            href = link.get('href', '')
            thread_match = re.search(r'threadid=(\d+)', href)
            if not thread_match:
                continue
            
            thread_id = int(thread_match.group(1))
            
            winner_match = re.match(
                r'^(.*?Winner)\s*[-–—]\s*(.+?)\s*[-–—]\s*(.+)$',
                text,
                re.IGNORECASE
            )
            
            if winner_match:
                thread_title = winner_match.group(1).strip()
                artist = winner_match.group(2).strip()
                album = winner_match.group(3).strip()
                
                year_match = re.search(r'\((\d{4})\)', album)
                year = year_match.group(1) if year_match else None
                if year:
                    album = re.sub(r'\s*\(\d{4}\)', '', album).strip()
                
                winners.append(AoTMWinner(
                    artist=artist,
                    album=album,
                    year=year,
                    thread_id=thread_id,
                    thread_title=thread_title
                ))
        
        return winners


# Global client instance
orpheus_client = OrpheusClient()
