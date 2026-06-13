import { PollAlbum, CacheStatus, RefreshResponse, TorrentFormat, QBitStatus, BatchDownloadResponse, DownloadsStatus, QualityPreference, AoTMWinner, AoTMCacheStatus } from './types';

const API_BASE = '/api';

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new Error(error.detail || `HTTP error ${response.status}`);
  }
  return response.json();
}

export async function fetchPoll(): Promise<PollAlbum[]> {
  const response = await fetch(`${API_BASE}/poll`);
  return handleResponse<PollAlbum[]>(response);
}

export async function refreshPoll(): Promise<RefreshResponse> {
  const response = await fetch(`${API_BASE}/poll/refresh`, {
    method: 'POST',
  });
  return handleResponse<RefreshResponse>(response);
}

export async function searchAlbum(albumId: number): Promise<{ success: boolean; group_id: number; formats: TorrentFormat[] }> {
  const response = await fetch(`${API_BASE}/album/${albumId}/search`, {
    method: 'POST',
  });
  return handleResponse(response);
}

export async function getAlbumFormats(albumId: number): Promise<TorrentFormat[]> {
  const response = await fetch(`${API_BASE}/album/${albumId}/formats`);
  return handleResponse<TorrentFormat[]>(response);
}

export async function downloadTorrent(torrentId: number): Promise<Blob> {
  const response = await fetch(`${API_BASE}/torrent/download`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ torrent_id: torrentId }),
  });
  
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Download failed' }));
    throw new Error(error.detail || `Download failed: ${response.status}`);
  }
  
  return response.blob();
}

export async function getQBitStatus(): Promise<QBitStatus> {
  const response = await fetch(`${API_BASE}/qbit/status`);
  return handleResponse<QBitStatus>(response);
}

export async function batchDownloadToQBit(torrents: Array<{torrent_id: number, album_id: number}>): Promise<BatchDownloadResponse> {
  const response = await fetch(`${API_BASE}/torrent/batch-download`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ torrents }),
  });
  return handleResponse<BatchDownloadResponse>(response);
}

export async function getDownloadsStatus(): Promise<DownloadsStatus> {
  const response = await fetch(`${API_BASE}/downloads/status`);
  return handleResponse<DownloadsStatus>(response);
}

export async function clearDownloads(): Promise<{success: boolean, message: string}> {
  const response = await fetch(`${API_BASE}/downloads/clear`, {
    method: 'POST',
  });
  return handleResponse(response);
}

export interface CreatePlaylistResponse {
  success: boolean;
  message: string;
  playlist_name: string;
  tracks_count: number;
  albums: string[];
  action: 'created' | 'updated';
}

export async function createPlaylist(): Promise<CreatePlaylistResponse> {
  const response = await fetch(`${API_BASE}/playlist/create`, {
    method: 'POST',
  });
  return handleResponse<CreatePlaylistResponse>(response);
}

export async function getCacheStatus(): Promise<CacheStatus> {
  const response = await fetch(`${API_BASE}/cache/status`);
  return handleResponse<CacheStatus>(response);
}

export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

export function formatTimeAgo(date: string): string {
  const seconds = Math.floor((Date.now() - new Date(date).getTime()) / 1000);
  
  const intervals: [number, string][] = [
    [31536000, 'year'],
    [2592000, 'month'],
    [86400, 'day'],
    [3600, 'hour'],
    [60, 'minute'],
    [1, 'second'],
  ];
  
  for (const [secs, label] of intervals) {
    const interval = Math.floor(seconds / secs);
    if (interval >= 1) {
      return `${interval} ${label}${interval > 1 ? 's' : ''} ago`;
    }
  }
  
  return 'just now';
}

/**
 * Select the best matching torrent for a given quality preference
 */
export function selectTorrentForQuality(formats: TorrentFormat[], preference: QualityPreference): TorrentFormat | null {
  if (!formats || formats.length === 0) return null;
  
  // Sort by preference matching
  const sorted = [...formats].sort((a, b) => {
    const scoreA = getQualityScore(a, preference);
    const scoreB = getQualityScore(b, preference);
    if (scoreA !== scoreB) return scoreB - scoreA;
    // Tie-breaker: more seeders
    return b.seeders - a.seeders;
  });
  
  return sorted[0];
}

