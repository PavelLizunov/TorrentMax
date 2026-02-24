"""TorrentMax — entry point."""

import sys
import os
import logging

from torrentmax.config.settings import AppSettings
from torrentmax.core.engine import TorrentEngine
from torrentmax.core.tuner import AutoTuner


def setup_logging(data_dir: str):
    """Configure logging to file and console."""
    log_dir = os.path.join(data_dir, 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'torrentmax.log')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )


def main():
    # High-DPI support
    os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')

    # Load settings early (before any GUI or libtorrent init)
    settings = AppSettings.load()
    settings.ensure_dirs()

    setup_logging(settings.data_dir)
    logger = logging.getLogger(__name__)
    logger.info("TorrentMax starting")

    # IMPORTANT: Create libtorrent session BEFORE QApplication.
    # libtorrent initializes OpenSSL on its background threads, which conflicts
    # with Qt's SSL initialization if Qt is created first — causes segfault.
    engine = TorrentEngine()
    engine.start(settings.data_dir, settings.listen_port)

    # Import Qt AFTER libtorrent session is created to avoid OpenSSL conflict
    from PyQt6.QtWidgets import QApplication
    from torrentmax.ui.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName('TorrentMax')
    app.setOrganizationName('TorrentMax')

    # Apply dark theme
    app.setStyleSheet(DARK_STYLE)

    # Apply speed limits
    limits = {}
    if settings.max_download_rate > 0:
        limits['download_rate_limit'] = settings.max_download_rate
    if settings.max_upload_rate > 0:
        limits['upload_rate_limit'] = settings.max_upload_rate
    if limits:
        engine.apply_settings(limits)

    # Auto-tuner
    tuner = AutoTuner(engine)
    if settings.auto_profile:
        profile = tuner.detect_and_apply()
        logger.info("Auto-detected profile: %s", profile)
    elif settings.manual_profile:
        tuner.set_manual_profile(settings.manual_profile)

    # Restore saved torrents
    saved = engine.load_torrent_list(settings.data_dir)
    for entry in saved:
        ih = entry.get('info_hash', '')
        save_path = entry.get('save_path', settings.download_path)
        name = entry.get('name', '')
        trackers = entry.get('trackers', [])

        # Reconstruct magnet with trackers for better peer discovery
        magnet = f"magnet:?xt=urn:btih:{ih}"
        if name:
            from urllib.parse import quote
            magnet += f"&dn={quote(name)}"
        for tr in trackers:
            from urllib.parse import quote
            magnet += f"&tr={quote(tr)}"

        engine.add_torrent(magnet, save_path, settings.data_dir)
    if saved:
        logger.info("Restored %d torrents", len(saved))

    # Create and show window
    window = MainWindow(engine, tuner, settings)
    if not settings.start_minimized:
        window.show()

    # Run
    exit_code = app.exec()

    # Cleanup is handled by MainWindow._quit_app() which stops timers,
    # saves state and stops the engine. Only do fallback cleanup here
    # in case the window was closed abnormally.
    if engine.is_running:
        logger.info("Fallback shutdown...")
        settings.save()
        engine.stop(settings.data_dir)

    logger.info("Goodbye")
    sys.exit(exit_code)


DARK_STYLE = """
QWidget {
    background-color: #1e1e1e;
    color: #cccccc;
    font-size: 13px;
}
QMainWindow {
    background-color: #1e1e1e;
}
QToolBar {
    background-color: #2d2d2d;
    border: none;
    spacing: 6px;
    padding: 4px;
}
QToolBar QToolButton {
    background-color: #3d3d3d;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 4px 10px;
    color: #cccccc;
}
QToolBar QToolButton:hover {
    background-color: #4d4d4d;
}
QToolBar QToolButton:pressed {
    background-color: #555;
}
QTableWidget {
    background-color: #1e1e1e;
    alternate-background-color: #252525;
    gridline-color: #333;
    selection-background-color: #264f78;
    selection-color: #ffffff;
    border: 1px solid #333;
}
QHeaderView::section {
    background-color: #2d2d2d;
    color: #cccccc;
    padding: 4px;
    border: 1px solid #333;
    font-weight: bold;
}
QComboBox {
    background-color: #3d3d3d;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 3px 8px;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #2d2d2d;
    selection-background-color: #264f78;
}
QLineEdit, QSpinBox {
    background-color: #3d3d3d;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 4px;
    color: #cccccc;
}
QPushButton {
    background-color: #3d3d3d;
    border: 1px solid #555;
    border-radius: 3px;
    padding: 5px 15px;
    color: #cccccc;
}
QPushButton:hover {
    background-color: #4d4d4d;
}
QPushButton:pressed {
    background-color: #555;
}
QTabWidget::pane {
    border: 1px solid #333;
}
QTabBar::tab {
    background-color: #2d2d2d;
    border: 1px solid #333;
    padding: 6px 12px;
}
QTabBar::tab:selected {
    background-color: #3d3d3d;
}
QStatusBar {
    background-color: #2d2d2d;
    color: #888;
}
QMenu {
    background-color: #2d2d2d;
    border: 1px solid #444;
}
QMenu::item:selected {
    background-color: #264f78;
}
QCheckBox {
    spacing: 6px;
}
QSplitter::handle {
    background-color: #333;
    height: 3px;
}
QDialog {
    background-color: #1e1e1e;
}
"""


if __name__ == '__main__':
    main()
