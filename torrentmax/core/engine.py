"""BitTorrent engine — libtorrent session wrapper."""

import os
import json
import time
import logging
import libtorrent as lt

logger = logging.getLogger(__name__)

# DHT bootstrap nodes — essential for finding peers via magnet links
DHT_BOOTSTRAP_NODES = [
    ('router.bittorrent.com', 6881),
    ('router.utorrent.com', 6881),
    ('dht.transmissionbt.com', 6881),
    ('dht.libtorrent.org', 25401),
    ('dht.aelitis.com', 6881),
]

# Default session settings (libtorrent 2.0+ compatible)
DEFAULT_SETTINGS = {
    'user_agent': 'TorrentMax/1.0',
    'alert_mask': lt.alert.category_t.all_categories,
    'enable_dht': True,
    'enable_lsd': True,
    'enable_upnp': True,
    'enable_natpmp': True,
    'listen_interfaces': '0.0.0.0:6881,[::]:6881',
    'file_pool_size': 500,
}

# Maximum time to wait for resume data on shutdown (seconds)
SHUTDOWN_RESUME_TIMEOUT = 8


class TorrentEngine:
    """Manages libtorrent session and torrent handles."""

    def __init__(self):
        self._session: lt.session | None = None
        self._handles: dict[str, lt.torrent_handle] = {}  # info_hash -> handle
        self._stopped = False  # guard against double-stop

    @property
    def session(self) -> lt.session | None:
        return self._session

    @property
    def is_running(self) -> bool:
        return self._session is not None and not self._stopped

    @property
    def handles(self) -> dict[str, lt.torrent_handle]:
        return dict(self._handles)

    def start(self, state_dir: str, listen_port: int = 6881):
        """Initialize and start the libtorrent session."""
        settings = dict(DEFAULT_SETTINGS)
        settings['listen_interfaces'] = f'0.0.0.0:{listen_port},[::]:{listen_port}'

        self._session = lt.session(settings)
        self._stopped = False

        # Load DHT state if available
        dht_file = os.path.join(state_dir, 'dht_state')
        if os.path.isfile(dht_file):
            try:
                with open(dht_file, 'rb') as f:
                    self._session.load_state(lt.bdecode(f.read()))
                logger.info("Loaded DHT state")
            except Exception as e:
                logger.warning("Failed to load DHT state: %s", e)

        # Bootstrap DHT — required for magnet link metadata resolution
        for host, port in DHT_BOOTSTRAP_NODES:
            self._session.add_dht_node((host, port))
        logger.info("Added %d DHT bootstrap nodes", len(DHT_BOOTSTRAP_NODES))

        logger.info("Engine started on port %d", listen_port)

    def stop(self, state_dir: str):
        """Save state and stop the session. Safe to call multiple times."""
        if not self._session or self._stopped:
            return
        self._stopped = True

        # Pause session first — stops all network activity immediately
        try:
            self._session.pause()
        except Exception as e:
            logger.warning("Failed to pause session: %s", e)

        # Save DHT state
        dht_file = os.path.join(state_dir, 'dht_state')
        try:
            state = self._session.save_state()
            with open(dht_file, 'wb') as f:
                f.write(lt.bencode(state))
        except Exception as e:
            logger.warning("Failed to save DHT state: %s", e)

        # Save resume data with hard timeout
        self._save_all_resume_data(state_dir)

        # Clean up session
        try:
            del self._session
        except Exception:
            pass
        self._session = None
        self._handles.clear()
        logger.info("Engine stopped")

    def add_torrent(self, source: str, save_path: str, state_dir: str) -> lt.torrent_handle | None:
        """Add a torrent from magnet link or .torrent file path.

        Returns the torrent handle or None on error.
        """
        if not self.is_running:
            logger.error("Engine not started")
            return None

        try:
            params = lt.parse_magnet_uri(source) if source.startswith('magnet:') else None
        except Exception as e:
            logger.error("Failed to parse magnet: %s", e)
            return None

        if params is None:
            # .torrent file
            if not os.path.isfile(source):
                logger.error("Torrent file not found: %s", source)
                return None
            try:
                info = lt.torrent_info(source)
                params = lt.add_torrent_params()
                params.ti = info
            except Exception as e:
                logger.error("Failed to parse torrent file: %s", e)
                return None

        params.save_path = save_path

        # Try loading resume data
        try:
            info_hash = str(params.info_hashes.v1 if hasattr(params, 'info_hashes') else params.info_hash)
        except Exception:
            info_hash = ""

        if info_hash:
            resume_file = os.path.join(state_dir, 'resume', f'{info_hash}.fastresume')
            if os.path.isfile(resume_file):
                try:
                    with open(resume_file, 'rb') as f:
                        params.resume_data = f.read()
                    logger.info("Loaded resume data for %s", info_hash)
                except Exception as e:
                    logger.warning("Failed to load resume data: %s", e)

        handle = self._session.add_torrent(params)
        ih = str(handle.info_hash())
        self._handles[ih] = handle
        logger.info("Added torrent: %s", handle.name() or ih)
        return handle

    def remove_torrent(self, info_hash: str, delete_files: bool = False):
        """Remove a torrent by info hash."""
        handle = self._handles.pop(info_hash, None)
        if handle and self._session:
            try:
                if delete_files:
                    self._session.remove_torrent(handle, lt.options_t.delete_files)
                else:
                    self._session.remove_torrent(handle)
            except Exception as e:
                logger.warning("Failed to remove torrent: %s", e)
            logger.info("Removed torrent: %s", info_hash)

    def apply_settings(self, settings: dict):
        """Apply a dict of libtorrent settings to the session."""
        if not self.is_running:
            return
        pack = self._session.get_settings()
        pack.update(settings)
        self._session.apply_settings(pack)
        logger.debug("Applied settings: %s", list(settings.keys()))

    def get_session_stats(self) -> dict:
        """Return session-level stats."""
        if not self.is_running:
            return {}
        try:
            status = self._session.status()
            return {
                'download_rate': status.download_rate,
                'upload_rate': status.upload_rate,
                'num_peers': status.num_peers,
                'dht_nodes': status.dht_nodes,
            }
        except Exception:
            return {}

    def process_alerts(self) -> list[lt.alert]:
        """Pop and return all pending alerts."""
        if not self.is_running:
            return []
        try:
            return self._session.pop_alerts()
        except Exception:
            return []

    def _save_all_resume_data(self, state_dir: str):
        """Save resume data for all torrents with a hard timeout."""
        resume_dir = os.path.join(state_dir, 'resume')
        os.makedirs(resume_dir, exist_ok=True)

        outstanding = 0
        for ih, handle in self._handles.items():
            try:
                if handle.is_valid() and handle.need_save_resume_data():
                    handle.save_resume_data(lt.save_resume_flags_t.save_info_dict)
                    outstanding += 1
            except Exception:
                pass

        if outstanding == 0:
            return

        logger.info("Waiting for %d resume data saves...", outstanding)
        deadline = time.monotonic() + SHUTDOWN_RESUME_TIMEOUT

        while outstanding > 0:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                logger.warning("Resume data timeout, %d saves pending", outstanding)
                break

            # Wait for at most 1 second at a time
            wait_ms = min(1000, int(remaining * 1000))
            alert_ptr = self._session.wait_for_alert(wait_ms)
            if not alert_ptr:
                continue

            for alert in self._session.pop_alerts():
                if isinstance(alert, lt.save_resume_data_alert):
                    try:
                        ih = str(alert.handle.info_hash())
                        path = os.path.join(resume_dir, f'{ih}.fastresume')
                        with open(path, 'wb') as f:
                            f.write(lt.bencode(lt.write_resume_data(alert)))
                    except Exception as e:
                        logger.warning("Failed to write resume data: %s", e)
                    outstanding -= 1
                elif isinstance(alert, lt.save_resume_data_failed_alert):
                    outstanding -= 1
                # All other alert types are silently ignored

        logger.info("Resume data save complete (%d remaining)", outstanding)

    def save_torrent_list(self, state_dir: str):
        """Persist the list of active torrents for session restore."""
        entries = []
        for ih, handle in self._handles.items():
            try:
                if handle.is_valid():
                    status = handle.status()
                    # Save trackers for better restore
                    trackers = []
                    try:
                        trackers = [t.url for t in handle.trackers()]
                    except Exception:
                        pass
                    entries.append({
                        'info_hash': ih,
                        'save_path': status.save_path,
                        'name': handle.name(),
                        'trackers': trackers,
                    })
            except Exception:
                # Handle may have become invalid
                pass
        path = os.path.join(state_dir, 'torrents.json')
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(entries, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save torrent list: %s", e)

    def load_torrent_list(self, state_dir: str) -> list[dict]:
        """Load the persisted torrent list."""
        path = os.path.join(state_dir, 'torrents.json')
        if not os.path.isfile(path):
            return []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning("Failed to load torrent list: %s", e)
            return []
