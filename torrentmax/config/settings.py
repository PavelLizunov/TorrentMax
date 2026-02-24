"""Application settings — persistence via JSON."""

import json
import logging
import os
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)

DEFAULT_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', '.'), 'TorrentMax')


@dataclass
class AppSettings:
    """Persistent application settings."""
    # Paths
    download_path: str = ""
    data_dir: str = ""

    # Network
    listen_port: int = 6881
    max_download_rate: int = 0          # 0 = unlimited (bytes/sec)
    max_upload_rate: int = 0            # 0 = unlimited (bytes/sec)
    auto_profile: bool = True           # Auto-detect connection profile
    manual_profile: str = ""            # 'wifi', 'lan', 'vpn', or '' for auto

    # Appearance
    start_minimized: bool = False
    minimize_to_tray: bool = True

    def __post_init__(self):
        if not self.download_path:
            self.download_path = os.path.join(os.path.expanduser('~'), 'Downloads')
        if not self.data_dir:
            self.data_dir = DEFAULT_DATA_DIR

    @staticmethod
    def load(path: str | None = None) -> 'AppSettings':
        """Load settings from JSON. Returns defaults if file doesn't exist."""
        if path is None:
            path = os.path.join(DEFAULT_DATA_DIR, 'settings.json')

        if not os.path.isfile(path):
            logger.info("No settings file, using defaults")
            return AppSettings()

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            settings = AppSettings(**{k: v for k, v in data.items()
                                      if k in AppSettings.__dataclass_fields__})
            logger.info("Loaded settings from %s", path)
            return settings
        except Exception as e:
            logger.warning("Failed to load settings: %s", e)
            return AppSettings()

    def save(self, path: str | None = None):
        """Save settings to JSON."""
        if path is None:
            path = os.path.join(self.data_dir, 'settings.json')

        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(asdict(self), f, indent=2)
            logger.info("Saved settings to %s", path)
        except Exception as e:
            logger.warning("Failed to save settings: %s", e)

    def ensure_dirs(self):
        """Create data directories if they don't exist."""
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(os.path.join(self.data_dir, 'resume'), exist_ok=True)
        os.makedirs(self.download_path, exist_ok=True)
