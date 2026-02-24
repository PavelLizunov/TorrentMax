"""Network type detection — WiFi / LAN / VPN."""

import logging
import subprocess

import psutil

logger = logging.getLogger(__name__)


class ConnectionType:
    WIFI = "wifi"
    LAN = "lan"
    UNKNOWN = "unknown"


class NetworkDetector:
    """Detects active network connection type using psutil + netsh on Windows."""

    @staticmethod
    def get_type() -> str:
        """Return 'wifi', 'lan', or 'unknown'."""
        try:
            stats = psutil.net_if_stats()
            for iface_name, iface_stats in stats.items():
                if not iface_stats.isup:
                    continue
                name_lower = iface_name.lower()
                if 'wi-fi' in name_lower or 'wlan' in name_lower or 'wireless' in name_lower:
                    return ConnectionType.WIFI
                if 'ethernet' in name_lower or 'eth' in name_lower:
                    return ConnectionType.LAN
            # If we found active interfaces but couldn't classify, try netsh
            return NetworkDetector._detect_via_netsh()
        except Exception as e:
            logger.warning("Network detection failed: %s", e)
            return ConnectionType.UNKNOWN

    @staticmethod
    def _detect_via_netsh() -> str:
        """Fallback: use netsh to check if WiFi is connected."""
        try:
            result = subprocess.run(
                ['netsh', 'wlan', 'show', 'interfaces'],
                capture_output=True, text=True, timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            if result.returncode == 0 and 'connected' in result.stdout.lower():
                return ConnectionType.WIFI
        except Exception:
            pass
        return ConnectionType.LAN  # Default to LAN if WiFi not detected

    @staticmethod
    def get_active_interface_info() -> dict:
        """Return info about the active network interface."""
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        io = psutil.net_io_counters(pernic=True)

        for iface_name, iface_stats in stats.items():
            if not iface_stats.isup:
                continue
            # Skip loopback and virtual adapters
            name_lower = iface_name.lower()
            if 'loopback' in name_lower or name_lower == 'lo':
                continue

            info = {
                'name': iface_name,
                'speed_mbps': iface_stats.speed,
                'mtu': iface_stats.mtu,
            }
            if iface_name in addrs:
                for addr in addrs[iface_name]:
                    if addr.family.name == 'AF_INET':
                        info['ipv4'] = addr.address
                        break
            if iface_name in io:
                counters = io[iface_name]
                info['bytes_sent'] = counters.bytes_sent
                info['bytes_recv'] = counters.bytes_recv
            return info
        return {}


class VpnDetector:
    """Detects if a VPN connection is active."""

    VPN_KEYWORDS = [
        'tap', 'tun', 'vpn', 'nordlynx', 'wireguard', 'wg',
        'proton', 'mullvad', 'openvpn', 'amnezia', 'awg',
        'cloudflare', 'warp', 'zerotier', 'tailscale',
    ]

    @staticmethod
    def is_active() -> bool:
        """Check if a VPN adapter is active."""
        try:
            stats = psutil.net_if_stats()
            for iface_name, iface_stats in stats.items():
                if not iface_stats.isup:
                    continue
                name_lower = iface_name.lower()
                if any(kw in name_lower for kw in VpnDetector.VPN_KEYWORDS):
                    return True
        except Exception as e:
            logger.warning("VPN detection failed: %s", e)
        return False

    @staticmethod
    def get_vpn_interface() -> str | None:
        """Return the name of the active VPN interface, or None."""
        try:
            stats = psutil.net_if_stats()
            for iface_name, iface_stats in stats.items():
                if not iface_stats.isup:
                    continue
                name_lower = iface_name.lower()
                if any(kw in name_lower for kw in VpnDetector.VPN_KEYWORDS):
                    return iface_name
        except Exception:
            pass
        return None
