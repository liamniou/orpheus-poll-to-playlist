export interface TorrentFormat {
  id: number;
  quality: string;
  format: string;
  encoding: string;
  media: string;
  size: number;
  seeders: number;
  leechers: number;
  snatched: number;
  has_log: boolean;
  log_score: number | null;
}

export interface PollAlbum {
  id: number;
  artist: string;
  album: string;
  year: string | null;
  poll_position: number;
  votes: number | null;
  orpheus_group_id: number | null;
  available_formats: TorrentFormat[] | null;
}

export interface CacheStatus {
  last_updated: string | null;
  is_stale: boolean;
  albums_count: number;
  linked_count: number;
  cache_ttl_minutes: number;
}

export interface RefreshResponse {
  success: boolean;
  message: string;
  albums_count: number;
}

export interface QBitStatus {
  configured: boolean;
  connected: boolean;
  url: string | null;
}

export interface BatchDownloadResult {
  torrent_id: number;
  success: boolean;
  error?: string;
}

export interface BatchDownloadResponse {
  success: boolean;
  message: string;
  results: BatchDownloadResult[];
}

export interface TorrentDownload {
  hash: string;
  name: string;
  progress: number;
  status: 'downloading' | 'completed' | 'error';
  download_path: string;
  size: number;
  state: string;
}

export interface DownloadsStatus {
  downloads: TorrentDownload[];
  all_completed: boolean;
  total: number;
  completed: number;
}

export type QualityPreference = 'flac_24bit' | 'flac' | 'mp3_320' | 'mp3_v0';

export interface AoTMWinner {
  id: number;
  artist: string;
  album: string;
  year: string | null;
  thread_id: number;
  thread_title: string;
  orpheus_group_id: number | null;
}

export interface AoTMCacheStatus {
  last_updated: string | null;
  is_stale: boolean;
  winners_count: number;
  linked_count: number;
  cache_ttl_minutes: number;
}
