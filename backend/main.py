"""Main FastAPI application for Orpheus Poll Downloader."""

import json
import logging
import os
import re
import asyncio
import unicodedata
from datetime import datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import __version__
from .config import settings

# Configure logging
logger = logging.getLogger(__name__)
from .database import (
    init_db, save_poll_albums, get_poll_albums, get_cache_timestamp,
    update_album_group_id, cache_torrents, get_cached_torrents, PollAlbum,
    set_poll_title, get_poll_title, save_aotm_winners, get_aotm_winners,
    get_aotm_cache_timestamp, update_aotm_winner_group_id, AoTMWinner
)
from .config import settings as app_settings

# Playlist ID file path
PLAYLIST_ID_FILE = "./data/playlist_id.json"
from .orpheus_client import orpheus_client, TorrentInfo
from .navidrome_client import navidrome_client


class PollAlbumResponse(BaseModel):
    """Response model for poll album."""
    id: int
    artist: str
    album: str
    year: Optional[str]
    poll_position: int
    votes: Optional[int]
    orpheus_group_id: Optional[int]
    available_formats: Optional[List[dict]]
    

class TorrentDownloadRequest(BaseModel):
    """Request model for torrent download."""
    torrent_id: int
    

class BatchDownloadRequest(BaseModel):
    """Request model for batch torrent download to qBittorrent."""
    torrents: List[dict]  # List of {torrent_id: int, album_id: int}


class SelectiveDownloadRequest(BaseModel):
    """Request model for selective album download."""
    album_ids: List[int]
    quality_preference: str = "flac"
    

class SearchRequest(BaseModel):
    """Request model for album search."""
    album_id: int


class RefreshResponse(BaseModel):
    """Response model for refresh operation."""
    success: bool
    message: str
    albums_count: int


class QBitStatusResponse(BaseModel):
    """Response model for qBittorrent status."""
    configured: bool
    connected: bool
    url: Optional[str]


class AoTMWinnerResponse(BaseModel):
    """Response model for AoTM winner."""
    id: int
    artist: str
    album: str
    year: Optional[str]
    thread_id: int
    thread_title: str
    orpheus_group_id: Optional[int]


class AoTMRefreshRequest(BaseModel):
    """Request model for AoTM refresh."""
    max_pages: int = 10


class AddWinnersToQueueRequest(BaseModel):
    """Request model for adding winners to download queue."""
    thread_ids: List[int]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    await init_db()
    yield


