import { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Toaster, toast } from 'react-hot-toast';
import { PollAlbum, CacheStatus, TorrentFormat, QBitStatus, QualityPreference, DownloadsStatus, AoTMWinner, AoTMCacheStatus } from './types';
import { fetchPoll, refreshPoll, searchAlbum, getCacheStatus, getQBitStatus, getDownloadsStatus, selectTorrentForQuality, formatBytes, formatTimeAgo, fetchAoTMWinners, refreshAoTMWinners, getAoTMCacheStatus, batchDownloadAoTMWinners, getAoTMDownloadsStatus, selectiveDownloadPoll, startNavidromeScan, getNavidromeScanStatus, createPlaylistSkipScan, createAoTMPlaylistSkipScan } from './api';
import clsx from 'clsx';

// Icons
const RefreshIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" />
  </svg>
);

const DownloadIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 12 12 16.5m0 0L7.5 12m4.5 4.5V3" />
  </svg>
);

const ChevronDownIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m19.5 8.25-7.5 7.5-7.5-7.5" />
  </svg>
);

const SearchIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m21 21-5.197-5.197m0 0A7.5 7.5 0 1 0 5.196 5.196a7.5 7.5 0 0 0 10.607 10.607Z" />
  </svg>
);

const MusicNoteIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="m9 9 10.5-3m0 6.553v3.75a2.25 2.25 0 0 1-1.632 2.163l-1.32.377a1.803 1.803 0 1 1-.99-3.467l2.31-.66a2.25 2.25 0 0 0 1.632-2.163Zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 0 1-1.632 2.163l-1.32.377a1.803 1.803 0 0 1-.99-3.467l2.31-.66A2.25 2.25 0 0 0 9 15.553Z" />
  </svg>
);

const CheckCircleIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" />
  </svg>
);

const ServerIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M5.25 14.25h13.5m-13.5 0a3 3 0 0 1-3-3m3 3a3 3 0 1 0 0 6h13.5a3 3 0 1 0 0-6m-16.5-3a3 3 0 0 1 3-3h13.5a3 3 0 0 1 3 3m-19.5 0a4.5 4.5 0 0 1 .9-2.7L5.737 5.1a3.375 3.375 0 0 1 2.7-1.35h7.126c1.062 0 2.062.5 2.7 1.35l2.587 3.45a4.5 4.5 0 0 1 .9 2.7m0 0a3 3 0 0 1-3 3m0 3h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Zm-3 6h.008v.008h-.008v-.008Zm0-6h.008v.008h-.008v-.008Z" />
  </svg>
);

const PlaylistIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25M9 9v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 19.553z" />
  </svg>
);

const TrophyIcon = ({ className }: { className?: string }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" d="M16.5 18.75h-9m9 0a3 3 0 0 1 3 3h-15a3 3 0 0 1 3-3m9 0v-3.375c0-.621-.503-1.125-1.125-1.125h-.871M7.5 18.75v-3.375c0-.621.504-1.125 1.125-1.125h.872m5.007 0H9.497m5.007 0a7.454 7.454 0 0 1-.982-3.172M9.497 14.25a7.454 7.454 0 0 0 .981-3.172M5.25 4.236c-.982.143-1.954.317-2.916.52A6.003 6.003 0 0 0 7.73 9.728M5.25 4.236V4.5c0 2.108.966 3.99 2.48 5.228M5.25 4.236V2.721C7.456 2.41 9.71 2.25 12 2.25c2.291 0 4.545.16 6.75.47v1.516M7.73 9.728a6.726 6.726 0 0 0 2.748 1.35m8.272-6.842V4.5c0 2.108-.966 3.99-2.48 5.228m2.48-5.492a46.32 46.32 0 0 1 2.916.52 6.003 6.003 0 0 1-5.395 4.972m0 0a6.726 6.726 0 0 1-2.749 1.35m0 0a6.772 6.772 0 0 1-2.748 0" />
  </svg>
);

type ScanPhase = 'idle' | 'scanning' | 'creating';

interface ScanProgress {
  phase: ScanPhase;
  count: number;
  label: string;
}

function ScanProgressBar({ progress }: { progress: ScanProgress }) {
  if (progress.phase === 'idle') return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-md mx-4 p-6 rounded-2xl bg-surface-900 border border-surface-700/50 shadow-2xl">
        <div className="flex items-center gap-3 mb-4">
          <div className={clsx(
            "w-10 h-10 rounded-xl flex items-center justify-center",
            progress.phase === 'scanning'
              ? "bg-accent-500/20"
              : "bg-success-500/20"
          )}>
            {progress.phase === 'scanning' ? (
              <RefreshIcon className="w-5 h-5 text-accent-400 animate-spin" />
            ) : (
              <PlaylistIcon className="w-5 h-5 text-success-400 animate-pulse" />
            )}
          </div>
          <div>
            <h3 className="text-sm font-semibold text-white">{progress.label}</h3>
            {progress.phase === 'scanning' && progress.count > 0 && (
              <p className="text-xs text-surface-400">{progress.count} files scanned</p>
            )}
          </div>
        </div>
        <div className="w-full h-1.5 bg-surface-800/50 rounded-full overflow-hidden">
          <div className={clsx(
            "h-full rounded-full transition-all duration-300",
            progress.phase === 'scanning'
              ? "bg-gradient-to-r from-accent-600 to-accent-400 animate-scan-pulse"
              : "bg-gradient-to-r from-success-600 to-success-400 animate-scan-pulse"
          )} style={{ width: progress.phase === 'scanning' ? '60%' : '90%' }} />
        </div>
      </div>
    </div>
  );
}

