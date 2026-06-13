"""Database models and connection handling."""

import aiosqlite
import os
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


DATABASE_PATH = "./data/orpheus_poll.db"


class PollAlbum(BaseModel):
    """Model for a poll album entry."""
    id: Optional[int] = None
    artist: str
    album: str
    year: Optional[str] = None
    poll_position: int
    votes: Optional[int] = None
    orpheus_group_id: Optional[int] = None
    available_formats: Optional[str] = None  # JSON string of available formats
    cached_at: Optional[datetime] = None


class TorrentInfo(BaseModel):
    """Model for torrent information."""
    id: int
    group_id: int
    format: str
    encoding: str
    media: str
    size: int
    seeders: int
    leechers: int
    snatched: int
    has_log: bool
    log_score: Optional[int] = None
    has_cue: bool
    scene: bool
    remaster_year: Optional[int] = None
    remaster_title: Optional[str] = None


class TorrentDownload(BaseModel):
    """Model for tracked torrent download."""
    id: Optional[int] = None
    torrent_id: int
    album_id: int
    torrent_hash: Optional[str] = None  # qBittorrent torrent hash
    added_at: Optional[datetime] = None
    status: str = "pending"  # pending, downloading, completed, error
    progress: float = 0.0  # 0.0 to 1.0
    download_path: Optional[str] = None
    error_message: Optional[str] = None


class AoTMWinner(BaseModel):
    """Model for AoTM winner entry."""
    id: Optional[int] = None
    artist: str
    album: str
    year: Optional[str] = None
    thread_id: int
    thread_title: str  # e.g., "AoTM January Round 1 Winner"
    orpheus_group_id: Optional[int] = None
    cached_at: Optional[datetime] = None


async def init_db():
    """Initialize the database with required tables."""
    os.makedirs(os.path.dirname(DATABASE_PATH) or ".", exist_ok=True)
    
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS poll_albums (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL,
                album TEXT NOT NULL,
                year TEXT,
                poll_position INTEGER NOT NULL,
                votes INTEGER,
                orpheus_group_id INTEGER,
                available_formats TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cache_metadata (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS torrent_cache (
                group_id INTEGER PRIMARY KEY,
                torrents_json TEXT,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS torrent_downloads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                torrent_id INTEGER NOT NULL UNIQUE,
                album_id INTEGER NOT NULL,
                torrent_hash TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending',
                progress REAL DEFAULT 0.0,
                download_path TEXT,
                error_message TEXT,
                FOREIGN KEY (album_id) REFERENCES poll_albums(id)
            )
        """)
        
        await db.execute("""
            CREATE TABLE IF NOT EXISTS aotm_winners_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                artist TEXT NOT NULL,
                album TEXT NOT NULL,
                year TEXT,
                thread_id INTEGER NOT NULL UNIQUE,
                thread_title TEXT NOT NULL,
                orpheus_group_id INTEGER,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        await db.commit()


async def save_poll_albums(albums: List[PollAlbum]):
    """Save poll albums to database, replacing existing entries."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        # Clear existing poll albums
        await db.execute("DELETE FROM poll_albums")
        
        for album in albums:
            await db.execute("""
                INSERT INTO poll_albums (artist, album, year, poll_position, votes, orpheus_group_id, available_formats)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (album.artist, album.album, album.year, album.poll_position, album.votes, album.orpheus_group_id, album.available_formats))
        
        # Update cache timestamp
        await db.execute("""
            INSERT OR REPLACE INTO cache_metadata (key, value, updated_at)
            VALUES ('last_poll_fetch', datetime('now'), datetime('now'))
        """)
        
        await db.commit()


async def get_poll_albums() -> List[PollAlbum]:
    """Retrieve all cached poll albums."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM poll_albums ORDER BY poll_position") as cursor:
            rows = await cursor.fetchall()
            return [PollAlbum(**dict(row)) for row in rows]


async def get_cache_timestamp() -> Optional[datetime]:
    """Get the last poll fetch timestamp."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT updated_at FROM cache_metadata WHERE key = 'last_poll_fetch'") as cursor:
            row = await cursor.fetchone()
            if row:
                return datetime.fromisoformat(row['updated_at'])
            return None


async def set_poll_title(title: str):
    """Store the current poll title."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO cache_metadata (key, value, updated_at)
            VALUES ('poll_title', ?, datetime('now'))
        """, (title,))
        await db.commit()


