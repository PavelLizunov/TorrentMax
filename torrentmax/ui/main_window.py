"""Main application window."""

import os
import logging

import psutil
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QToolBar, QStatusBar, QTableWidget, QTableWidgetItem, QHeaderView,
    QLabel, QComboBox, QMenu, QSystemTrayIcon, QFileDialog, QMessageBox,
    QAbstractItemView, QApplication,
)

import libtorrent as lt

from torrentmax.core.engine import TorrentEngine
from torrentmax.core.torrent import TorrentStatus, TorrentState, format_size, format_speed, format_eta
from torrentmax.core.tuner import AutoTuner
from torrentmax.config.settings import AppSettings
from torrentmax.network.detector import NetworkDetector, VpnDetector
from torrentmax.ui.add_torrent import AddTorrentDialog
from torrentmax.ui.monitor import MonitorWidget
from torrentmax.ui.settings_dialog import SettingsDialog

logger = logging.getLogger(__name__)

# Column indices
COL_NAME = 0
COL_SIZE = 1
COL_PROGRESS = 2
COL_STATUS = 3
COL_SPEED_DOWN = 4
COL_SPEED_UP = 5
COL_PEERS = 6
COL_ETA = 7
NUM_COLS = 8

COLUMN_HEADERS = ['Name', 'Size', 'Progress', 'Status', 'Down', 'Up', 'Peers', 'ETA']


