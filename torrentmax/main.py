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
    app.setOrganizationName('NiniTux')

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
/* ── NiniTux Brand Dark Theme (Zinc + Blue) ── */

QWidget {
    background-color: #18181B;
    color: #F4F4F5;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}
QMainWindow {
    background-color: #18181B;
}

/* ── Toolbar ── */
QToolBar {
    background-color: #27272A;
    border: none;
    border-bottom: 1px solid #3F3F46;
    spacing: 6px;
    padding: 4px 8px;
}
QToolBar QToolButton {
    background-color: #343438;
    border: 1px solid #52525B;
    border-radius: 4px;
    padding: 5px 12px;
    color: #D4D4D8;
    font-weight: bold;
    font-size: 10pt;
}
QToolBar QToolButton:hover {
    background-color: #3B82F6;
    border-color: #3B82F6;
    color: #FFFFFF;
}
QToolBar QToolButton:pressed {
    background-color: #2563EB;
    border-color: #2563EB;
    color: #FFFFFF;
}

/* ── Torrent Table ── */
QTableWidget {
    background-color: #18181B;
    alternate-background-color: #1f1f23;
    gridline-color: #3F3F46;
    selection-background-color: #1E3A8A;
    selection-color: #FFFFFF;
    border: 1px solid #3F3F46;
}
QHeaderView::section {
    background-color: #27272A;
    color: #A1A1AA;
    padding: 5px;
    border: 1px solid #3F3F46;
    font-weight: bold;
    font-size: 11px;
    text-transform: uppercase;
}

/* ── Inputs ── */
QComboBox {
    background-color: #27272A;
    border: 1px solid #52525B;
    border-radius: 4px;
    padding: 4px 10px;
    color: #F4F4F5;
}
QComboBox:focus {
    border-color: #3B82F6;
}
QComboBox::drop-down {
    border: none;
}
QComboBox QAbstractItemView {
    background-color: #27272A;
    selection-background-color: #1E3A8A;
    border: 1px solid #3F3F46;
}
QLineEdit, QSpinBox {
    background-color: #27272A;
    border: 1px solid #52525B;
    border-radius: 4px;
    padding: 5px 8px;
    color: #F4F4F5;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #3B82F6;
}

/* ── Buttons ── */
QPushButton {
    background-color: #343438;
    border: 1px solid #52525B;
    border-radius: 4px;
    padding: 6px 16px;
    color: #D4D4D8;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #3B82F6;
    border-color: #3B82F6;
    color: #FFFFFF;
}
QPushButton:pressed {
    background-color: #2563EB;
    border-color: #2563EB;
    color: #FFFFFF;
}

/* ── Tabs ── */
QTabWidget::pane {
    border: 1px solid #3F3F46;
    background-color: #18181B;
}
QTabBar::tab {
    background-color: #27272A;
    border: 1px solid #3F3F46;
    border-bottom: none;
    padding: 7px 14px;
    color: #A1A1AA;
    font-weight: bold;
}
QTabBar::tab:selected {
    background-color: #18181B;
    color: #3B82F6;
    border-bottom: 2px solid #3B82F6;
}
QTabBar::tab:hover:!selected {
    color: #F4F4F5;
}

/* ── Status Bar ── */
QStatusBar {
    background-color: #27272A;
    color: #71717A;
    border-top: 1px solid #3F3F46;
    font-size: 12px;
}

/* ── Menus ── */
QMenu {
    background-color: #27272A;
    border: 1px solid #3F3F46;
}
QMenu::item {
    padding: 6px 24px;
}
QMenu::item:selected {
    background-color: #1E3A8A;
    color: #FFFFFF;
}

/* ── Misc ── */
QCheckBox {
    spacing: 8px;
    color: #D4D4D8;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #52525B;
    border-radius: 3px;
    background-color: #27272A;
}
QCheckBox::indicator:checked {
    background-color: #3B82F6;
    border-color: #3B82F6;
}
QSplitter::handle {
    background-color: #3F3F46;
    height: 2px;
}
QDialog {
    background-color: #18181B;
}
QLabel {
    color: #F4F4F5;
}
QScrollBar:vertical {
    background-color: #18181B;
    width: 10px;
    border: none;
}
QScrollBar::handle:vertical {
    background-color: #52525B;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background-color: #71717A;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    background-color: #18181B;
    height: 10px;
    border: none;
}
QScrollBar::handle:horizontal {
    background-color: #52525B;
    border-radius: 5px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background-color: #71717A;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
"""


if __name__ == '__main__':
    main()