async def get_poll_title() -> Optional[str]:
    """Get the current poll title."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute("SELECT value FROM cache_metadata WHERE key = 'poll_title'") as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return None


async def update_album_group_id(album_id: int, group_id: int, formats: str):
    """Update an album with its Orpheus group ID and available formats."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE poll_albums 
            SET orpheus_group_id = ?, available_formats = ?
            WHERE id = ?
        """, (group_id, formats, album_id))
        await db.commit()


async def cache_torrents(group_id: int, torrents_json: str):
    """Cache torrent information for a group."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO torrent_cache (group_id, torrents_json, cached_at)
            VALUES (?, ?, datetime('now'))
        """, (group_id, torrents_json))
        await db.commit()


async def get_cached_torrents(group_id: int, cache_ttl_minutes: int = 720) -> Optional[str]:
    """Get cached torrents for a group if not stale (default 12h TTL)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        async with db.execute(
            """SELECT torrents_json, cached_at FROM torrent_cache 
               WHERE group_id = ? 
               AND datetime(cached_at, '+' || ? || ' minutes') > datetime('now')""",
            (group_id, cache_ttl_minutes)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return None


async def record_download(torrent_id: int, album_id: int, torrent_hash: Optional[str] = None, status: str = "downloading"):
    """Record a torrent download in the database."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            INSERT OR REPLACE INTO torrent_downloads 
            (torrent_id, album_id, torrent_hash, added_at, status)
            VALUES (?, ?, ?, datetime('now'), ?)
        """, (torrent_id, album_id, torrent_hash, status))
        await db.commit()


async def update_download_progress(torrent_id: int, progress: float, status: str, download_path: Optional[str] = None):
    """Update download progress for a torrent."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE torrent_downloads 
            SET progress = ?, status = ?, download_path = ?
            WHERE torrent_id = ?
        """, (progress, status, download_path, torrent_id))
        await db.commit()


async def get_download_by_torrent_id(torrent_id: int) -> Optional[TorrentDownload]:
    """Get download info by torrent ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM torrent_downloads WHERE torrent_id = ?",
            (torrent_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return TorrentDownload(**dict(row))
            return None


async def get_all_downloads() -> List[TorrentDownload]:
    """Get all download records."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM torrent_downloads ORDER BY added_at DESC") as cursor:
            rows = await cursor.fetchall()
            return [TorrentDownload(**dict(row)) for row in rows]


async def clear_downloads():
    """Clear all download records (for starting fresh)."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM torrent_downloads")
        await db.commit()


async def delete_download_by_torrent_id(torrent_id: int):
    """Delete a specific download record by torrent ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM torrent_downloads WHERE torrent_id = ?", (torrent_id,))
        await db.commit()


async def save_aotm_winners(winners: List["AoTMWinner"]):
    """Save AoTM winners to cache, updating existing entries."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        for winner in winners:
            await db.execute("""
                INSERT OR REPLACE INTO aotm_winners_cache 
                (artist, album, year, thread_id, thread_title, orpheus_group_id, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (winner.artist, winner.album, winner.year, winner.thread_id, 
                  winner.thread_title, winner.orpheus_group_id))
        
        # Update cache timestamp
        await db.execute("""
            INSERT OR REPLACE INTO cache_metadata (key, value, updated_at)
            VALUES ('last_aotm_fetch', datetime('now'), datetime('now'))
        """)
        
        await db.commit()


async def get_aotm_winners() -> List["AoTMWinner"]:
    """Retrieve all cached AoTM winners."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM aotm_winners_cache ORDER BY cached_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [AoTMWinner(**dict(row)) for row in rows]


async def get_aotm_cache_timestamp() -> Optional[datetime]:
    """Get the last AoTM fetch timestamp."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT updated_at FROM cache_metadata WHERE key = 'last_aotm_fetch'"
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return datetime.fromisoformat(row['updated_at'])
            return None


async def update_aotm_winner_group_id(thread_id: int, group_id: int):
    """Update an AoTM winner with its Orpheus group ID."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("""
            UPDATE aotm_winners_cache 
            SET orpheus_group_id = ?
            WHERE thread_id = ?
        """, (group_id, thread_id))
        await db.commit()


async def clear_aotm_cache():
    """Clear all AoTM winners cache."""
    async with aiosqlite.connect(DATABASE_PATH) as db:
        await db.execute("DELETE FROM aotm_winners_cache")
        await db.execute("DELETE FROM cache_metadata WHERE key = 'last_aotm_fetch'")
        await db.commit()
