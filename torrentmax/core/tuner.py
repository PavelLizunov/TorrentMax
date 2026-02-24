"""Auto-tuning — adapts libtorrent settings based on connection type and runtime stats."""

import logging
from dataclasses import dataclass

from torrentmax.network.detector import NetworkDetector, VpnDetector, ConnectionType

logger = logging.getLogger(__name__)

# Connection profiles — libtorrent setting overrides per connection type
PROFILES: dict[str, dict] = {
    ConnectionType.WIFI: {
        'connections_limit': 100,
        'max_out_request_queue': 500,
        'send_buffer_watermark': 3 * 1024 * 1024,
        'send_buffer_low_watermark': 512 * 1024,
        'recv_socket_buffer_size': 1 * 1024 * 1024,
        'send_socket_buffer_size': 1 * 1024 * 1024,
        'request_queue_time': 3,
        'whole_pieces_threshold': 20,
        'cache_size': 1024,               # 16 MB
        'active_downloads': 3,
        'active_seeds': 3,
    },
    ConnectionType.LAN: {
        'connections_limit': 300,
        'max_out_request_queue': 1500,
        'send_buffer_watermark': 16 * 1024 * 1024,
        'send_buffer_low_watermark': 4 * 1024 * 1024,
        'recv_socket_buffer_size': 4 * 1024 * 1024,
        'send_socket_buffer_size': 4 * 1024 * 1024,
        'request_queue_time': 3,
        'whole_pieces_threshold': 5,
        'cache_size': 4096,               # 64 MB
        'active_downloads': 5,
        'active_seeds': 5,
    },
    'vpn': {
        'connections_limit': 150,
        'max_out_request_queue': 1000,
        'send_buffer_watermark': 8 * 1024 * 1024,
        'send_buffer_low_watermark': 2 * 1024 * 1024,
        'recv_socket_buffer_size': 2 * 1024 * 1024,
        'send_socket_buffer_size': 2 * 1024 * 1024,
        'request_queue_time': 4,
        'whole_pieces_threshold': 10,
        'cache_size': 2048,               # 32 MB
        'active_downloads': 3,
        'active_seeds': 3,
    },
}


@dataclass
class Bottleneck:
    """Describes a detected performance bottleneck."""
    category: str       # 'disk', 'network', 'peers', 'cpu'
    severity: float     # 0.0 — 1.0
    message: str
    suggestion: str


class AutoTuner:
    """Detects connection type and applies optimal libtorrent settings."""

    def __init__(self, engine):
        self._engine = engine
        self._current_profile: str = ConnectionType.UNKNOWN
        self._override_profile: str | None = None  # Manual override by user

    @property
    def current_profile(self) -> str:
        return self._current_profile

    def set_manual_profile(self, profile_name: str | None):
        """Set a manual profile override. None to return to auto."""
        self._override_profile = profile_name
        if profile_name:
            self._apply_profile(profile_name)

    def detect_and_apply(self) -> str:
        """Detect network type and apply the best profile. Returns profile name."""
        if self._override_profile:
            return self._override_profile

        vpn_active = VpnDetector.is_active()
        connection_type = NetworkDetector.get_type()

        if vpn_active:
            profile_name = 'vpn'
        elif connection_type == ConnectionType.WIFI:
            profile_name = ConnectionType.WIFI
        else:
            profile_name = ConnectionType.LAN

        if profile_name != self._current_profile:
            self._apply_profile(profile_name)

        return profile_name

    def analyze_bottlenecks(self, session_stats: dict, disk_usage_pct: float,
                            cpu_pct: float) -> list[Bottleneck]:
        """Analyze current stats and detect performance bottlenecks."""
        bottlenecks = []

        # Disk bottleneck
        if disk_usage_pct > 90:
            bottlenecks.append(Bottleneck(
                category='disk',
                severity=min(1.0, disk_usage_pct / 100),
                message=f"Disk loaded at {disk_usage_pct:.0f}%",
                suggestion="Reducing connections to lower disk pressure",
            ))
        elif disk_usage_pct > 70:
            bottlenecks.append(Bottleneck(
                category='disk',
                severity=0.5,
                message=f"Disk at {disk_usage_pct:.0f}%",
                suggestion="Disk usage is elevated, monitoring",
            ))

        # CPU bottleneck
        if cpu_pct > 85:
            bottlenecks.append(Bottleneck(
                category='cpu',
                severity=min(1.0, cpu_pct / 100),
                message=f"CPU at {cpu_pct:.0f}%",
                suggestion="High CPU — may limit throughput",
            ))

        # Peer bottleneck — downloading but very few peers
        dl_rate = session_stats.get('download_rate', 0)
        num_peers = session_stats.get('num_peers', 0)
        if dl_rate > 0 and num_peers < 5:
            bottlenecks.append(Bottleneck(
                category='peers',
                severity=0.7,
                message=f"Only {num_peers} peers connected",
                suggestion="Few peers available — speed limited by swarm",
            ))

        # No download despite peers
        if num_peers > 10 and dl_rate < 10 * 1024:
            bottlenecks.append(Bottleneck(
                category='network',
                severity=0.6,
                message=f"Low speed ({dl_rate / 1024:.0f} KB/s) with {num_peers} peers",
                suggestion="Network may be throttled or peers are slow",
            ))

        return bottlenecks

    def apply_dynamic_adjustments(self, bottlenecks: list[Bottleneck]):
        """Apply runtime adjustments based on detected bottlenecks."""
        for bn in bottlenecks:
            if bn.category == 'disk' and bn.severity > 0.8:
                # Reduce connections to ease disk pressure
                current = PROFILES.get(self._current_profile, {})
                reduced = max(30, current.get('connections_limit', 100) // 2)
                self._engine.apply_settings({'connections_limit': reduced})
                logger.info("Reduced connections to %d due to disk load", reduced)

    def _apply_profile(self, profile_name: str):
        """Apply a named profile."""
        settings = PROFILES.get(profile_name)
        if not settings:
            logger.warning("Unknown profile: %s", profile_name)
            return
        self._engine.apply_settings(settings)
        self._current_profile = profile_name
        logger.info("Applied profile: %s", profile_name)
