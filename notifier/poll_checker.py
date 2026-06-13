#!/usr/bin/env python3
"""
Poll Checker - Monitors Orpheus AoTM poll for changes and sends Discord notifications.
Runs once daily via cron or container scheduler.
"""

import os
import sys
import json
import hashlib
import httpx
import asyncio
import re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup
from typing import List, Dict, Optional, Tuple

# Configuration from environment
ORPHEUS_SESSION_COOKIE = os.getenv("ORPHEUS_SESSION_COOKIE", "")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL", "")
STATE_FILE = os.getenv("STATE_FILE", "/app/data/poll_state.json")

ORPHEUS_BASE_URL = "https://orpheus.network"


def get_headers() -> Dict[str, str]:
    """Get headers for Orpheus requests."""
    headers = {
        "User-Agent": "OrpheusPollChecker/1.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    if ORPHEUS_SESSION_COOKIE:
        cookie_value = ORPHEUS_SESSION_COOKIE
        if cookie_value.startswith("session="):
            headers["Cookie"] = cookie_value
        else:
            headers["Cookie"] = f"session={cookie_value}"
    return headers


def parse_album_string(text: str) -> Optional[Dict[str, str]]:
    """Parse artist and album from a string."""
    clean_text = re.sub(r'\s*\(?\d+\s*votes?\)?', '', text, flags=re.IGNORECASE)
    # Remove percentages in various formats: "25%", "(25%)", "25 %", etc.
    clean_text = re.sub(r'\s*\(?\d+\.?\s*%\s*\)?', '', clean_text)
    # Remove standalone numbers with dots/parentheses at the end (leftover from percentage display)
    clean_text = re.sub(r'\s*\(?\d+\.?\)?$', '', clean_text)
    clean_text = clean_text.strip()
    
    for sep in [' - ', ' – ', ' — ', ': ']:
        if sep in clean_text:
            parts = clean_text.split(sep, 1)
            if len(parts) == 2:
                artist = parts[0].strip()
                album = parts[1].strip()
                
                year_match = re.search(r'\((\d{4})\)', album)
                year = year_match.group(1) if year_match else None
                if year:
                    album = re.sub(r'\s*\(\d{4}\)', '', album).strip()
                
                if artist and album:
                    return {'artist': artist, 'album': album, 'year': year}
    
    return None


async def fetch_poll() -> Tuple[List[Dict], Optional[str], Optional[int]]:
    """Fetch current poll data from Orpheus.
    
    Returns:
        Tuple of (albums, poll_title, thread_id)
    """
    if not ORPHEUS_SESSION_COOKIE:
        raise ValueError("ORPHEUS_SESSION_COOKIE not set")
    
    albums = []
    poll_title = None
    thread_id = None
    
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        # Get index page
        response = await client.get(
            f"{ORPHEUS_BASE_URL}/index.php",
            headers=get_headers()
        )
        
        if "login.php" in str(response.url):
            raise ValueError("Session cookie expired")
        
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'lxml')
        
        # Find poll section
        poll_section = None
        for box in soup.find_all('div', class_='box'):
            header = box.find(['h3', 'h4', 'div'], class_=['head', 'box_header', 'colhead_dark'])
            if header and 'poll' in header.get_text().lower():
                poll_section = box
                header_link = header.find('a', href=re.compile(r'threadid=(\d+)'))
                if header_link:
                    match = re.search(r'threadid=(\d+)', header_link.get('href', ''))
                    if match:
                        thread_id = int(match.group(1))
                break
        
        if not poll_section:
            return albums, poll_title, thread_id
        
        # Extract poll options - try labels first (before voting)
        labels = poll_section.find_all('label')
        for label in labels:
            text = label.get_text(strip=True)
            if not text or len(text) < 3 or 'blank' in text.lower() or 'show' in text.lower():
                continue
            
            album_info = parse_album_string(text)
            if album_info:
                albums.append(album_info)
        
        # If no labels found, try list items (after voting)
        if not albums:
            poll_list = poll_section.find('ul', class_='poll')
            if poll_list:
                list_items = poll_list.find_all('li')
                for li in list_items:
                    # Skip graph elements
                    if 'graph' in li.get('class', []):
                        continue
                    
                    text = li.get_text(strip=True)
                    if not text or len(text) < 3:
                        continue
                    
                    # Remove vote indicator arrow (➔)
                    if text.startswith('➔'):
                        text = text[1:].strip()
                    
                    # Remove percentage at the end (e.g., "25%")
                    text = re.sub(r'\s*\d+%\s*$', '', text).strip()
                    
                    if not text or 'blank' in text.lower() or 'show' in text.lower():
                        continue
                    
                    album_info = parse_album_string(text)
                    if album_info:
                        albums.append(album_info)
        
        # Get poll title from forum thread
        if thread_id:
            thread_response = await client.get(
                f"{ORPHEUS_BASE_URL}/forums.php?action=viewthread&threadid={thread_id}",
                headers=get_headers()
            )
            thread_response.raise_for_status()
            
            thread_soup = BeautifulSoup(thread_response.text, 'lxml')
            h2_elem = thread_soup.find('h2')
            if h2_elem:
                full_text = h2_elem.get_text(strip=True)
                parts = [p.strip() for p in full_text.split('›')]
                if parts:
                    poll_title = parts[-1]
                    if poll_title.endswith(' Voting'):
                        poll_title = poll_title[:-7].strip()
    
    return albums, poll_title, thread_id