class MainWindow(QMainWindow):
    """TorrentMax main window."""

    def __init__(self, engine: TorrentEngine, tuner: AutoTuner, settings: AppSettings):
        super().__init__()
        self._engine = engine
        self._tuner = tuner
        self._settings = settings
        self._info_hash_rows: dict[str, int] = {}  # info_hash -> row index
        self._force_quit = False
        self._shutting_down = False  # Prevents timer callbacks during shutdown

        # Warm up psutil.cpu_percent (first call always returns 0.0)
        psutil.cpu_percent(interval=None)

        self._setup_ui()
        self._setup_tray()
        self._setup_timers()

    def _setup_ui(self):
        self.setWindowTitle('TorrentMax  v1.0.0')
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        # Central layout
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)

        # Brand header
        header = self._create_brand_header()
        layout.addWidget(header)

        # Toolbar
        self._toolbar = self._create_toolbar()
        self.addToolBar(self._toolbar)

        # Info bar (with padding)
        info_container = QWidget()
        info_container.setContentsMargins(8, 6, 8, 2)
        info_inner = QVBoxLayout(info_container)
        info_inner.setContentsMargins(8, 6, 8, 2)
        info_bar = self._create_info_bar()
        info_inner.addLayout(info_bar)
        layout.addWidget(info_container)

        # Splitter: torrent table + monitor (with padding)
        splitter = QSplitter(Qt.Orientation.Vertical)

        # Torrent table
        self._table = self._create_table()
        splitter.addWidget(self._table)

        # Monitor widget
        self._monitor = MonitorWidget()
        splitter.addWidget(self._monitor)

        splitter.setSizes([400, 200])
        splitter.setContentsMargins(8, 4, 8, 4)
        layout.addWidget(splitter)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Ready")
        self._status_bar.addWidget(self._status_label, 1)

        # Context menu for table
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

    def _create_brand_header(self) -> QWidget:
        """VPNRouter-style branded header panel."""
        header = QWidget()
        header.setFixedHeight(56)
        header.setStyleSheet(
            "QWidget { background-color: #27272A; border-bottom: 1px solid #3F3F46; }"
        )
        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(16, 8, 16, 8)

        # App name in brand blue
        name_label = QLabel("TorrentMax")
        name_label.setStyleSheet(
            "font-size: 18px; font-weight: bold; color: #3B82F6; background: transparent; border: none;"
        )
        h_layout.addWidget(name_label)

        # Version
        ver_label = QLabel("v1.0.0")
        ver_label.setStyleSheet(
            "font-size: 12px; color: #71717A; margin-left: 8px; background: transparent; border: none;"
        )
        h_layout.addWidget(ver_label)

        h_layout.addStretch()

        # Publisher tag
        pub_label = QLabel("by NiniTux")
        pub_label.setStyleSheet(
            "font-size: 11px; color: #52525B; font-style: italic; background: transparent; border: none;"
        )
        h_layout.addWidget(pub_label)

        return header

    def _create_toolbar(self) -> QToolBar:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        toolbar.setIconSize(toolbar.iconSize())

        self._act_add = QAction("\u2795 Torrent", self)
        self._act_add.setShortcut("Ctrl+O")
        self._act_add.triggered.connect(self._on_add_torrent)
        toolbar.addAction(self._act_add)

        self._act_add_magnet = QAction("\U0001F517 Magnet", self)
        self._act_add_magnet.setShortcut("Ctrl+M")
        self._act_add_magnet.triggered.connect(self._on_add_magnet)
        toolbar.addAction(self._act_add_magnet)

        toolbar.addSeparator()

        self._act_resume = QAction("\u25B6 Resume", self)
        self._act_resume.triggered.connect(self._on_resume)
        toolbar.addAction(self._act_resume)

        self._act_pause = QAction("\u23F8 Pause", self)
        self._act_pause.triggered.connect(self._on_pause)
        toolbar.addAction(self._act_pause)

        self._act_remove = QAction("\u2716 Remove", self)
        self._act_remove.setShortcut("Delete")
        self._act_remove.triggered.connect(self._on_remove)
        toolbar.addAction(self._act_remove)

        toolbar.addSeparator()

        self._act_settings = QAction("\u2699 Settings", self)
        self._act_settings.setShortcut("Ctrl+,")
        self._act_settings.triggered.connect(self._on_settings)
        toolbar.addAction(self._act_settings)

        toolbar.addSeparator()

        self._act_quit = QAction("\u2B1B Quit", self)
        self._act_quit.setShortcut("Ctrl+Q")
        self._act_quit.triggered.connect(self._force_quit_app)
        toolbar.addAction(self._act_quit)

        return toolbar

    def _create_info_bar(self) -> QHBoxLayout:
        layout = QHBoxLayout()

        # Profile selector
        layout.addWidget(QLabel("Profile:"))
        self._profile_combo = QComboBox()
        self._profile_combo.addItems(["Auto", "WiFi", "LAN", "VPN"])
        self._profile_combo.currentTextChanged.connect(self._on_profile_changed)
        layout.addWidget(self._profile_combo)

        layout.addSpacing(20)

        # Connection info
        self._conn_label = QLabel("Connection: --")
        layout.addWidget(self._conn_label)

        self._vpn_label = QLabel("VPN: --")
        layout.addWidget(self._vpn_label)

        layout.addStretch()

        # Global speed labels — VPN brand colors
        self._global_down_label = QLabel("\u25BC 0 B/s")
        self._global_down_label.setStyleSheet("font-weight: bold; color: #3B82F6; font-size: 12px;")
        layout.addWidget(self._global_down_label)

        self._global_up_label = QLabel("\u25B2 0 B/s")
        self._global_up_label.setStyleSheet("font-weight: bold; color: #22C55E; font-size: 12px;")
        layout.addWidget(self._global_up_label)

        return layout

    def _create_table(self) -> QTableWidget:
        table = QTableWidget(0, NUM_COLS)
        table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(True)

        header = table.horizontalHeader()
        header.setSectionResizeMode(COL_NAME, QHeaderView.ResizeMode.Stretch)
        for col in range(1, NUM_COLS):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)

        return table

    def _setup_tray(self):
        self._tray = QSystemTrayIcon(self)
        tray_menu = QMenu()
        tray_menu.addAction("Show", self._show_from_tray)
        tray_menu.addSeparator()
        tray_menu.addAction("Quit", self._force_quit_app)
        self._tray.setContextMenu(tray_menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.setToolTip("TorrentMax v1.0.0")
        self._tray.show()

    def _setup_timers(self):
        # UI refresh — 1 second
        self._refresh_timer = QTimer(self)
        self._refresh_timer.timeout.connect(self._refresh_ui)
        self._refresh_timer.start(1000)

        # Network detection — 30 seconds
        self._network_timer = QTimer(self)
        self._network_timer.timeout.connect(self._detect_network)
        self._network_timer.start(30000)
        self._detect_network()  # Initial detection

        # Alert processing — 500ms
        self._alert_timer = QTimer(self)
        self._alert_timer.timeout.connect(self._process_alerts)
        self._alert_timer.start(500)

    def _stop_timers(self):
        """Stop all timers and set shutdown flag."""
        self._shutting_down = True
        self._refresh_timer.stop()
        self._network_timer.stop()
        self._alert_timer.stop()

    # --- Actions ---

    def _on_add_torrent(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select .torrent file", "",
            "Torrent files (*.torrent);;All files (*)"
        )
        if not path:
            return
        # Ask where to save
        save_path = QFileDialog.getExistingDirectory(
            self, "Save torrent to...", self._settings.download_path
        )
        if not save_path:
            return
        self._add_torrent_source(path, save_path)

    def _on_add_magnet(self):
        dialog = AddTorrentDialog(self, self._settings.download_path)
        if dialog.exec():
            magnet = dialog.get_magnet()
            save_path = dialog.get_save_path()
            if magnet:
                self._add_torrent_source(magnet, save_path)

    def _add_torrent_source(self, source: str, save_path: str | None = None):
        if save_path is None:
            save_path = self._settings.download_path
        handle = self._engine.add_torrent(source, save_path, self._settings.data_dir)
        if handle:
            self._engine.save_torrent_list(self._settings.data_dir)

    def _on_resume(self):
        if not self._engine.is_running:
            return
        for ih in self._get_selected_hashes():
            handle = self._engine.handles.get(ih)
            if handle and handle.is_valid():
                handle.resume()

    def _on_pause(self):
        if not self._engine.is_running:
            return
        for ih in self._get_selected_hashes():
            handle = self._engine.handles.get(ih)
            if handle and handle.is_valid():
                handle.pause()

    def _on_remove(self):
        hashes = self._get_selected_hashes()
        if not hashes:
            return

        # Capture shift state NOW (before dialog steals focus)
        shift_held = bool(QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier)

        if shift_held:
            msg = f"Remove {len(hashes)} torrent(s) AND delete files?"
        else:
            msg = f"Remove {len(hashes)} torrent(s)? (files will be kept)"

        reply = QMessageBox.question(
            self, "Remove torrents", msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            for ih in hashes:
                self._engine.remove_torrent(ih, delete_files=shift_held)
            self._engine.save_torrent_list(self._settings.data_dir)

    def _on_settings(self):
        dialog = SettingsDialog(self, self._settings)
        if dialog.exec():
            self._settings = dialog.get_settings()
            self._settings.save()
            self._apply_speed_limits()

    def _on_profile_changed(self, text: str):
        profile_map = {"Auto": None, "WiFi": "wifi", "LAN": "lan", "VPN": "vpn"}
        profile = profile_map.get(text)
        self._tuner.set_manual_profile(profile)
        self._settings.auto_profile = (profile is None)
        self._settings.manual_profile = profile or ""

    def _show_context_menu(self, pos):
        menu = QMenu()
        menu.addAction("Resume", self._on_resume)
        menu.addAction("Pause", self._on_pause)
        menu.addSeparator()
        menu.addAction("Remove", self._on_remove)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    # --- Refresh ---

    def _refresh_ui(self):
        """Update the torrent table and global stats."""
        if self._shutting_down or not self._engine.is_running:
            return

        session_stats = self._engine.get_session_stats()

        # Update global speed
        self._global_down_label.setText(f"\u25BC {format_speed(session_stats.get('download_rate', 0))}")
        self._global_up_label.setText(f"\u25B2 {format_speed(session_stats.get('upload_rate', 0))}")

        # Build status list — catch errors from invalid handles
        statuses: list[TorrentStatus] = []
        for ih, handle in self._engine.handles.items():
            try:
                if handle.is_valid():
                    statuses.append(TorrentStatus.from_handle(handle))
            except Exception:
                pass

        # Sync table rows
        current_hashes = {s.info_hash for s in statuses}
        old_hashes = set(self._info_hash_rows.keys())

        # Remove gone torrents — rebuild index once after all removals
        removed = old_hashes - current_hashes
        if removed:
            for ih in removed:
                row = self._info_hash_rows.pop(ih, None)
                if row is not None:
                    self._table.removeRow(row)
            # Rebuild entire index after removals (rows shifted)
            self._info_hash_rows = {}
            for r in range(self._table.rowCount()):
                item = self._table.item(r, COL_NAME)
                if item:
                    self._info_hash_rows[item.data(Qt.ItemDataRole.UserRole)] = r

        # Add new / update existing
        for status in statuses:
            if status.info_hash not in self._info_hash_rows:
                row = self._table.rowCount()
                self._table.insertRow(row)
                self._info_hash_rows[status.info_hash] = row
                # Set info_hash as user data on name column
                name_item = QTableWidgetItem(status.name)
                name_item.setData(Qt.ItemDataRole.UserRole, status.info_hash)
                self._table.setItem(row, COL_NAME, name_item)
                for col in range(1, NUM_COLS):
                    self._table.setItem(row, col, QTableWidgetItem(""))

            row = self._info_hash_rows[status.info_hash]
            self._table.item(row, COL_NAME).setText(status.name)
            self._table.item(row, COL_SIZE).setText(format_size(status.total_size))
            self._table.item(row, COL_PROGRESS).setText(f"{status.progress * 100:.1f}%")
            self._table.item(row, COL_STATUS).setText(status.state.value)
            self._table.item(row, COL_SPEED_DOWN).setText(format_speed(status.download_rate))
            self._table.item(row, COL_SPEED_UP).setText(format_speed(status.upload_rate))
            self._table.item(row, COL_PEERS).setText(f"{status.num_seeds}/{status.num_peers}")
            self._table.item(row, COL_ETA).setText(format_eta(status.eta_seconds))

        # Update monitor
        try:
            disk_usage = psutil.disk_usage(self._settings.download_path).percent
        except Exception:
            disk_usage = 0.0
        cpu_pct = psutil.cpu_percent(interval=None)

        self._monitor.update_stats(
            download_rate=session_stats.get('download_rate', 0),
            upload_rate=session_stats.get('upload_rate', 0),
            disk_pct=disk_usage,
            cpu_pct=cpu_pct,
            num_peers=session_stats.get('num_peers', 0),
        )

        # Bottleneck analysis
        bottlenecks = self._tuner.analyze_bottlenecks(session_stats, disk_usage, cpu_pct)
        self._monitor.update_bottlenecks(bottlenecks)
        self._tuner.apply_dynamic_adjustments(bottlenecks)

        # Status bar
        active = sum(1 for s in statuses if s.state == TorrentState.DOWNLOADING)
        self._status_label.setText(
            f"Torrents: {len(statuses)} | Active: {active} | "
            f"Profile: {self._tuner.current_profile} | "
            f"DHT: {session_stats.get('dht_nodes', 0)} nodes"
        )

    def _detect_network(self):
        """Periodically detect network type."""
        if self._shutting_down:
            return
        conn_type = NetworkDetector.get_type()
        vpn = VpnDetector.is_active()
        self._conn_label.setText(f"Connection: {conn_type.upper()}")
        self._vpn_label.setText(f"VPN: {'Active' if vpn else 'Off'}")

        if self._settings.auto_profile:
            self._tuner.detect_and_apply()

    def _process_alerts(self):
        """Process libtorrent alerts."""
        if self._shutting_down or not self._engine.is_running:
            return
        for alert in self._engine.process_alerts():
            try:
                if isinstance(alert, lt.save_resume_data_alert):
                    ih = str(alert.handle.info_hash())
                    resume_dir = os.path.join(self._settings.data_dir, 'resume')
                    os.makedirs(resume_dir, exist_ok=True)
                    path = os.path.join(resume_dir, f'{ih}.fastresume')
                    with open(path, 'wb') as f:
                        f.write(lt.bencode(lt.write_resume_data(alert)))
                elif isinstance(alert, lt.torrent_error_alert):
                    logger.error("Torrent error: %s", alert.message())
            except Exception as e:
                logger.warning("Alert processing error: %s", e)

    def _apply_speed_limits(self):
        """Apply speed limits from settings."""
        self._engine.apply_settings({
            'download_rate_limit': self._settings.max_download_rate,
            'upload_rate_limit': self._settings.max_upload_rate,
        })

    # --- Helpers ---

    def _get_selected_hashes(self) -> list[str]:
        """Return info hashes of selected rows."""
        hashes = []
        for index in self._table.selectionModel().selectedRows():
            item = self._table.item(index.row(), COL_NAME)
            if item:
                ih = item.data(Qt.ItemDataRole.UserRole)
                if ih:
                    hashes.append(ih)
        return hashes

    def _force_quit_app(self):
        """Force quit — bypasses minimize-to-tray."""
        self._force_quit = True
        self.close()

    def _show_from_tray(self):
        self.showNormal()
        self.activateWindow()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_from_tray()

    def _quit_app(self):
        """Cleanly shut down: stop timers, save state, quit app."""
        if self._shutting_down:
            return  # Already shutting down
        # 1. Stop all timers and set guard flag
        self._stop_timers()

        # 2. Process any remaining queued events (drain pending timer callbacks)
        QApplication.processEvents()

        # 3. Save state and stop engine
        try:
            self._settings.save()
            self._engine.save_torrent_list(self._settings.data_dir)
            self._engine.stop(self._settings.data_dir)
        except Exception as e:
            logger.error("Error during shutdown: %s", e)

        # 4. Hide tray icon and quit
        self._tray.hide()
        QApplication.quit()

    def closeEvent(self, event):
        if self._settings.minimize_to_tray and not self._force_quit:
            event.ignore()
            self.hide()
        else:
            event.accept()
            self._quit_app()