const QUALITY_OPTIONS: { value: QualityPreference; label: string; description: string }[] = [
  { value: 'flac_24bit', label: '24-Bit FLAC', description: 'Hi-res lossless audio' },
  { value: 'flac', label: 'FLAC', description: 'Lossless CD quality' },
  { value: 'mp3_320', label: 'MP3 320 kbps', description: 'High quality lossy' },
  { value: 'mp3_v0', label: 'MP3 V0', description: 'Variable bitrate (~245 kbps)' },
];

// Quality dropdown component
function QualityDropdown({ 
  value, 
  onChange,
  disabled 
}: { 
  value: QualityPreference;
  onChange: (value: QualityPreference) => void;
  disabled?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(false);
  const selected = QUALITY_OPTIONS.find(o => o.value === value);

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        disabled={disabled}
        className={clsx(
          "flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-200",
          "bg-surface-800/60 border border-surface-700/50",
          "hover:bg-surface-700/60 hover:border-accent-500/30",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <span className="text-white">{selected?.label}</span>
        <ChevronDownIcon className={clsx("w-4 h-4 text-surface-400 transition-transform", isOpen && "rotate-180")} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setIsOpen(false)} />
          <div className="absolute z-50 mt-2 w-64 right-0 rounded-xl bg-surface-900/95 backdrop-blur-xl border border-surface-700/50 shadow-2xl overflow-hidden animate-scale-in">
            {QUALITY_OPTIONS.map((option) => (
              <button
                key={option.value}
                onClick={() => { onChange(option.value); setIsOpen(false); }}
                className={clsx(
                  "w-full px-4 py-3 text-left transition-all duration-150",
                  "hover:bg-surface-800/60",
                  "border-b border-surface-800/50 last:border-b-0",
                  option.value === value && "bg-accent-500/10"
                )}
              >
                <div className="font-medium text-white">{option.label}</div>
                <div className="text-xs text-surface-500">{option.description}</div>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

// Album row component (horizontal card) with checkbox
function AlbumRow({ 
  album, 
  onSearch, 
  isSearching,
  selectedTorrent,
  isSelected,
  onToggle,
}: { 
  album: PollAlbum;
  onSearch: (albumId: number) => void;
  isSearching: boolean;
  selectedTorrent: TorrentFormat | null;
  isSelected: boolean;
  onToggle: (albumId: number) => void;
}) {
  const hasFormats = album.available_formats && album.available_formats.length > 0;
  const isLinked = album.orpheus_group_id !== null;

  const getFormatClass = (format: string) => {
    if (format === 'FLAC') return 'format-flac';
    if (format === 'MP3') return 'format-mp3';
    return 'format-other';
  };

  return (
    <div 
      className={clsx(
        "group relative rounded-xl transition-all duration-300 cursor-pointer",
        "bg-gradient-to-r from-surface-900/80 to-surface-950/80",
        "border",
        isSelected
          ? "border-accent-500/50 bg-accent-500/5"
          : "border-surface-800/50 hover:border-accent-500/30 hover:shadow-lg hover:shadow-accent-500/5"
      )}
      onClick={() => onToggle(album.id)}
    >
      <div className="flex items-center gap-4 p-4">
        {/* Checkbox */}
        <div
          className={clsx(
            "w-5 h-5 rounded border-2 flex items-center justify-center transition-all shrink-0",
            isSelected
              ? "bg-accent-500 border-accent-500"
              : "border-surface-600 group-hover:border-surface-500"
          )}
          onClick={(e) => { e.stopPropagation(); onToggle(album.id); }}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
          )}
        </div>

        {/* Position badge */}
        <div className={clsx(
          "w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold shrink-0",
          album.poll_position === 1 && "bg-gradient-to-br from-yellow-400 to-amber-600 text-black",
          album.poll_position === 2 && "bg-gradient-to-br from-gray-300 to-gray-500 text-black",
          album.poll_position === 3 && "bg-gradient-to-br from-amber-600 to-amber-800 text-white",
          album.poll_position > 3 && "bg-surface-800/80 text-surface-400"
        )}>
          {album.poll_position}
        </div>

        {/* Album info */}
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-semibold text-white truncate group-hover:text-accent-400 transition-colors">
            {album.artist} — {album.album}
          </h3>
          <div className="flex items-center gap-3 mt-1">
            {album.year && <span className="text-xs text-surface-500">({album.year})</span>}
            {album.votes !== null && (
              <span className="text-xs text-surface-400">{album.votes} votes</span>
            )}
          </div>
        </div>

        {/* Status / Format info */}
        <div className="flex items-center gap-4 shrink-0">
          {!isLinked ? (
            <button
              onClick={(e) => { e.stopPropagation(); onSearch(album.id); }}
              disabled={isSearching}
              className={clsx(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium",
                "bg-accent-500/20 text-accent-400 border border-accent-500/30",
                "hover:bg-accent-500/30",
                "transition-all duration-200",
                isSearching && "opacity-50 cursor-wait"
              )}
            >
              {isSearching ? (
                <RefreshIcon className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <SearchIcon className="w-3.5 h-3.5" />
              )}
              {isSearching ? 'Searching...' : 'Find'}
            </button>
          ) : hasFormats && selectedTorrent ? (
            <div className="flex items-center gap-3">
              <span className={clsx("px-2 py-0.5 rounded text-xs font-bold text-white", getFormatClass(selectedTorrent.format))}>
                {selectedTorrent.format}
              </span>
              <span className="text-xs text-surface-400">{selectedTorrent.encoding}</span>
              <span className="text-xs text-surface-500">{selectedTorrent.media}</span>
              <span className="text-xs text-success-400">{selectedTorrent.seeders} ↑</span>
              <span className="text-xs text-surface-500">{formatBytes(selectedTorrent.size)}</span>
            </div>
          ) : hasFormats ? (
            <span className="text-xs text-warning-400">No match for quality</span>
          ) : isLinked ? (
            <span className="text-xs text-surface-500 italic">No torrents</span>
          ) : null}

          {/* Linked indicator */}
          {isLinked && (
            <CheckCircleIcon className="w-5 h-5 text-success-400" />
          )}
        </div>
      </div>
    </div>
  );
}

// Header component
function Header({ 
  onRefresh, 
  isRefreshing,
  cacheStatus,
  qbitStatus,
}: { 
  onRefresh: () => void;
  isRefreshing: boolean;
  cacheStatus: CacheStatus | null;
  qbitStatus: QBitStatus | null;
}) {
  return (
    <header className="relative overflow-hidden">
      {/* Background effects */}
      <div className="absolute inset-0 bg-gradient-to-b from-accent-500/10 via-transparent to-transparent" />
      <div className="absolute inset-0 bg-grid opacity-50" />
      
      <div className="relative max-w-4xl mx-auto px-6 py-8">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          {/* Title */}
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent-500 to-brand-500 flex items-center justify-center glow-accent">
              <MusicNoteIcon className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-2xl font-bold">
                <span className="gradient-text">Orpheus</span>
                <span className="text-white"> Poll</span>
              </h1>
              <p className="text-xs text-surface-500">Download poll albums to qBittorrent</p>
            </div>
          </div>

          {/* Actions & Status */}
          <div className="flex items-center gap-4">
            {/* qBit status */}
            {qbitStatus && (
              <div className={clsx(
                "flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs",
                qbitStatus.connected ? "bg-success-500/10 text-success-400" : "bg-warning-500/10 text-warning-400"
              )}>
                <ServerIcon className="w-4 h-4" />
                <span>{qbitStatus.connected ? 'qBit Connected' : 'qBit Disconnected'}</span>
              </div>
            )}

            <button
              onClick={onRefresh}
              disabled={isRefreshing}
              className={clsx(
                "flex items-center gap-2 px-4 py-2 rounded-xl",
                "bg-gradient-to-r from-accent-500 to-brand-500",
                "text-white font-semibold text-sm",
                "shadow-lg shadow-accent-500/25",
                "hover:shadow-xl hover:shadow-accent-500/30",
                "transition-all duration-300",
                isRefreshing && "opacity-70 cursor-wait"
              )}
            >
              <RefreshIcon className={clsx("w-4 h-4", isRefreshing && "animate-spin")} />
              {isRefreshing ? 'Refreshing...' : 'Refresh'}
            </button>
          </div>
        </div>

        {cacheStatus && cacheStatus.last_updated && (
          <div className="mt-3 text-xs text-surface-500 flex items-center gap-4">
            <span>Updated {formatTimeAgo(cacheStatus.last_updated)}</span>
            <span className="flex items-center gap-1">
              <span className={clsx("w-1.5 h-1.5 rounded-full", cacheStatus.is_stale ? "bg-warning-500" : "bg-success-500")} />
              {cacheStatus.albums_count} albums • {cacheStatus.linked_count} linked
            </span>
          </div>
        )}
      </div>
    </header>
  );
}

// Empty state component
function EmptyState({ onRefresh }: { onRefresh: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="w-16 h-16 rounded-2xl bg-surface-800/50 flex items-center justify-center mb-4">
        <MusicNoteIcon className="w-8 h-8 text-surface-500" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">No poll data yet</h3>
      <p className="text-surface-400 text-sm mb-4 max-w-md">
        Click refresh to fetch the latest poll from Orpheus Network.
      </p>
      <button
        onClick={onRefresh}
        className={clsx(
          "flex items-center gap-2 px-5 py-2.5 rounded-xl",
          "bg-gradient-to-r from-accent-500 to-brand-500",
          "text-white font-semibold text-sm",
          "shadow-lg shadow-accent-500/25",
          "hover:shadow-xl hover:shadow-accent-500/30",
          "transition-all duration-300"
        )}
      >
        <RefreshIcon className="w-4 h-4" />
        Fetch Poll Data
      </button>
    </div>
  );
}

// Loading skeleton
function LoadingSkeleton() {
  return (
    <div className="space-y-3">
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="rounded-xl bg-surface-900/60 border border-surface-800/50 p-4 shimmer">
          <div className="flex items-center gap-4">
            <div className="w-10 h-10 bg-surface-800/50 rounded-lg" />
            <div className="flex-1">
              <div className="h-5 bg-surface-800/50 rounded-lg w-1/2 mb-2" />
              <div className="h-3 bg-surface-800/50 rounded-lg w-1/4" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// AoTM Winner row component
function AoTMWinnerRow({
  winner,
  isSelected,
  onToggle,
}: {
  winner: AoTMWinner;
  isSelected: boolean;
  onToggle: (threadId: number) => void;
}) {
  return (
    <div
      className={clsx(
        "group relative rounded-lg transition-all duration-200 cursor-pointer",
        "bg-surface-900/60 border",
        isSelected
          ? "border-amber-500/50 bg-amber-500/5"
          : "border-surface-800/50 hover:border-surface-700/50"
      )}
      onClick={() => onToggle(winner.thread_id)}
    >
      <div className="flex items-center gap-3 p-3">
        {/* Checkbox */}
        <div
          className={clsx(
            "w-5 h-5 rounded border-2 flex items-center justify-center transition-all shrink-0",
            isSelected
              ? "bg-amber-500 border-amber-500"
              : "border-surface-600 group-hover:border-surface-500"
          )}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-black" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="m4.5 12.75 6 6 9-13.5" />
            </svg>
          )}
        </div>

        {/* Trophy icon */}
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500/20 to-amber-600/10 flex items-center justify-center shrink-0">
          <TrophyIcon className="w-4 h-4 text-amber-400" />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <h4 className="text-sm font-medium text-white truncate">
            {winner.artist} — {winner.album}
          </h4>
          <p className="text-xs text-surface-500 truncate">{winner.thread_title}</p>
        </div>

        {/* Linked indicator */}
        {winner.orpheus_group_id && (
          <CheckCircleIcon className="w-4 h-4 text-success-400 shrink-0" />
        )}
      </div>
    </div>
  );
}

// AoTM Winners Panel component
function AoTMWinnersPanel({
  winners,
  cacheStatus,
  selectedWinners,
  onToggleWinner,
  onSelectAll,
  onDeselectAll,
  onRefresh,
  onDownload,
  onCreatePlaylist,
  isRefreshing,
  isDownloading,
  isCreatingPlaylist,
  downloadsStatus,
  qualityPreference,
  onQualityChange,
  qbitConnected,
}: {
  winners: AoTMWinner[];
  cacheStatus: AoTMCacheStatus | null;
  selectedWinners: Set<number>;
  onToggleWinner: (threadId: number) => void;
  onSelectAll: () => void;
  onDeselectAll: () => void;
  onRefresh: () => void;
  onDownload: () => void;
  onCreatePlaylist: () => void;
  isRefreshing: boolean;
  isDownloading: boolean;
  isCreatingPlaylist: boolean;
  downloadsStatus: DownloadsStatus | null;
  qualityPreference: QualityPreference;
  onQualityChange: (quality: QualityPreference) => void;
  qbitConnected: boolean;
}) {
  const [isExpanded, setIsExpanded] = useState(false);

  return (
    <div className="rounded-xl bg-surface-900/30 border border-amber-500/20 overflow-hidden mb-4">
      {/* Header - always visible */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full flex items-center justify-between p-4 hover:bg-surface-800/30 transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-amber-500/20 to-amber-600/10 flex items-center justify-center">
            <TrophyIcon className="w-5 h-5 text-amber-400" />
          </div>
          <div className="text-left">
            <h3 className="text-sm font-semibold text-white">Previous AoTM Winners</h3>
            <p className="text-xs text-surface-500">
              {winners.length > 0
                ? `${winners.length} winners available`
                : "Load previous winners from forum"}
            </p>
          </div>
        </div>
        <ChevronDownIcon
          className={clsx(
            "w-5 h-5 text-surface-400 transition-transform duration-200",
            isExpanded && "rotate-180"
          )}
        />
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="border-t border-surface-800/50">
          {/* Top Controls - Load & Select */}
          <div className="flex items-center justify-between gap-3 p-3 bg-surface-900/50">
            <div className="flex items-center gap-2">
              <button
                onClick={onRefresh}
                disabled={isRefreshing}
                className={clsx(
                  "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
                  "bg-surface-800/60 text-surface-300 border border-surface-700/50",
                  "hover:bg-surface-700/60 hover:text-white",
                  "transition-all duration-200",
                  isRefreshing && "opacity-50 cursor-wait"
                )}
              >
                <RefreshIcon className={clsx("w-3.5 h-3.5", isRefreshing && "animate-spin")} />
                {isRefreshing ? "Loading..." : "Load Winners"}
              </button>

              {winners.length > 0 && (
                <>
                  <button
                    onClick={onSelectAll}
                    className="px-2 py-1.5 rounded-lg text-xs text-surface-400 hover:text-white hover:bg-surface-800/60 transition-all"
                  >
                    Select All
                  </button>
                  <button
                    onClick={onDeselectAll}
                    className="px-2 py-1.5 rounded-lg text-xs text-surface-400 hover:text-white hover:bg-surface-800/60 transition-all"
                  >
                    Clear
                  </button>
                </>
              )}
            </div>

            {winners.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-surface-500">Quality:</span>
                <QualityDropdown
                  value={qualityPreference}
                  onChange={onQualityChange}
                  disabled={isDownloading}
                />
              </div>
            )}
          </div>

          {/* Action buttons */}
          {selectedWinners.size > 0 && (
            <div className="flex items-center justify-between gap-3 px-3 pb-3 bg-surface-900/50">
              <div className="text-xs text-amber-400">
                {selectedWinners.size} winner{selectedWinners.size !== 1 ? 's' : ''} selected
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={onDownload}
                  disabled={isDownloading || !qbitConnected}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
                    "bg-gradient-to-r from-amber-500 to-amber-600",
                    "text-black shadow-lg shadow-amber-500/20",
                    "hover:shadow-xl hover:shadow-amber-500/30",
                    "transition-all duration-200",
                    (isDownloading || !qbitConnected) && "opacity-50 cursor-not-allowed"
                  )}
                >
                  {isDownloading ? (
                    <RefreshIcon className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <DownloadIcon className="w-3.5 h-3.5" />
                  )}
                  Send to qBit
                </button>

                <button
                  onClick={onCreatePlaylist}
                  disabled={!downloadsStatus?.all_completed || isCreatingPlaylist}
                  className={clsx(
                    "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium",
                    "bg-gradient-to-r from-success-600 to-success-500",
                    "text-white shadow-lg shadow-success-500/20",
                    "hover:shadow-xl hover:shadow-success-500/30",
                    "transition-all duration-200",
                    (!downloadsStatus?.all_completed || isCreatingPlaylist) && "opacity-50 cursor-not-allowed"
                  )}
                >
                  {isCreatingPlaylist ? (
                    <RefreshIcon className="w-3.5 h-3.5 animate-spin" />
                  ) : (
                    <PlaylistIcon className="w-3.5 h-3.5" />
                  )}
                  AoTM Playlist
                </button>
              </div>
            </div>
          )}

          {/* Download progress for AoTM */}
          {downloadsStatus && downloadsStatus.total > 0 && (
            <div className="px-3 pb-3 bg-surface-900/50">
              <div className="p-2 rounded-lg bg-surface-950/50 border border-surface-800/30">
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-surface-400">
                    Downloads: {downloadsStatus.completed}/{downloadsStatus.total}
                  </span>
                  {downloadsStatus.all_completed ? (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-success-500/20 text-success-400 font-medium">
                      Complete!
                    </span>
                  ) : (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 font-medium">
                      In Progress
                    </span>
                  )}
                </div>
                <div className="w-full h-1.5 bg-surface-800/50 rounded-full overflow-hidden">
                  <div 
                    className={clsx(
                      "h-full transition-all duration-500 rounded-full",
                      downloadsStatus.all_completed 
                        ? "bg-gradient-to-r from-success-600 to-success-400" 
                        : "bg-gradient-to-r from-amber-600 to-amber-400"
                    )}
                    style={{ width: `${(downloadsStatus.completed / downloadsStatus.total) * 100}%` }}
                  />
                </div>
              </div>
            </div>
          )}

          {/* Cache status */}
          {cacheStatus && cacheStatus.last_updated && (
            <div className="px-3 py-2 text-xs text-surface-500 bg-surface-950/50 border-t border-surface-800/30">
              Last updated: {formatTimeAgo(cacheStatus.last_updated)}
            </div>
          )}

          {/* Winners list */}
          {winners.length > 0 ? (
            <div className="p-3 space-y-2 max-h-80 overflow-y-auto">
              {winners.map((winner) => (
                <AoTMWinnerRow
                  key={winner.thread_id}
                  winner={winner}
                  isSelected={selectedWinners.has(winner.thread_id)}
                  onToggle={onToggleWinner}
                />
              ))}
            </div>
          ) : (
            <div className="p-6 text-center text-surface-500 text-sm">
              Click "Load Winners" to fetch previous AoTM winners from the forum
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Main App component
function App() {
  const [albums, setAlbums] = useState<PollAlbum[]>([]);
  const [cacheStatus, setCacheStatus] = useState<CacheStatus | null>(null);
  const [qbitStatus, setQBitStatus] = useState<QBitStatus | null>(null);
  const [downloadsStatus, setDownloadsStatus] = useState<DownloadsStatus | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [isCreatingPlaylist, setIsCreatingPlaylist] = useState(false);
  const [searchingAlbums, setSearchingAlbums] = useState<Set<number>>(new Set());
  const [qualityPreference, setQualityPreference] = useState<QualityPreference>('flac');
  const downloadStatusInterval = useRef<number | null>(null);

  // Selected poll albums state
  const [selectedAlbums, setSelectedAlbums] = useState<Set<number>>(new Set());

  // AoTM Winners state
  const [aotmWinners, setAotmWinners] = useState<AoTMWinner[]>([]);
  const [aotmCacheStatus, setAotmCacheStatus] = useState<AoTMCacheStatus | null>(null);
  const [selectedWinners, setSelectedWinners] = useState<Set<number>>(new Set());
  const [isRefreshingAotm, setIsRefreshingAotm] = useState(false);
  const [isDownloadingAotm, setIsDownloadingAotm] = useState(false);
  const [isCreatingAotmPlaylist, setIsCreatingAotmPlaylist] = useState(false);
  const [aotmDownloadsStatus, setAotmDownloadsStatus] = useState<DownloadsStatus | null>(null);
  const [aotmQualityPreference, setAotmQualityPreference] = useState<QualityPreference>('flac');
  const [scanProgress, setScanProgress] = useState<ScanProgress>({ phase: 'idle', count: 0, label: '' });

  const loadData = useCallback(async () => {
    try {
      const [pollData, statusData, qbitData, downloadData, aotmData, aotmStatus, aotmDownloadData] = await Promise.all([
        fetchPoll(),
        getCacheStatus(),
        getQBitStatus(),
        getDownloadsStatus(),
        fetchAoTMWinners().catch(() => []),
        getAoTMCacheStatus().catch(() => null),
        getAoTMDownloadsStatus().catch(() => null)
      ]);
      setAlbums(pollData);
      setCacheStatus(statusData);
      setQBitStatus(qbitData);
      setDownloadsStatus(downloadData);
      setAotmWinners(aotmData);
      setAotmCacheStatus(aotmStatus);
      setAotmDownloadsStatus(aotmDownloadData);
      
      // Auto-select all albums that have torrents available
      if (pollData.length > 0 && selectedAlbums.size === 0) {
        const albumsWithTorrents = pollData.filter(a => a.orpheus_group_id !== null);
        setSelectedAlbums(new Set(albumsWithTorrents.map(a => a.id)));
      }
    } catch (error) {
      console.error('Error loading data:', error);
      toast.error('Failed to load poll data');
    } finally {
      setIsLoading(false);
    }
  }, [selectedAlbums.size]);

  // Poll for download status while downloads are active
  useEffect(() => {
    loadData();
    
    // Set up interval to check download status for both poll and AoTM
    const interval = setInterval(async () => {
      try {
        const [downloadData, aotmDownloadData] = await Promise.all([
          getDownloadsStatus(),
          getAoTMDownloadsStatus()
        ]);
        setDownloadsStatus(downloadData);
        setAotmDownloadsStatus(aotmDownloadData);
      } catch (error) {
        console.error('Error fetching download status:', error);
      }
    }, 3000); // Poll every 3 seconds
    
    downloadStatusInterval.current = interval;
    
    return () => {
      if (downloadStatusInterval.current) {
        clearInterval(downloadStatusInterval.current);
      }
    };
  }, [loadData]);

  const handleRefresh = async () => {
    setIsRefreshing(true);
    try {
      const result = await refreshPoll();
      if (result.success) {
        toast.success(result.message);
        setTimeout(loadData, 1000);
        const interval = setInterval(loadData, 3000);
        setTimeout(() => clearInterval(interval), 30000);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('Error refreshing:', error);
      toast.error('Failed to refresh poll data');
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSearch = async (albumId: number) => {
    setSearchingAlbums(prev => new Set(prev).add(albumId));
    try {
      const result = await searchAlbum(albumId);
      if (result.success) {
        toast.success('Album found on Orpheus!');
        await loadData();
      }
    } catch (error) {
      console.error('Error searching:', error);
      toast.error('Album not found on Orpheus');
    } finally {
      setSearchingAlbums(prev => {
        const next = new Set(prev);
        next.delete(albumId);
        return next;
      });
    }
  };

  // Get selected torrents for each album based on quality preference
  const selectedTorrents = useMemo(() => {
    const selections: Map<number, TorrentFormat | null> = new Map();
    for (const album of albums) {
      if (album.available_formats && album.available_formats.length > 0) {
        const selected = selectTorrentForQuality(album.available_formats, qualityPreference);
        selections.set(album.id, selected);
      } else {
        selections.set(album.id, null);
      }
    }
    return selections;
  }, [albums, qualityPreference]);

  // Count of selected albums that have available torrents
  const downloadableSelectedCount = useMemo(() => {
    return albums.filter(a => 
      selectedAlbums.has(a.id) && 
      a.orpheus_group_id !== null &&
      a.available_formats && 
      a.available_formats.length > 0
    ).length;
  }, [albums, selectedAlbums]);

  // Toggle album selection
  const handleToggleAlbum = (albumId: number) => {
    setSelectedAlbums(prev => {
      const next = new Set(prev);
      if (next.has(albumId)) {
        next.delete(albumId);
      } else {
        next.add(albumId);
      }
      return next;
    });
  };

  const handleSelectAllAlbums = () => {
    const albumsWithTorrents = albums.filter(a => a.orpheus_group_id !== null);
    setSelectedAlbums(new Set(albumsWithTorrents.map(a => a.id)));
  };

  const handleDeselectAllAlbums = () => {
    setSelectedAlbums(new Set());
  };

  const handleBatchDownload = async () => {
    if (selectedAlbums.size === 0) {
      toast.error('No albums selected');
      return;
    }

    if (!qbitStatus?.connected) {
      toast.error('qBittorrent is not connected');
      return;
    }

    setIsDownloading(true);
    try {
      const result = await selectiveDownloadPoll(Array.from(selectedAlbums), qualityPreference);
      
      if (result.success) {
        toast.success(result.message);
        // Immediately fetch download status
        const downloadData = await getDownloadsStatus();
        setDownloadsStatus(downloadData);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('Error downloading:', error);
      toast.error('Failed to download torrents');
    } finally {
      setIsDownloading(false);
    }
  };

  const waitForScanComplete = async (maxWaitMs = 120000): Promise<boolean> => {
    const startTime = Date.now();
    while (Date.now() - startTime < maxWaitMs) {
      await new Promise(r => setTimeout(r, 1500));
      try {
        const status = await getNavidromeScanStatus();
        setScanProgress(prev => ({ ...prev, count: status.count }));
        if (!status.scanning) return true;
      } catch {
        return false;
      }
    }
    return false;
  };

  const handleCreatePlaylist = async () => {
    setIsCreatingPlaylist(true);
    try {
      setScanProgress({ phase: 'scanning', count: 0, label: 'Scanning & creating playlist...' });
      const result = await createPlaylist();
      
      if (result.success) {
        toast.success(`${result.action === 'created' ? 'Created' : 'Updated'} playlist "${result.playlist_name}" with ${result.tracks_count} tracks!`);
      } else {
        toast.error(result.message || 'Failed to create playlist');
      }
    } catch (error) {
      console.error('Error creating playlist:', error);
      toast.error(error instanceof Error ? error.message : 'Failed to create playlist');
    } finally {
      setScanProgress({ phase: 'idle', count: 0, label: '' });
      setIsCreatingPlaylist(false);
    }
  };

  // AoTM Winners handlers
  const handleRefreshAotm = async () => {
    setIsRefreshingAotm(true);
    try {
      const result = await refreshAoTMWinners(10);
      if (result.success) {
        toast.success(result.message);
        const [aotmData, aotmStatus] = await Promise.all([
          fetchAoTMWinners(),
          getAoTMCacheStatus()
        ]);
        setAotmWinners(aotmData);
        setAotmCacheStatus(aotmStatus);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('Error refreshing AoTM winners:', error);
      toast.error('Failed to load AoTM winners');
    } finally {
      setIsRefreshingAotm(false);
    }
  };

  const handleToggleWinner = (threadId: number) => {
    setSelectedWinners(prev => {
      const next = new Set(prev);
      if (next.has(threadId)) {
        next.delete(threadId);
      } else {
        next.add(threadId);
      }
      return next;
    });
  };

  const handleSelectAllWinners = () => {
    setSelectedWinners(new Set(aotmWinners.map(w => w.thread_id)));
  };

  const handleDeselectAllWinners = () => {
    setSelectedWinners(new Set());
  };

  const handleDownloadAotmWinners = async () => {
    if (selectedWinners.size === 0) return;
    
    if (!qbitStatus?.connected) {
      toast.error('qBittorrent is not connected');
      return;
    }

    setIsDownloadingAotm(true);
    try {
      const result = await batchDownloadAoTMWinners(Array.from(selectedWinners), aotmQualityPreference);
      if (result.success) {
        toast.success(result.message);
        const downloadData = await getAoTMDownloadsStatus();
        setAotmDownloadsStatus(downloadData);
      } else {
        toast.error(result.message);
      }
    } catch (error) {
      console.error('Error downloading AoTM winners:', error);
      toast.error('Failed to download AoTM winners');
    } finally {
      setIsDownloadingAotm(false);
    }
  };

  const handleCreateAotmPlaylist = async () => {
    setIsCreatingAotmPlaylist(true);
    try {
      setScanProgress({ phase: 'scanning', count: 0, label: 'Scanning & creating AoTM playlist...' });
      const result = await createAoTMPlaylist();
      
      if (result.success) {
        toast.success(`${result.action === 'created' ? 'Created' : 'Updated'} playlist "${result.playlist_name}" with ${result.tracks_count} tracks!`);
      } else {
        toast.error(result.message || 'Failed to create AoTM playlist');
      }
    } catch (error) {
      console.error('Error creating AoTM playlist:', error);
      toast.error(error instanceof Error ? error.message : 'Failed to create AoTM playlist');
    } finally {
      setScanProgress({ phase: 'idle', count: 0, label: '' });
      setIsCreatingAotmPlaylist(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-950">
      <Toaster
        position="top-right"
        toastOptions={{
          className: 'bg-surface-800 text-white border border-surface-700',
          style: {
            background: '#1a1a24',
            color: '#f8fafc',
            border: '1px solid rgba(255,255,255,0.1)',
          },
          success: {
            iconTheme: { primary: '#22c55e', secondary: '#1a1a24' },
          },
          error: {
            iconTheme: { primary: '#ef4444', secondary: '#1a1a24' },
          },
        }}
      />

      <ScanProgressBar progress={scanProgress} />

      <Header 
        onRefresh={handleRefresh}
        isRefreshing={isRefreshing}
        cacheStatus={cacheStatus}
        qbitStatus={qbitStatus}
      />

      <main className="max-w-4xl mx-auto px-6 pb-8">
        {isLoading ? (
          <LoadingSkeleton />
        ) : albums.length === 0 ? (
          <EmptyState onRefresh={handleRefresh} />
        ) : (
          <>
            {/* Current Poll Section */}
            <div className="space-y-3 mb-4">
              {/* Section Header */}
              <div className="flex items-center gap-3 mb-2">
                <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent-500/20 to-brand-500/10 flex items-center justify-center">
                  <MusicNoteIcon className="w-5 h-5 text-accent-400" />
                </div>
                <h2 className="text-sm font-semibold text-white">Current Poll</h2>
              </div>

              {/* Controls bar */}
              <div className="p-4 rounded-xl bg-surface-900/50 border border-surface-800/50 space-y-3">
                <div className="flex items-center justify-between gap-4">
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-surface-400">Quality:</span>
                    <QualityDropdown
                      value={qualityPreference}
                      onChange={setQualityPreference}
                      disabled={isDownloading}
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={handleSelectAllAlbums}
                      className="px-2 py-1.5 rounded-lg text-xs text-surface-400 hover:text-white hover:bg-surface-800/60 transition-all"
                    >
                      Select All
                    </button>
                    <button
                      onClick={handleDeselectAllAlbums}
                      className="px-2 py-1.5 rounded-lg text-xs text-surface-400 hover:text-white hover:bg-surface-800/60 transition-all"
                    >
                      Clear
                    </button>
                  </div>
                </div>

                {/* Action buttons */}
                <div className="flex items-center justify-between">
                  <div className="text-xs text-accent-400">
                    {selectedAlbums.size} album{selectedAlbums.size !== 1 ? 's' : ''} selected ({downloadableSelectedCount} downloadable)
                  </div>
                  <div className="flex items-center gap-3">
                    <button
                      onClick={handleBatchDownload}
                      disabled={isDownloading || downloadableSelectedCount === 0 || !qbitStatus?.connected}
                      className={clsx(
                        "flex items-center gap-2 px-4 py-2 rounded-xl",
                        "bg-gradient-to-r from-brand-500 to-accent-500",
                        "text-white font-semibold text-sm",
                        "shadow-lg shadow-brand-500/25",
                        "hover:shadow-xl hover:shadow-brand-500/30",
                        "transition-all duration-300",
                        (isDownloading || downloadableSelectedCount === 0 || !qbitStatus?.connected) && "opacity-50 cursor-not-allowed"
                      )}
                    >
                      {isDownloading ? (
                        <RefreshIcon className="w-4 h-4 animate-spin" />
                      ) : (
                        <DownloadIcon className="w-4 h-4" />
                      )}
                      {isDownloading ? 'Sending...' : `Send ${downloadableSelectedCount} to qBit`}
                    </button>

                    <button
                      onClick={handleCreatePlaylist}
                      disabled={!downloadsStatus?.all_completed || isCreatingPlaylist}
                      className={clsx(
                        "flex items-center gap-2 px-4 py-2 rounded-xl",
                        "bg-gradient-to-r from-success-600 to-success-500",
                        "text-white font-semibold text-sm",
                        "shadow-lg shadow-success-500/25",
                        "hover:shadow-xl hover:shadow-success-500/30",
                        "transition-all duration-300",
                        (!downloadsStatus?.all_completed || isCreatingPlaylist) && "opacity-50 cursor-not-allowed"
                      )}
                    >
                      {isCreatingPlaylist ? (
                        <RefreshIcon className="w-4 h-4 animate-spin" />
                      ) : (
                        <PlaylistIcon className="w-4 h-4" />
                      )}
                      Create Playlist
                    </button>
                  </div>
                </div>
              </div>

              {/* Download progress indicator */}
              {downloadsStatus && downloadsStatus.total > 0 && (
                <div className="p-3 rounded-xl bg-surface-900/30 border border-surface-800/30">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm text-surface-400">
                      Poll Downloads: {downloadsStatus.completed}/{downloadsStatus.total}
                    </span>
                    {downloadsStatus.all_completed ? (
                      <span className="text-xs px-2 py-1 rounded bg-success-500/20 text-success-400 font-medium">
                        All Complete!
                      </span>
                    ) : (
                      <span className="text-xs px-2 py-1 rounded bg-accent-500/20 text-accent-400 font-medium">
                        In Progress
                      </span>
                    )}
                  </div>
                  <div className="w-full h-2 bg-surface-800/50 rounded-full overflow-hidden">
                    <div 
                      className={clsx(
                        "h-full transition-all duration-500 rounded-full",
                        downloadsStatus.all_completed ? "bg-gradient-to-r from-success-600 to-success-400" : "bg-gradient-to-r from-accent-600 to-brand-500"
                      )}
                      style={{ width: `${(downloadsStatus.completed / downloadsStatus.total) * 100}%` }}
                    />
                  </div>
                </div>
              )}
            </div>

            {/* Album list */}
            <div className="space-y-3 mb-6">
              {albums.map((album) => (
                <AlbumRow
                  key={album.id}
                  album={album}
                  onSearch={handleSearch}
                  isSearching={searchingAlbums.has(album.id)}
                  selectedTorrent={selectedTorrents.get(album.id) || null}
                  isSelected={selectedAlbums.has(album.id)}
                  onToggle={handleToggleAlbum}
                />
              ))}
            </div>

            {/* AoTM Winners Panel */}
            <AoTMWinnersPanel
              winners={aotmWinners}
              cacheStatus={aotmCacheStatus}
              selectedWinners={selectedWinners}
              onToggleWinner={handleToggleWinner}
              onSelectAll={handleSelectAllWinners}
              onDeselectAll={handleDeselectAllWinners}
              onRefresh={handleRefreshAotm}
              onDownload={handleDownloadAotmWinners}
              onCreatePlaylist={handleCreateAotmPlaylist}
              isRefreshing={isRefreshingAotm}
              isDownloading={isDownloadingAotm}
              isCreatingPlaylist={isCreatingAotmPlaylist}
              downloadsStatus={aotmDownloadsStatus}
              qualityPreference={aotmQualityPreference}
              onQualityChange={setAotmQualityPreference}
              qbitConnected={qbitStatus?.connected || false}
            />
          </>
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-surface-800/50 py-4">
        <div className="max-w-4xl mx-auto px-6 text-center text-xs text-surface-500">
          Orpheus Poll to Playlist v1.0.0
        </div>
      </footer>
    </div>
  );
}

export default App;