function getQualityScore(format: TorrentFormat, preference: QualityPreference): number {
  const fmt = format.format?.toUpperCase() || '';
  const enc = format.encoding?.toUpperCase() || '';
  const is24bit = enc.includes('24BIT') || enc.includes('24-BIT') || enc.includes('24 BIT');
  
  switch (preference) {
    case 'flac_24bit':
      if (fmt === 'FLAC' && is24bit) return 100;
      if (fmt === 'FLAC') return 50; // Fallback to regular FLAC
      return 0;
    case 'flac':
      if (fmt === 'FLAC' && !is24bit) return 100; // Prefer 16-bit
      if (fmt === 'FLAC' && is24bit) return 90; // Accept 24-bit
      return 0;
    case 'mp3_320':
      if (fmt === 'MP3' && enc === '320') return 100;
      if (fmt === 'MP3' && enc.includes('V0')) return 80;
      if (fmt === 'MP3') return 60;
      return 0;
    case 'mp3_v0':
      if (fmt === 'MP3' && enc.includes('V0')) return 100;
      if (fmt === 'MP3' && enc === '320') return 80;
      if (fmt === 'MP3') return 60;
      return 0;
    default:
      return 0;
  }
}

// ==================== AoTM Winners API ====================

export async function fetchAoTMWinners(): Promise<AoTMWinner[]> {
  const response = await fetch(`${API_BASE}/aotm/winners`);
  return handleResponse<AoTMWinner[]>(response);
}

export async function refreshAoTMWinners(maxPages: number = 10): Promise<{ success: boolean; message: string; winners_count: number }> {
  const response = await fetch(`${API_BASE}/aotm/refresh`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ max_pages: maxPages }),
  });
  return handleResponse(response);
}

export async function getAoTMCacheStatus(): Promise<AoTMCacheStatus> {
  const response = await fetch(`${API_BASE}/aotm/cache-status`);
  return handleResponse<AoTMCacheStatus>(response);
}

export async function searchAoTMWinner(threadId: number): Promise<{ success: boolean; group_id: number; formats: TorrentFormat[] }> {
  const response = await fetch(`${API_BASE}/aotm/winner/${threadId}/search`, {
    method: 'POST',
  });
  return handleResponse(response);
}

export async function addWinnersToPoll(threadIds: number[]): Promise<{ success: boolean; message: string; added_count: number }> {
  const response = await fetch(`${API_BASE}/aotm/add-to-poll`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ thread_ids: threadIds }),
  });
  return handleResponse(response);
}

export async function batchDownloadAoTMWinners(
  threadIds: number[], 
  qualityPreference: QualityPreference
): Promise<BatchDownloadResponse> {
  const response = await fetch(`${API_BASE}/aotm/batch-download`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ thread_ids: threadIds, quality_preference: qualityPreference }),
  });
  return handleResponse<BatchDownloadResponse>(response);
}

export async function getAoTMDownloadsStatus(): Promise<DownloadsStatus> {
  const response = await fetch(`${API_BASE}/aotm/downloads/status`);
  return handleResponse<DownloadsStatus>(response);
}

export async function createAoTMPlaylist(): Promise<CreatePlaylistResponse> {
  const response = await fetch(`${API_BASE}/aotm/playlist/create`, {
    method: 'POST',
  });
  return handleResponse<CreatePlaylistResponse>(response);
}

export async function startNavidromeScan(folderPaths?: string[]): Promise<{ success: boolean; message: string }> {
  const body: Record<string, unknown> = {};
  if (folderPaths && folderPaths.length > 0) {
    body.folder_paths = folderPaths;
  }
  const response = await fetch(`${API_BASE}/navidrome/scan`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return handleResponse(response);
}

export async function getNavidromeScanStatus(): Promise<{ scanning: boolean; count: number }> {
  const response = await fetch(`${API_BASE}/navidrome/scan/status`);
  return handleResponse(response);
}

export async function createPlaylistSkipScan(): Promise<CreatePlaylistResponse> {
  const response = await fetch(`${API_BASE}/playlist/create?skip_scan=true`, {
    method: 'POST',
  });
  return handleResponse<CreatePlaylistResponse>(response);
}

export async function createAoTMPlaylistSkipScan(): Promise<CreatePlaylistResponse> {
  const response = await fetch(`${API_BASE}/aotm/playlist/create?skip_scan=true`, {
    method: 'POST',
  });
  return handleResponse<CreatePlaylistResponse>(response);
}

export async function selectiveDownloadPoll(
  albumIds: number[],
  qualityPreference: QualityPreference
): Promise<BatchDownloadResponse> {
  const response = await fetch(`${API_BASE}/poll/selective-download`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ album_ids: albumIds, quality_preference: qualityPreference }),
  });
  return handleResponse<BatchDownloadResponse>(response);
}