app = FastAPI(
    title="Orpheus Poll to Playlist",
    description="Fetch and download albums from Orpheus Network polls",
    version=__version__,
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


@app.get("/api/poll", response_model=List[PollAlbumResponse])
async def get_poll():
    """Get cached poll albums."""
    albums = await get_poll_albums()
    
    result = []
    for album in albums:
        formats = None
        if album.available_formats:
            try:
                formats = json.loads(album.available_formats)
            except json.JSONDecodeError:
                formats = None
        
        result.append(PollAlbumResponse(
            id=album.id,
            artist=album.artist,
            album=album.album,
            year=album.year,
            poll_position=album.poll_position,
            votes=album.votes,
            orpheus_group_id=album.orpheus_group_id,
            available_formats=formats
        ))
    
    return result


@app.post("/api/poll/refresh", response_model=RefreshResponse)
async def refresh_poll(background_tasks: BackgroundTasks):
    """Refresh poll data from Orpheus Network."""
    try:
        albums, poll_title = await orpheus_client.fetch_latest_poll()
        
        if not albums:
            return RefreshResponse(
                success=False,
                message="No poll data found. Make sure you're logged in.",
                albums_count=0
            )
        
        await save_poll_albums(albums)
        
        # Save poll title if we got one
        if poll_title:
            await set_poll_title(poll_title)
        
        # Search for albums in background
        background_tasks.add_task(search_albums_on_orpheus)
        
        return RefreshResponse(
            success=True,
            message=f"Successfully fetched {len(albums)} poll entries",
            albums_count=len(albums)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def search_albums_on_orpheus():
    """Background task to search for poll albums on Orpheus."""
    albums = await get_poll_albums()
    
    for album in albums:
        # Skip if we already have formats
        if album.available_formats:
            continue
        
        group_id = album.orpheus_group_id
        
        # If we don't have a group ID, search for it
        if not group_id:
            try:
                result = await orpheus_client.search_album(album.artist, album.album)
                if result and 'groupId' in result:
                    group_id = result['groupId']
            except Exception as e:
                logger.warning("Error searching for %s - %s: %s", album.artist, album.album, e)
                continue
        
        # Now fetch the available formats
        if group_id:
            try:
                torrents = await orpheus_client.get_available_formats(group_id)
                formats = [
                    {
                        "id": t.id,
                        "quality": orpheus_client.format_quality_string(t),
                        "format": t.format,
                        "encoding": t.encoding,
                        "media": t.media,
                        "size": t.size,
                        "seeders": t.seeders,
                        "leechers": t.leechers,
                        "snatched": t.snatched,
                        "has_log": t.has_log,
                        "log_score": t.log_score,
                    }
                    for t in torrents
                ]
                
                await update_album_group_id(album.id, group_id, json.dumps(formats))
                
                # Cache torrents
                await cache_torrents(group_id, json.dumps([t.model_dump() for t in torrents]))
            except Exception as e:
                logger.warning("Error fetching formats for %s - %s (group %s): %s", album.artist, album.album, group_id, e)
                continue


@app.post("/api/album/{album_id}/search")
async def search_single_album(album_id: int):
    """Search for a single album on Orpheus."""
    albums = await get_poll_albums()
    album = next((a for a in albums if a.id == album_id), None)
    
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    try:
        result = await orpheus_client.search_album(album.artist, album.album)
        
        if not result or 'groupId' not in result:
            raise HTTPException(status_code=404, detail="Album not found on Orpheus")
        
        group_id = result['groupId']
        
        # Get available formats
        torrents = await orpheus_client.get_available_formats(group_id)
        formats = [
            {
                "id": t.id,
                "quality": orpheus_client.format_quality_string(t),
                "format": t.format,
                "encoding": t.encoding,
                "media": t.media,
                "size": t.size,
                "seeders": t.seeders,
                "leechers": t.leechers,
                "snatched": t.snatched,
                "has_log": t.has_log,
                "log_score": t.log_score,
            }
            for t in torrents
        ]
        
        await update_album_group_id(album.id, group_id, json.dumps(formats))
        
        return {
            "success": True,
            "group_id": group_id,
            "formats": formats
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/album/{album_id}/formats")
async def get_album_formats(album_id: int):
    """Get available formats for an album."""
    albums = await get_poll_albums()
    album = next((a for a in albums if a.id == album_id), None)
    
    if not album:
        raise HTTPException(status_code=404, detail="Album not found")
    
    if not album.orpheus_group_id:
        raise HTTPException(status_code=404, detail="Album not yet linked to Orpheus")
    
    if album.available_formats:
        try:
            return json.loads(album.available_formats)
        except json.JSONDecodeError:
            pass
    
    # Fetch fresh format data
    torrents = await orpheus_client.get_available_formats(album.orpheus_group_id)
    formats = [
        {
            "id": t.id,
            "quality": orpheus_client.format_quality_string(t),
            "format": t.format,
            "encoding": t.encoding,
            "media": t.media,
            "size": t.size,
            "seeders": t.seeders,
            "leechers": t.leechers,
            "snatched": t.snatched,
            "has_log": t.has_log,
            "log_score": t.log_score,
        }
        for t in torrents
    ]
    
    await update_album_group_id(album.id, album.orpheus_group_id, json.dumps(formats))
    
    return formats


@app.post("/api/torrent/download")
async def download_torrent(request: TorrentDownloadRequest):
    """Download a torrent file."""
    try:
        torrent_data = await orpheus_client.download_torrent(request.torrent_id)
        
        # Save to downloads directory
        filename = f"{request.torrent_id}.torrent"
        filepath = os.path.join(settings.download_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(torrent_data)
        
        return Response(
            content=torrent_data,
            media_type="application/x-bittorrent",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"'
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_qbit_session() -> tuple[httpx.AsyncClient, str]:
    """Get authenticated qBittorrent session. Returns (client, cookie)."""
    if not settings.qbit_url:
        raise HTTPException(status_code=400, detail="qBittorrent URL not configured")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Login to qBittorrent
        login_response = await client.post(
            f"{settings.qbit_url}/api/v2/auth/login",
            data={
                "username": settings.qbit_user,
                "password": settings.qbit_password,
            }
        )
        
        if login_response.status_code != 200 or login_response.text != "Ok.":
            raise HTTPException(status_code=401, detail="Failed to authenticate with qBittorrent")
        
        # Extract session cookie
        cookie = login_response.cookies.get("SID")
        if not cookie:
            raise HTTPException(status_code=401, detail="No session cookie from qBittorrent")
        
        return cookie


@app.get("/api/qbit/status", response_model=QBitStatusResponse)
async def get_qbit_status():
    """Check qBittorrent connection status."""
    if not settings.qbit_url:
        return QBitStatusResponse(configured=False, connected=False, url=None)
    
    try:
        cookie = await get_qbit_session()
        return QBitStatusResponse(
            configured=True,
            connected=True,
            url=settings.qbit_url
        )
    except Exception:
        return QBitStatusResponse(
            configured=True,
            connected=False,
            url=settings.qbit_url
        )


def _normalize_for_match(s: str) -> str:
    """Normalize string for loose matching: strip accents, punctuation, collapse whitespace."""
    s = unicodedata.normalize('NFKD', s.lower())
    s = re.sub(r'[^\w\s]', '', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def _match_albums_to_torrents(albums, torrent_names: List[str]) -> List[dict]:
    """Match album records (PollAlbum or AoTMWinner) to completed torrent names.
    
    Returns list of {"artist": ..., "album": ...} for albums that have a matching torrent.
    Returns an empty list when nothing matches so the caller can use path-based fallback.
    """
    matched = []
    for album in albums:
        norm_artist = _normalize_for_match(album.artist)
        norm_album = _normalize_for_match(album.album)
        
        for torrent_name in torrent_names:
            norm_torrent = _normalize_for_match(torrent_name)
            if norm_artist in norm_torrent and norm_album in norm_torrent:
                matched.append({"artist": album.artist, "album": album.album})
                break
    
    if not matched:
        logger.warning(
            "Could not match any of the %d albums to %d torrent names — "
            "will fall back to path-based search",
            len(albums), len(torrent_names)
        )
    
    return matched


def get_playlist_tag(poll_title: Optional[str]) -> str:
    """Generate a normalized tag from poll title."""
    current_year = datetime.now().year
    playlist_title = f"{current_year} - {poll_title}" if poll_title else f"Orpheus Poll {current_year}"
    playlist_tag = re.sub(r'[<>:"/\\|?*]', '_', playlist_title)
    return playlist_tag.replace(' ', '_')


def save_playlist_id(playlist_id: str, playlist_name: str, navidrome_url: str):
    """Save the playlist ID to a file."""
    os.makedirs(os.path.dirname(PLAYLIST_ID_FILE), exist_ok=True)
    data = {
        "playlist_id": playlist_id,
        "playlist_name": playlist_name,
        "navidrome_url": navidrome_url.rstrip('/'),
        "playlist_url": f"{navidrome_url.rstrip('/')}/app/#/playlist/{playlist_id}/show",
        "updated_at": datetime.now().isoformat()
    }
    with open(PLAYLIST_ID_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    logger.info("Saved playlist ID %s to %s", playlist_id, PLAYLIST_ID_FILE)


def load_playlist_id() -> Optional[dict]:
    """Load the playlist ID from file."""
    if not os.path.exists(PLAYLIST_ID_FILE):
        return None
    try:
        with open(PLAYLIST_ID_FILE, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.warning("Failed to load playlist ID file: %s", e)
        return None


@app.post("/api/poll/selective-download")
async def selective_download_to_qbit(request: SelectiveDownloadRequest):
    """Download selected poll albums to qBittorrent."""
    logger.info("Selective download request: %d albums", len(request.album_ids))
    
    if not settings.qbit_url:
        raise HTTPException(status_code=400, detail="qBittorrent URL not configured.")
    
    albums = await get_poll_albums()
    selected_albums = [a for a in albums if a.id in request.album_ids]
    
    if not selected_albums:
        raise HTTPException(status_code=400, detail="No valid albums selected")
    
    # Get poll title for tagging
    poll_title = await get_poll_title()
    playlist_tag = get_playlist_tag(poll_title)
    
    # Get torrents for each album based on quality preference
    torrents_to_download = []
    for album in selected_albums:
        if not album.orpheus_group_id:
            continue
        
        try:
            torrents = await orpheus_client.get_available_formats(album.orpheus_group_id)
            if torrents:
                best_torrent = select_torrent_for_quality(torrents, request.quality_preference)
                if best_torrent:
                    torrents_to_download.append({
                        "torrent_id": best_torrent.id,
                        "album_id": album.id
                    })
        except Exception as e:
            logger.warning("Error getting formats for %s - %s: %s", album.artist, album.album, e)
    
    if not torrents_to_download:
        raise HTTPException(status_code=400, detail="No torrents found for selected albums")
    
    # Get qBittorrent session
    try:
        session_cookie = await get_qbit_session()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to qBittorrent: {str(e)}")
    
    results = []
    async with httpx.AsyncClient(timeout=60.0, cookies={"SID": session_cookie}) as client:
        for item in torrents_to_download:
            torrent_id = item.get("torrent_id")
            
            try:
                torrent_data = await orpheus_client.download_torrent(torrent_id)
                
                filename = f"{torrent_id}.torrent"
                filepath = os.path.join(settings.download_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(torrent_data)
                
                files = {
                    'torrents': (filename, torrent_data, 'application/x-bittorrent')
                }
                data = {
                    'tags': playlist_tag,
                }
                if settings.qbit_category:
                    data['category'] = settings.qbit_category
                
                add_response = await client.post(
                    f"{settings.qbit_url}/api/v2/torrents/add",
                    files=files,
                    data=data
                )
                
                if add_response.status_code == 200:
                    results.append({"torrent_id": torrent_id, "success": True})
                else:
                    results.append({"torrent_id": torrent_id, "success": False, "error": f"qBit returned {add_response.status_code}"})
                    
            except Exception as e:
                results.append({"torrent_id": torrent_id, "success": False, "error": str(e)})
    
    success_count = sum(1 for r in results if r.get("success"))
    
    return {
        "success": success_count > 0,
        "message": f"Added {success_count}/{len(torrents_to_download)} torrents to qBittorrent",
        "results": results
    }


@app.post("/api/torrent/batch-download")
async def batch_download_to_qbit(request: BatchDownloadRequest):
    """Download multiple torrents and add them to qBittorrent."""
    logger.info("Batch download request: %d torrents", len(request.torrents))
    
    if not settings.qbit_url:
        raise HTTPException(status_code=400, detail="qBittorrent URL not configured. Set QBIT_URL, QBIT_USER, QBIT_PASSWORD environment variables.")
    
    # Get poll title for tagging
    poll_title = await get_poll_title()
    playlist_tag = get_playlist_tag(poll_title)
    logger.debug("Using tag: %s", playlist_tag)
    
    # Get qBittorrent session
    try:
        session_cookie = await get_qbit_session()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to qBittorrent: {str(e)}")
    
    results = []
    
    async with httpx.AsyncClient(timeout=60.0, cookies={"SID": session_cookie}) as client:
        for item in request.torrents:
            torrent_id = item.get("torrent_id")
            
            if not torrent_id:
                results.append({"torrent_id": torrent_id, "success": False, "error": "Missing torrent_id"})
                continue
            
            try:
                # Download torrent from Orpheus
                torrent_data = await orpheus_client.download_torrent(torrent_id)
                
                # Save locally
                filename = f"{torrent_id}.torrent"
                filepath = os.path.join(settings.download_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(torrent_data)
                
                # Add to qBittorrent using multipart form
                files = {
                    'torrents': (filename, torrent_data, 'application/x-bittorrent')
                }
                data = {
                    'tags': playlist_tag,
                }
                if settings.qbit_category:
                    data['category'] = settings.qbit_category
                
                add_response = await client.post(
                    f"{settings.qbit_url}/api/v2/torrents/add",
                    files=files,
                    data=data
                )
                
                if add_response.status_code == 200:
                    logger.info("Successfully added torrent %s to qBittorrent", torrent_id)
                    results.append({"torrent_id": torrent_id, "success": True})
                else:
                    logger.error("qBittorrent returned status %s for torrent %s", add_response.status_code, torrent_id)
                    results.append({"torrent_id": torrent_id, "success": False, "error": f"qBit returned {add_response.status_code}"})
                    
            except Exception as e:
                logger.error("Error processing torrent %s: %s", torrent_id, e)
                results.append({"torrent_id": torrent_id, "success": False, "error": str(e)})
    
    success_count = sum(1 for r in results if r.get("success"))
    
    logger.info("Batch download complete: %d requested, %d added, %d failed",
                len(request.torrents), success_count, len(request.torrents) - success_count)
    
    return {
        "success": success_count > 0,
        "message": f"Added {success_count}/{len(request.torrents)} torrents to qBittorrent",
        "results": results
    }


@app.get("/api/cache/status")
async def get_cache_status():
    """Get cache status information."""
    timestamp = await get_cache_timestamp()
    albums = await get_poll_albums()
    
    is_stale = True
    if timestamp:
        is_stale = datetime.now() - timestamp > timedelta(minutes=app_settings.cache_ttl_minutes)
    
    return {
        "last_updated": timestamp.isoformat() if timestamp else None,
        "is_stale": is_stale,
        "albums_count": len(albums),
        "linked_count": sum(1 for a in albums if a.orpheus_group_id),
        "cache_ttl_minutes": app_settings.cache_ttl_minutes
    }


# ==================== AoTM Winners Endpoints ====================

@app.get("/api/aotm/winners", response_model=List[AoTMWinnerResponse])
async def get_aotm_winners_list():
    """Get cached AoTM winners."""
    winners = await get_aotm_winners()
    return [
        AoTMWinnerResponse(
            id=w.id,
            artist=w.artist,
            album=w.album,
            year=w.year,
            thread_id=w.thread_id,
            thread_title=w.thread_title,
            orpheus_group_id=w.orpheus_group_id
        )
        for w in winners
    ]


@app.post("/api/aotm/refresh")
async def refresh_aotm_winners(request: AoTMRefreshRequest = AoTMRefreshRequest()):
    """Refresh AoTM winners from Orpheus forum."""
    try:
        winners = await orpheus_client.fetch_aotm_winners(max_pages=request.max_pages)
        
        if not winners:
            return {
                "success": False,
                "message": "No AoTM winners found.",
                "winners_count": 0
            }
        
        await save_aotm_winners(winners)
        
        return {
            "success": True,
            "message": f"Found {len(winners)} AoTM winners",
            "winners_count": len(winners)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/aotm/cache-status")
async def get_aotm_cache_status():
    """Get AoTM cache status."""
    timestamp = await get_aotm_cache_timestamp()
    winners = await get_aotm_winners()
    
    is_stale = True
    if timestamp:
        is_stale = datetime.now() - timestamp > timedelta(minutes=app_settings.cache_ttl_minutes)
    
    return {
        "last_updated": timestamp.isoformat() if timestamp else None,
        "is_stale": is_stale,
        "winners_count": len(winners),
        "linked_count": sum(1 for w in winners if w.orpheus_group_id),
        "cache_ttl_minutes": app_settings.cache_ttl_minutes
    }


@app.post("/api/aotm/winner/{thread_id}/search")
async def search_aotm_winner(thread_id: int):
    """Search for a single AoTM winner on Orpheus."""
    winners = await get_aotm_winners()
    winner = next((w for w in winners if w.thread_id == thread_id), None)
    
    if not winner:
        raise HTTPException(status_code=404, detail="Winner not found")
    
    try:
        result = await orpheus_client.search_album(winner.artist, winner.album)
        
        if not result or 'groupId' not in result:
            raise HTTPException(status_code=404, detail="Album not found on Orpheus")
        
        group_id = result['groupId']
        await update_aotm_winner_group_id(thread_id, group_id)
        
        # Get available formats
        torrents = await orpheus_client.get_available_formats(group_id)
        formats = [
            {
                "id": t.id,
                "quality": orpheus_client.format_quality_string(t),
                "format": t.format,
                "encoding": t.encoding,
                "media": t.media,
                "size": t.size,
                "seeders": t.seeders,
                "leechers": t.leechers,
                "snatched": t.snatched,
                "has_log": t.has_log,
                "log_score": t.log_score,
            }
            for t in torrents
        ]
        
        return {
            "success": True,
            "group_id": group_id,
            "formats": formats
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/aotm/add-to-poll")
async def add_winners_to_poll(request: AddWinnersToQueueRequest):
    """Add selected AoTM winners to the current poll albums list."""
    winners = await get_aotm_winners()
    current_albums = await get_poll_albums()
    
    # Get the max poll_position
    max_position = max((a.poll_position for a in current_albums), default=0)
    
    selected_winners = [w for w in winners if w.thread_id in request.thread_ids]
    
    if not selected_winners:
        raise HTTPException(status_code=400, detail="No valid winners selected")
    
    # Convert winners to PollAlbum format
    new_albums = []
    for i, winner in enumerate(selected_winners):
        # Check if already in poll (by artist + album)
        already_exists = any(
            a.artist.lower() == winner.artist.lower() and 
            a.album.lower() == winner.album.lower()
            for a in current_albums
        )
        
        if already_exists:
            continue
        
        new_albums.append(PollAlbum(
            artist=winner.artist,
            album=winner.album,
            year=winner.year,
            poll_position=max_position + i + 1,
            votes=None,
            orpheus_group_id=winner.orpheus_group_id
        ))
    
    if not new_albums:
        return {
            "success": True,
            "message": "All selected winners are already in the poll",
            "added_count": 0
        }
    
    # Save all albums (current + new)
    all_albums = current_albums + new_albums
    await save_poll_albums(all_albums)
    
    return {
        "success": True,
        "message": f"Added {len(new_albums)} winners to poll",
        "added_count": len(new_albums)
    }


class AoTMDownloadRequest(BaseModel):
    """Request model for AoTM winners download."""
    thread_ids: List[int]
    quality_preference: str = "flac"


@app.post("/api/aotm/batch-download")
async def batch_download_aotm_winners(request: AoTMDownloadRequest, background_tasks: BackgroundTasks):
    """Download selected AoTM winners to qBittorrent."""
    if not settings.qbit_url:
        raise HTTPException(status_code=400, detail="qBittorrent URL not configured.")
    
    winners = await get_aotm_winners()
    selected_winners = [w for w in winners if w.thread_id in request.thread_ids]
    
    if not selected_winners:
        raise HTTPException(status_code=400, detail="No valid winners selected")
    
    # Search for albums that don't have group IDs yet
    for winner in selected_winners:
        if not winner.orpheus_group_id:
            try:
                result = await orpheus_client.search_album(winner.artist, winner.album)
                if result and 'groupId' in result:
                    winner.orpheus_group_id = result['groupId']
                    await update_aotm_winner_group_id(winner.thread_id, result['groupId'])
            except Exception as e:
                logger.warning("Error searching for %s - %s: %s", winner.artist, winner.album, e)
    
    # Get torrents for each winner based on quality preference
    torrents_to_download = []
    for winner in selected_winners:
        if not winner.orpheus_group_id:
            continue
        
        try:
            torrents = await orpheus_client.get_available_formats(winner.orpheus_group_id)
            if torrents:
                # Select best torrent based on preference
                best_torrent = select_torrent_for_quality(torrents, request.quality_preference)
                if best_torrent:
                    torrents_to_download.append({
                        "torrent_id": best_torrent.id,
                        "album_id": winner.thread_id
                    })
        except Exception as e:
            logger.warning("Error getting formats for %s - %s: %s", winner.artist, winner.album, e)
    
    if not torrents_to_download:
        raise HTTPException(status_code=400, detail="No torrents found for selected winners")
    
    # Tag for AoTM winners
    playlist_tag = "AoTM_Winners"
    
    # Get qBittorrent session
    try:
        session_cookie = await get_qbit_session()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to qBittorrent: {str(e)}")
    
    results = []
    async with httpx.AsyncClient(timeout=60.0, cookies={"SID": session_cookie}) as client:
        for item in torrents_to_download:
            torrent_id = item.get("torrent_id")
            
            try:
                torrent_data = await orpheus_client.download_torrent(torrent_id)
                
                filename = f"{torrent_id}.torrent"
                filepath = os.path.join(settings.download_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(torrent_data)
                
                files = {
                    'torrents': (filename, torrent_data, 'application/x-bittorrent')
                }
                data = {
                    'tags': playlist_tag,
                }
                if settings.qbit_category:
                    data['category'] = settings.qbit_category
                
                add_response = await client.post(
                    f"{settings.qbit_url}/api/v2/torrents/add",
                    files=files,
                    data=data
                )
                
                if add_response.status_code == 200:
                    results.append({"torrent_id": torrent_id, "success": True})
                else:
                    results.append({"torrent_id": torrent_id, "success": False, "error": f"qBit returned {add_response.status_code}"})
                    
            except Exception as e:
                results.append({"torrent_id": torrent_id, "success": False, "error": str(e)})
    
    success_count = sum(1 for r in results if r.get("success"))
    
    return {
        "success": success_count > 0,
        "message": f"Added {success_count}/{len(torrents_to_download)} torrents to qBittorrent",
        "results": results
    }


def select_torrent_for_quality(torrents: List, quality_preference: str):
    """Select best torrent based on quality preference."""
    if not torrents:
        return None
    
    def score_torrent(t):
        fmt = (t.format or '').upper()
        enc = (t.encoding or '').upper()
        is_24bit = '24BIT' in enc or '24-BIT' in enc or '24 BIT' in enc
        
        if quality_preference == 'flac_24bit':
            if fmt == 'FLAC' and is_24bit:
                return 100
            if fmt == 'FLAC':
                return 50
            return 0
        elif quality_preference == 'flac':
            if fmt == 'FLAC' and not is_24bit:
                return 100
            if fmt == 'FLAC' and is_24bit:
                return 90
            return 0
        elif quality_preference == 'mp3_320':
            if fmt == 'MP3' and enc == '320':
                return 100
            if fmt == 'MP3' and 'V0' in enc:
                return 80
            if fmt == 'MP3':
                return 60
            return 0
        elif quality_preference == 'mp3_v0':
            if fmt == 'MP3' and 'V0' in enc:
                return 100
            if fmt == 'MP3' and enc == '320':
                return 80
            if fmt == 'MP3':
                return 60
            return 0
        return 0
    
    scored = [(t, score_torrent(t)) for t in torrents]
    scored.sort(key=lambda x: (-x[1], -x[0].seeders))
    
    if scored and scored[0][1] > 0:
        return scored[0][0]
    return torrents[0] if torrents else None


@app.get("/api/aotm/downloads/status")
async def get_aotm_downloads_status():
    """Get status of AoTM winners downloads from qBittorrent."""
    if not settings.qbit_url:
        return {
            "downloads": [],
            "all_completed": False,
            "total": 0,
            "completed": 0
        }
    
    playlist_tag = "AoTM_Winners"
    
    try:
        session_cookie = await get_qbit_session()
        async with httpx.AsyncClient(timeout=30.0, cookies={"SID": session_cookie}) as client:
            torrents_response = await client.get(
                f"{settings.qbit_url}/api/v2/torrents/info",
                params={"tag": playlist_tag}
            )
            
            if torrents_response.status_code != 200:
                return {
                    "downloads": [],
                    "all_completed": False,
                    "total": 0,
                    "completed": 0
                }
            
            qbit_torrents = torrents_response.json()
            
            downloads = []
            for t in qbit_torrents:
                progress = t.get("progress", 0.0)
                state = t.get("state", "")
                save_path = t.get("save_path", "")
                torrent_name = t.get("name", "")
                
                if save_path and torrent_name:
                    full_path = os.path.join(save_path, torrent_name).rstrip('/')
                else:
                    full_path = save_path
                
                if progress >= 1.0 or state in ["uploading", "pausedUP", "stoppedUP"]:
                    status = "completed"
                elif state in ["error", "missingFiles"]:
                    status = "error"
                else:
                    status = "downloading"
                
                downloads.append({
                    "hash": t.get("hash"),
                    "name": torrent_name,
                    "progress": progress,
                    "status": status,
                    "download_path": full_path,
                    "size": t.get("size", 0),
                    "state": state,
                })
            
            total = len(downloads)
            completed = sum(1 for d in downloads if d["status"] == "completed")
            all_completed = total > 0 and completed == total
            
            return {
                "downloads": downloads,
                "all_completed": all_completed,
                "total": total,
                "completed": completed
            }
            
    except Exception as e:
        logger.warning("Error fetching AoTM downloads from qBit: %s", e)
        return {
            "downloads": [],
            "all_completed": False,
            "total": 0,
            "completed": 0
        }


@app.post("/api/aotm/playlist/create")
async def create_aotm_playlist(skip_scan: bool = False):
    """Create Navidrome playlist for completed AoTM winners downloads."""
    if not settings.navidrome_url or not settings.navidrome_user:
        raise HTTPException(status_code=400, detail="Navidrome not configured.")
    
    if not settings.qbit_url:
        raise HTTPException(status_code=400, detail="qBittorrent not configured.")
    
    playlist_title = "AoTM Winners"
    playlist_tag = "AoTM_Winners"
    
    try:
        session_cookie = await get_qbit_session()
        async with httpx.AsyncClient(timeout=30.0, cookies={"SID": session_cookie}) as client:
            torrents_response = await client.get(
                f"{settings.qbit_url}/api/v2/torrents/info",
                params={"tag": playlist_tag}
            )
            
            if torrents_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch torrents from qBittorrent")
            
            qbit_torrents = torrents_response.json()
            
            all_file_paths = []
            completed_torrent_names = []
            completed_folder_paths = []
            
            for t in qbit_torrents:
                progress = t.get("progress", 0.0)
                state = t.get("state", "")
                torrent_hash = t.get("hash", "")
                torrent_name = t.get("name", "")
                save_path = t.get("save_path", "").rstrip("/")
                
                if progress >= 1.0 or state in ["uploading", "pausedUP", "stoppedUP"]:
                    files_response = await client.get(
                        f"{settings.qbit_url}/api/v2/torrents/files",
                        params={"hash": torrent_hash}
                    )
                    
                    if files_response.status_code == 200:
                        files = files_response.json()
                        for f in files:
                            file_name = f.get("name", "")
                            if file_name.lower().endswith(('.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wav', '.aac')):
                                all_file_paths.append(file_name)
                        
                        if files:
                            completed_torrent_names.append(torrent_name)
                            if save_path and torrent_name:
                                completed_folder_paths.append(os.path.join(save_path, torrent_name))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to qBittorrent: {str(e)}")
    
    if not completed_torrent_names:
        raise HTTPException(status_code=400, detail="No completed downloads found")
    
    try:
        if not skip_scan:
            lib_id = app_settings.navidrome_library_id
            scan_targets = None
            if completed_folder_paths:
                music_root = app_settings.navidrome_music_folder.rstrip("/")
                if music_root:
                    # Translate qBit paths to Navidrome-visible paths:
                    # strip qBit save_path prefix, prepend Navidrome music folder
                    navidrome_paths = [
                        f"{music_root}/{os.path.basename(p)}" for p in completed_folder_paths
                    ]
                else:
                    navidrome_paths = completed_folder_paths
                scan_targets = [f"{lib_id}:{p}" for p in navidrome_paths]
            logger.info("Triggering Navidrome targeted scan for %d folders: %s", len(completed_folder_paths), scan_targets)
            await navidrome_client.start_scan(targets=scan_targets)
            
            max_wait = 120
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(2)
                waited += 2
                status = await navidrome_client.get_scan_status()
                if not status.get("scanning"):
                    logger.info("Scan completed after %ds", waited)
                    break
            else:
                logger.warning("Scan still running after %ds, continuing anyway...", max_wait)
        
        # Match AoTM winners against completed torrent names
        winners = await get_aotm_winners()
        downloaded_albums = _match_albums_to_torrents(winners, completed_torrent_names)
        
        music_folder = app_settings.navidrome_music_folder
        songs = []
        if all_file_paths:
            logger.info("Searching Navidrome by path for %d files (music_folder=%r)", len(all_file_paths), music_folder)
            songs = await navidrome_client.find_songs_by_paths(all_file_paths, navidrome_music_folder=music_folder)
        
        if not songs and downloaded_albums:
            logger.warning("Path-based search found no songs, falling back to metadata search")
            songs = await navidrome_client.find_songs_by_albums(downloaded_albums)
        
        if not songs:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No tracks found in Navidrome for the {len(completed_torrent_names)} downloaded album(s). "
                    "Make sure the library scan completed and the files are indexed."
                )
            )
        
        all_song_ids = [song["id"] for song in songs]
        
        existing_playlist = await navidrome_client.get_playlist_by_name(playlist_title)
        
        if existing_playlist:
            playlist_id = existing_playlist.get("id")
            success = await navidrome_client.update_playlist(playlist_id, all_song_ids)
            
            if success:
                return {
                    "success": True,
                    "message": f"Updated Navidrome playlist '{playlist_title}'",
                    "playlist_id": playlist_id,
                    "playlist_name": playlist_title,
                    "playlist_url": f"{settings.navidrome_url.rstrip('/')}/app/#/playlist/{playlist_id}/show",
                    "tracks_count": len(all_song_ids),
                    "albums": completed_torrent_names,
                    "action": "updated"
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to update Navidrome playlist")
        else:
            playlist_id = await navidrome_client.create_playlist(playlist_title, all_song_ids)
            
            if playlist_id:
                return {
                    "success": True,
                    "message": f"Created Navidrome playlist '{playlist_title}'",
                    "playlist_id": playlist_id,
                    "playlist_name": playlist_title,
                    "playlist_url": f"{settings.navidrome_url.rstrip('/')}/app/#/playlist/{playlist_id}/show",
                    "tracks_count": len(all_song_ids),
                    "albums": completed_torrent_names,
                    "action": "created"
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to create Navidrome playlist")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error creating AoTM Navidrome playlist: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create Navidrome playlist: {str(e)}")


class ScanRequest(BaseModel):
    """Request model for Navidrome scan."""
    full: bool = False
    folder_paths: Optional[List[str]] = None


@app.post("/api/navidrome/scan")
async def trigger_navidrome_scan(request: ScanRequest = ScanRequest()):
    """Trigger a Navidrome library scan, optionally targeting specific folders."""
    if not settings.navidrome_url or not settings.navidrome_user:
        raise HTTPException(status_code=400, detail="Navidrome not configured.")
    
    lib_id = settings.navidrome_library_id
    targets = None
    if request.folder_paths:
        targets = [f"{lib_id}:{path}" for path in request.folder_paths]
    
    scan_type = "full" if request.full else "quick"
    target_desc = f" ({len(targets)} folders)" if targets else ""
    success = await navidrome_client.start_scan(full=request.full, targets=targets)
    if success:
        return {"success": True, "message": f"{scan_type.capitalize()} scan started{target_desc}"}
    else:
        raise HTTPException(status_code=500, detail="Failed to start Navidrome scan")


@app.get("/api/navidrome/scan/status")
async def get_navidrome_scan_status():
    """Get current Navidrome scan status."""
    if not settings.navidrome_url or not settings.navidrome_user:
        return {"scanning": False, "count": 0}
    
    status = await navidrome_client.get_scan_status()
    return status


@app.get("/api/downloads/status")
async def get_downloads_status():
    """Get status of downloads directly from qBittorrent by tag."""
    if not settings.qbit_url:
        return {
            "downloads": [],
            "all_completed": False,
            "total": 0,
            "completed": 0
        }
    
    # Get current playlist tag
    poll_title = await get_poll_title()
    playlist_tag = get_playlist_tag(poll_title)
    
    try:
        session_cookie = await get_qbit_session()
        async with httpx.AsyncClient(timeout=30.0, cookies={"SID": session_cookie}) as client:
            # Get torrents with current playlist tag
            torrents_response = await client.get(
                f"{settings.qbit_url}/api/v2/torrents/info",
                params={"tag": playlist_tag}
            )
            
            if torrents_response.status_code != 200:
                return {
                    "downloads": [],
                    "all_completed": False,
                    "total": 0,
                    "completed": 0
                }
            
            qbit_torrents = torrents_response.json()
            
            downloads = []
            for t in qbit_torrents:
                progress = t.get("progress", 0.0)
                state = t.get("state", "")
                save_path = t.get("save_path", "")
                torrent_name = t.get("name", "")
                
                # Construct full download path
                if save_path and torrent_name:
                    full_path = os.path.join(save_path, torrent_name).rstrip('/')
                else:
                    full_path = save_path
                
                # Map qBit state to our status
                if progress >= 1.0 or state in ["uploading", "pausedUP", "stoppedUP"]:
                    status = "completed"
                elif state in ["error", "missingFiles"]:
                    status = "error"
                else:
                    status = "downloading"
                
                downloads.append({
                    "hash": t.get("hash"),
                    "name": torrent_name,
                    "progress": progress,
                    "status": status,
                    "download_path": full_path,
                    "size": t.get("size", 0),
                    "state": state,
                })
            
            total = len(downloads)
            completed = sum(1 for d in downloads if d["status"] == "completed")
            all_completed = total > 0 and completed == total
            
            return {
                "downloads": downloads,
                "all_completed": all_completed,
                "total": total,
                "completed": completed
            }
            
    except Exception as e:
        logger.warning("Error fetching downloads from qBit: %s", e)
        return {
            "downloads": [],
            "all_completed": False,
            "total": 0,
            "completed": 0
        }


@app.get("/api/playlist/id")
async def get_playlist_id():
    """Get the saved playlist ID."""
    data = load_playlist_id()
    if not data:
        raise HTTPException(status_code=404, detail="No playlist ID saved yet")
    return data


@app.post("/api/playlist/create")
async def create_playlist(skip_scan: bool = False):
    """Create Navidrome playlist for completed downloads from qBittorrent."""
    if not settings.navidrome_url or not settings.navidrome_user:
        raise HTTPException(status_code=400, detail="Navidrome not configured. Set NAVIDROME_URL, NAVIDROME_USER, NAVIDROME_PASSWORD environment variables.")
    
    if not settings.qbit_url:
        raise HTTPException(status_code=400, detail="qBittorrent not configured.")
    
    # Get poll title and tag
    poll_title = await get_poll_title()
    playlist_tag = get_playlist_tag(poll_title)
    current_year = datetime.now().year
    playlist_title = f"{current_year} - {poll_title}" if poll_title else f"Orpheus Poll {current_year}"
    
    # Get completed downloads from qBittorrent with their file paths
    try:
        session_cookie = await get_qbit_session()
        async with httpx.AsyncClient(timeout=30.0, cookies={"SID": session_cookie}) as client:
            torrents_response = await client.get(
                f"{settings.qbit_url}/api/v2/torrents/info",
                params={"tag": playlist_tag}
            )
            
            if torrents_response.status_code != 200:
                raise HTTPException(status_code=500, detail="Failed to fetch torrents from qBittorrent")
            
            qbit_torrents = torrents_response.json()
            
            all_file_paths = []
            completed_torrent_names = []
            completed_folder_paths = []
            
            for t in qbit_torrents:
                progress = t.get("progress", 0.0)
                state = t.get("state", "")
                torrent_hash = t.get("hash", "")
                torrent_name = t.get("name", "")
                save_path = t.get("save_path", "").rstrip("/")
                
                if progress >= 1.0 or state in ["uploading", "pausedUP", "stoppedUP"]:
                    files_response = await client.get(
                        f"{settings.qbit_url}/api/v2/torrents/files",
                        params={"hash": torrent_hash}
                    )
                    
                    if files_response.status_code == 200:
                        files = files_response.json()
                        for f in files:
                            file_name = f.get("name", "")
                            if file_name.lower().endswith(('.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wav', '.aac')):
                                all_file_paths.append(file_name)
                        
                        if files:
                            completed_torrent_names.append(torrent_name)
                            if save_path and torrent_name:
                                completed_folder_paths.append(os.path.join(save_path, torrent_name))
                            logger.info("Found %d audio files in torrent: %s", 
                                       len([f for f in files if f.get("name", "").lower().endswith(('.flac', '.mp3', '.m4a', '.ogg', '.opus', '.wav', '.aac'))]),
                                       torrent_name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to qBittorrent: {str(e)}")
    
    if not completed_torrent_names:
        raise HTTPException(status_code=400, detail="No completed downloads found")
    
    logger.info("Found %d audio files from %d completed torrents", len(all_file_paths), len(completed_torrent_names))
    
    try:
        if not skip_scan:
            lib_id = app_settings.navidrome_library_id
            scan_targets = None
            if completed_folder_paths:
                music_root = app_settings.navidrome_music_folder.rstrip("/")
                if music_root:
                    navidrome_paths = [
                        f"{music_root}/{os.path.basename(p)}" for p in completed_folder_paths
                    ]
                else:
                    navidrome_paths = completed_folder_paths
                scan_targets = [f"{lib_id}:{p}" for p in navidrome_paths]
            logger.info("Triggering Navidrome targeted scan for %d folders: %s", len(completed_folder_paths), scan_targets)
            await navidrome_client.start_scan(targets=scan_targets)
            
            max_wait = 120
            waited = 0
            while waited < max_wait:
                await asyncio.sleep(2)
                waited += 2
                status = await navidrome_client.get_scan_status()
                if not status.get("scanning"):
                    logger.info("Scan completed after %ds", waited)
                    break
            else:
                logger.warning("Scan still running after %ds, continuing anyway...", max_wait)
        
        # Match poll albums against completed torrent names using clean metadata
        poll_albums = await get_poll_albums()
        downloaded_albums = _match_albums_to_torrents(poll_albums, completed_torrent_names)
        
        music_folder = app_settings.navidrome_music_folder
        songs = []
        if all_file_paths:
            logger.info("Searching Navidrome by path for %d files (music_folder=%r)", len(all_file_paths), music_folder)
            songs = await navidrome_client.find_songs_by_paths(all_file_paths, navidrome_music_folder=music_folder)
        
        if not songs and downloaded_albums:
            logger.warning("Path-based search found no songs, falling back to metadata search")
            songs = await navidrome_client.find_songs_by_albums(downloaded_albums)
        
        if not songs:
            raise HTTPException(
                status_code=404,
                detail=(
                    f"No tracks found in Navidrome for the {len(completed_torrent_names)} downloaded album(s). "
                    "Make sure the library scan completed and the files are indexed."
                )
            )
        
        all_song_ids = [song["id"] for song in songs]
        logger.info("Found %d songs in Navidrome matching the downloaded files", len(all_song_ids))
        
        # Step 3: Create or update playlist in Navidrome
        logger.info("Creating/updating playlist '%s' with %d tracks...", playlist_title, len(all_song_ids))
        
        existing_playlist = await navidrome_client.get_playlist_by_name(playlist_title)
        
        if existing_playlist:
            playlist_id = existing_playlist.get("id")
            success = await navidrome_client.update_playlist(playlist_id, all_song_ids)
            
            if success:
                # Save playlist ID to file
                save_playlist_id(playlist_id, playlist_title, settings.navidrome_url)
                
                return {
                    "success": True,
                    "message": f"Updated Navidrome playlist '{playlist_title}'",
                    "playlist_id": playlist_id,
                    "playlist_name": playlist_title,
                    "playlist_url": f"{settings.navidrome_url.rstrip('/')}/app/#/playlist/{playlist_id}/show",
                    "tracks_count": len(all_song_ids),
                    "albums": completed_torrent_names,
                    "action": "updated"
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to update Navidrome playlist")
        else:
            playlist_id = await navidrome_client.create_playlist(playlist_title, all_song_ids)
            
            if playlist_id:
                # Save playlist ID to file
                save_playlist_id(playlist_id, playlist_title, settings.navidrome_url)
                
                return {
                    "success": True,
                    "message": f"Created Navidrome playlist '{playlist_title}'",
                    "playlist_id": playlist_id,
                    "playlist_name": playlist_title,
                    "playlist_url": f"{settings.navidrome_url.rstrip('/')}/app/#/playlist/{playlist_id}/show",
                    "tracks_count": len(all_song_ids),
                    "albums": completed_torrent_names,
                    "action": "created"
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to create Navidrome playlist")
    
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Error creating Navidrome playlist: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create Navidrome playlist: {str(e)}")


# Serve static files (frontend)
frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.exists(frontend_path):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_path, "assets")), name="assets")
    
    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve the frontend application."""
        file_path = os.path.join(frontend_path, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_path, "index.html"))
