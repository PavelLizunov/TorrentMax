"""Single torrent status model."""

from dataclasses import dataclass, field
from enum import Enum

import libtorrent as lt


class TorrentState(Enum):
    QUEUED = "queued"
    CHECKING = "checking"
    DOWNLOADING_META = "downloading_meta"
    DOWNLOADING = "downloading"
    SEEDING = "seeding"
    PAUSED = "paused"
    ERROR = "error"


# Map libtorrent states to our enum
_LT_STATE_MAP = {
    lt.torrent_status.states.checking_files: TorrentState.CHECKING,
    lt.torrent_status.states.downloading_metadata: TorrentState.DOWNLOADING_META,
    lt.torrent_status.states.downloading: TorrentState.DOWNLOADING,
    lt.torrent_status.states.finished: TorrentState.SEEDING,
    lt.torrent_status.states.seeding: TorrentState.SEEDING,
    lt.torrent_status.states.checking_resume_data: TorrentState.CHECKING,
}


@dataclass
class TorrentStatus:
    """Snapshot of a single torrent's status for the UI."""
    info_hash: str
    name: str
    state: TorrentState
    progress: float           # 0.0 — 1.0
    download_rate: float      # bytes/sec
    upload_rate: float        # bytes/sec
    total_size: int           # bytes
    total_downloaded: int     # bytes
    total_uploaded: int       # bytes
    num_peers: int
    num_seeds: int
    eta_seconds: int          # -1 if unknown
    save_path: str
    error: str = ""

    @staticmethod
    def from_handle(handle: lt.torrent_handle) -> 'TorrentStatus':
        """Build TorrentStatus from a libtorrent handle."""
        s = handle.status()
        info_hash = str(handle.info_hash())
        name = handle.name() or info_hash[:8]

        if s.errc.value() != 0:
            state = TorrentState.ERROR
            error = s.errc.message()
        elif s.flags & lt.torrent_flags.paused:
            state = TorrentState.PAUSED
            error = ""
        else:
            state = _LT_STATE_MAP.get(s.state, TorrentState.QUEUED)
            error = ""

        # ETA calculation
        eta = -1
        if s.download_rate > 0 and s.total_wanted > 0:
            remaining = s.total_wanted - s.total_wanted_done
            if remaining > 0:
                eta = int(remaining / s.download_rate)

        return TorrentStatus(
            info_hash=info_hash,
            name=name,
            state=state,
            progress=s.progress,
            download_rate=s.download_rate,
            upload_rate=s.upload_rate,
            total_size=s.total_wanted,
            total_downloaded=s.total_wanted_done,
            total_uploaded=s.total_upload,
            num_peers=s.num_peers,
            num_seeds=s.num_seeds,
            eta_seconds=eta,
            save_path=s.save_path,
            error=error,
        )


def format_size(size_bytes: int | float) -> str:
    """Format bytes into human-readable string."""
    if size_bytes < 0:
        return "?"
    value = float(size_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if abs(value) < 1024:
            if unit == 'B':
                return f"{int(value)} B"
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} PB"


def format_speed(bytes_per_sec: float) -> str:
    """Format speed into human-readable string."""
    return f"{format_size(int(bytes_per_sec))}/s"


def format_eta(seconds: int) -> str:
    """Format ETA into human-readable string."""
    if seconds < 0:
        return "--"
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    return f"{hours}h {minutes}m"