def load_state() -> Dict:
    """Load previous poll state from file."""
    state_path = Path(STATE_FILE)
    if state_path.exists():
        try:
            with open(state_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass
    return {}


def save_state(state: Dict):
    """Save poll state to file."""
    state_path = Path(STATE_FILE)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with open(state_path, 'w') as f:
        json.dump(state, f, indent=2)


def compute_poll_hash(albums: List[Dict], poll_title: Optional[str]) -> str:
    """Compute a hash of the poll content for change detection."""
    content = json.dumps({
        'title': poll_title,
        'albums': sorted([f"{a['artist']}-{a['album']}" for a in albums])
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


async def send_discord_notification(
    changed: bool,
    poll_title: Optional[str],
    albums: List[Dict],
    previous_title: Optional[str] = None
) -> bool:
    """Send notification to Discord webhook.
    
    Returns:
        True if notification was sent successfully, False otherwise.
    """
    if not DISCORD_WEBHOOK_URL:
        print("DISCORD_WEBHOOK_URL not set, skipping notification")
        return True  # Consider success if not configured
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    if changed:
        # Poll changed notification
        title = f"🗳️ AoTM Poll Updated!"
        color = 0x00FF00  # Green
        
        description = f"**{poll_title or 'Album of the Month'}**\n\n"
        
        if previous_title and previous_title != poll_title:
            description += f"_Previous: {previous_title}_\n\n"
        
        description += "**Current nominees:**\n"
        for i, album in enumerate(albums, 1):
            year_str = f" ({album['year']})" if album.get('year') else ""
            description += f"{i}. **{album['artist']}** - {album['album']}{year_str}\n"
        
        description += f"\n[View Poll on Orpheus]({ORPHEUS_BASE_URL}/index.php)"
    else:
        # No change notification
        title = "📋 AoTM Poll Check"
        color = 0x808080  # Gray
        description = f"No changes detected.\n\n**Current poll:** {poll_title or 'N/A'}\n**Albums:** {len(albums)}"
    
    embed = {
        "title": title,
        "description": description,
        "color": color,
        "footer": {"text": f"Checked at {now}"},
        "thumbnail": {"url": "https://orpheus.network/static/common/noartwork/music.png"}
    }
    
    payload = {
        "username": "Orpheus Poll Checker",
        "embeds": [embed]
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(DISCORD_WEBHOOK_URL, json=payload)
            response.raise_for_status()
            print(f"Discord notification sent successfully")
            return True
        except Exception as e:
            print(f"Failed to send Discord notification: {e}")
            return False


async def main():
    """Main poll checking logic."""
    print(f"=== Orpheus Poll Checker ===")
    print(f"Time: {datetime.now().isoformat()}")
    
    # Validate configuration
    if not ORPHEUS_SESSION_COOKIE:
        print("ERROR: ORPHEUS_SESSION_COOKIE not configured")
        sys.exit(1)
    
    try:
        # Fetch current poll
        print("Fetching current poll from Orpheus...")
        albums, poll_title, thread_id = await fetch_poll()
        
        if not albums:
            print("WARNING: No poll albums found")
            await send_discord_notification(
                changed=True,
                poll_title="⚠️ Poll Not Found",
                albums=[],
                previous_title=None
            )
            return
        
        print(f"Found poll: {poll_title}")
        print(f"Albums: {len(albums)}")
        for album in albums:
            print(f"  - {album['artist']} - {album['album']}")
        
        # Load previous state
        state = load_state()
        previous_hash = state.get('poll_hash')
        previous_title = state.get('poll_title')
        
        # Compute current hash
        current_hash = compute_poll_hash(albums, poll_title)
        
        # Detect changes
        changed = previous_hash != current_hash
        
        if changed:
            print(f"CHANGE DETECTED!")
            print(f"  Previous hash: {previous_hash or 'none'}")
            print(f"  Current hash: {current_hash}")
        else:
            print("No changes detected")
        
        # Send notification
        notification_sent = await send_discord_notification(
            changed=changed,
            poll_title=poll_title,
            albums=albums,
            previous_title=previous_title if changed else None
        )
        
        # Only save state if notification was sent successfully when there's a change
        # This prevents missing change notifications if Discord fails
        if changed and not notification_sent:
            print("WARNING: Change detected but notification failed - NOT saving state to retry next run")
        else:
            save_state({
                'poll_hash': current_hash,
                'poll_title': poll_title,
                'thread_id': thread_id,
                'albums': albums,
                'last_checked': datetime.now().isoformat(),
                'last_change': datetime.now().isoformat() if changed else state.get('last_change')
            })
            print("State saved")
        
    except Exception as e:
        print(f"ERROR: {e}")
        # Try to send error notification
        try:
            if DISCORD_WEBHOOK_URL:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await client.post(DISCORD_WEBHOOK_URL, json={
                        "username": "Orpheus Poll Checker",
                        "embeds": [{
                            "title": "❌ Poll Check Failed",
                            "description": f"Error: {str(e)}",
                            "color": 0xFF0000,
                            "footer": {"text": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                        }]
                    })
        except:
            pass
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
