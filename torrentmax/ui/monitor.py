"""Monitoring widget — real-time graphs and bottleneck display."""

import collections

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
import pyqtgraph as pg

from torrentmax.core.torrent import format_speed
from torrentmax.core.tuner import Bottleneck

# Graph history — last 60 seconds
HISTORY_LEN = 60


class MonitorWidget(QWidget):
    """Real-time performance monitoring with graphs."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Data buffers
        self._dl_history = collections.deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self._ul_history = collections.deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self._disk_history = collections.deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)
        self._cpu_history = collections.deque([0.0] * HISTORY_LEN, maxlen=HISTORY_LEN)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Title — brand style
        title = QLabel("\u25CF MONITOR")
        title.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #A1A1AA; "
            "letter-spacing: 2px;"
        )
        layout.addWidget(title)

        # Graphs row
        graphs_layout = QHBoxLayout()

        # Speed graph — VPN brand blue/green
        self._speed_plot = pg.PlotWidget(title="Speed")
        self._speed_plot.setBackground('#18181B')
        self._speed_plot.showGrid(x=False, y=True, alpha=0.2)
        self._speed_plot.setYRange(0, 1024 * 1024)  # Initial 1 MB/s
        self._speed_plot.setMouseEnabled(x=False, y=False)
        self._speed_plot.hideAxis('bottom')
        self._speed_plot.setMaximumHeight(150)
        self._speed_plot.getAxis('left').setPen(pg.mkPen('#3F3F46'))
        self._speed_plot.getAxis('left').setTextPen(pg.mkPen('#71717A'))

        self._dl_curve = self._speed_plot.plot(pen=pg.mkPen('#3B82F6', width=2))
        self._ul_curve = self._speed_plot.plot(pen=pg.mkPen('#22C55E', width=2))
        graphs_layout.addWidget(self._speed_plot)

        # System graph (disk + CPU) — brand amber/red
        self._sys_plot = pg.PlotWidget(title="System")
        self._sys_plot.setBackground('#18181B')
        self._sys_plot.showGrid(x=False, y=True, alpha=0.2)
        self._sys_plot.setYRange(0, 100)
        self._sys_plot.setMouseEnabled(x=False, y=False)
        self._sys_plot.hideAxis('bottom')
        self._sys_plot.setMaximumHeight(150)
        self._sys_plot.getAxis('left').setPen(pg.mkPen('#3F3F46'))
        self._sys_plot.getAxis('left').setTextPen(pg.mkPen('#71717A'))

        self._disk_curve = self._sys_plot.plot(pen=pg.mkPen('#F59E0B', width=2))
        self._cpu_curve = self._sys_plot.plot(pen=pg.mkPen('#EF4444', width=2))
        graphs_layout.addWidget(self._sys_plot)

        layout.addLayout(graphs_layout)

        # Stats labels row — brand colors
        stats_layout = QHBoxLayout()

        self._dl_label = QLabel("\u25BC Download: 0 B/s")
        self._dl_label.setStyleSheet("color: #3B82F6; font-weight: bold;")
        stats_layout.addWidget(self._dl_label)

        self._ul_label = QLabel("\u25B2 Upload: 0 B/s")
        self._ul_label.setStyleSheet("color: #22C55E; font-weight: bold;")
        stats_layout.addWidget(self._ul_label)

        self._disk_label = QLabel("\u25CF Disk: 0%")
        self._disk_label.setStyleSheet("color: #F59E0B;")
        stats_layout.addWidget(self._disk_label)

        self._cpu_label = QLabel("\u25CF CPU: 0%")
        self._cpu_label.setStyleSheet("color: #EF4444;")
        stats_layout.addWidget(self._cpu_label)

        self._peers_label = QLabel("\u25CF Peers: 0")
        self._peers_label.setStyleSheet("color: #A1A1AA;")
        stats_layout.addWidget(self._peers_label)

        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # Bottleneck display — brand card style
        self._bottleneck_frame = QFrame()
        self._bottleneck_frame.setStyleSheet(
            "QFrame { background-color: #27272A; border: 1px solid #3F3F46; "
            "border-radius: 6px; padding: 4px; }"
        )
        bn_layout = QVBoxLayout(self._bottleneck_frame)
        bn_layout.setContentsMargins(10, 6, 10, 6)
        self._bottleneck_label = QLabel("\u2713 No bottlenecks detected")
        self._bottleneck_label.setWordWrap(True)
        self._bottleneck_label.setStyleSheet("font-size: 11px; color: #22C55E; border: none;")
        bn_layout.addWidget(self._bottleneck_label)
        layout.addWidget(self._bottleneck_frame)

    def update_stats(self, download_rate: float, upload_rate: float,
                     disk_pct: float, cpu_pct: float, num_peers: int):
        """Push new data point and update graphs."""
        self._dl_history.append(download_rate)
        self._ul_history.append(upload_rate)
        self._disk_history.append(disk_pct)
        self._cpu_history.append(cpu_pct)

        x = list(range(HISTORY_LEN))
        self._dl_curve.setData(x, list(self._dl_history))
        self._ul_curve.setData(x, list(self._ul_history))
        self._disk_curve.setData(x, list(self._disk_history))
        self._cpu_curve.setData(x, list(self._cpu_history))

        # Auto-scale speed graph
        max_speed = max(max(self._dl_history), max(self._ul_history), 1024)
        self._speed_plot.setYRange(0, max_speed * 1.1)

        # Update labels — brand style with icons
        self._dl_label.setText(f"\u25BC Download: {format_speed(download_rate)}")
        self._ul_label.setText(f"\u25B2 Upload: {format_speed(upload_rate)}")
        self._disk_label.setText(f"\u25CF Disk: {disk_pct:.0f}%")
        self._cpu_label.setText(f"\u25CF CPU: {cpu_pct:.0f}%")
        self._peers_label.setText(f"\u25CF Peers: {num_peers}")

        # Color warnings: brand colors (red > 90%, amber > 70%, zinc otherwise)
        disk_color = '#EF4444' if disk_pct > 90 else '#F59E0B' if disk_pct > 70 else '#71717A'
        self._disk_label.setStyleSheet(f"color: {disk_color};")

        cpu_color = '#EF4444' if cpu_pct > 85 else '#F59E0B' if cpu_pct > 60 else '#71717A'
        self._cpu_label.setStyleSheet(f"color: {cpu_color};")

    def update_bottlenecks(self, bottlenecks: list[Bottleneck]):
        """Update the bottleneck display — VPN brand styling."""
        if not bottlenecks:
            self._bottleneck_label.setText("\u2713 No bottlenecks detected")
            self._bottleneck_label.setStyleSheet("font-size: 11px; color: #22C55E; border: none;")
            self._bottleneck_frame.setStyleSheet(
                "QFrame { background-color: #14532D; border: 1px solid #166534; "
                "border-radius: 6px; padding: 4px; }"
            )
            return

        # Show the most severe bottleneck
        worst = max(bottlenecks, key=lambda b: b.severity)
        lines = []
        for bn in bottlenecks:
            icon = "\u26A0" if bn.severity > 0.7 else "\u25CF"
            lines.append(f"{icon} {bn.message} \u2014 {bn.suggestion}")

        self._bottleneck_label.setText("\n".join(lines))

        if worst.severity > 0.7:
            # Danger — brand red
            self._bottleneck_label.setStyleSheet("font-size: 11px; color: #FCA5A5; border: none;")
            self._bottleneck_frame.setStyleSheet(
                "QFrame { background-color: #7F1D1D; border: 1px solid #991B1B; "
                "border-radius: 6px; padding: 4px; }"
            )
        else:
            # Warning — brand amber
            self._bottleneck_label.setStyleSheet("font-size: 11px; color: #FDE68A; border: none;")
            self._bottleneck_frame.setStyleSheet(
                "QFrame { background-color: #451A03; border: 1px solid #92400E; "
                "border-radius: 6px; padding: 4px; }"
            )
