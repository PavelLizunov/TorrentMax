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

        # Title
        title = QLabel("MONITOR")
        title.setStyleSheet("font-weight: bold; font-size: 11px;")
        layout.addWidget(title)

        # Graphs row
        graphs_layout = QHBoxLayout()

        # Speed graph
        self._speed_plot = pg.PlotWidget(title="Speed")
        self._speed_plot.setBackground('#1e1e1e')
        self._speed_plot.showGrid(x=False, y=True, alpha=0.3)
        self._speed_plot.setYRange(0, 1024 * 1024)  # Initial 1 MB/s
        self._speed_plot.setMouseEnabled(x=False, y=False)
        self._speed_plot.hideAxis('bottom')
        self._speed_plot.setMaximumHeight(150)

        self._dl_curve = self._speed_plot.plot(pen=pg.mkPen('#2196F3', width=2))
        self._ul_curve = self._speed_plot.plot(pen=pg.mkPen('#4CAF50', width=2))
        graphs_layout.addWidget(self._speed_plot)

        # System graph (disk + CPU)
        self._sys_plot = pg.PlotWidget(title="System")
        self._sys_plot.setBackground('#1e1e1e')
        self._sys_plot.showGrid(x=False, y=True, alpha=0.3)
        self._sys_plot.setYRange(0, 100)
        self._sys_plot.setMouseEnabled(x=False, y=False)
        self._sys_plot.hideAxis('bottom')
        self._sys_plot.setMaximumHeight(150)

        self._disk_curve = self._sys_plot.plot(pen=pg.mkPen('#FF9800', width=2))
        self._cpu_curve = self._sys_plot.plot(pen=pg.mkPen('#F44336', width=2))
        graphs_layout.addWidget(self._sys_plot)

        layout.addLayout(graphs_layout)

        # Stats labels row
        stats_layout = QHBoxLayout()

        self._dl_label = QLabel("Download: 0 B/s")
        self._dl_label.setStyleSheet("color: #2196F3;")
        stats_layout.addWidget(self._dl_label)

        self._ul_label = QLabel("Upload: 0 B/s")
        self._ul_label.setStyleSheet("color: #4CAF50;")
        stats_layout.addWidget(self._ul_label)

        self._disk_label = QLabel("Disk: 0%")
        self._disk_label.setStyleSheet("color: #FF9800;")
        stats_layout.addWidget(self._disk_label)

        self._cpu_label = QLabel("CPU: 0%")
        self._cpu_label.setStyleSheet("color: #F44336;")
        stats_layout.addWidget(self._cpu_label)

        self._peers_label = QLabel("Peers: 0")
        stats_layout.addWidget(self._peers_label)

        stats_layout.addStretch()
        layout.addLayout(stats_layout)

        # Bottleneck display
        self._bottleneck_frame = QFrame()
        self._bottleneck_frame.setStyleSheet(
            "QFrame { background-color: #2d2d2d; border-radius: 4px; padding: 4px; }"
        )
        bn_layout = QVBoxLayout(self._bottleneck_frame)
        bn_layout.setContentsMargins(8, 4, 8, 4)
        self._bottleneck_label = QLabel("No bottlenecks detected")
        self._bottleneck_label.setWordWrap(True)
        self._bottleneck_label.setStyleSheet("font-size: 11px;")
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

        # Update labels
        self._dl_label.setText(f"Download: {format_speed(download_rate)}")
        self._ul_label.setText(f"Upload: {format_speed(upload_rate)}")
        self._disk_label.setText(f"Disk: {disk_pct:.0f}%")
        self._cpu_label.setText(f"CPU: {cpu_pct:.0f}%")
        self._peers_label.setText(f"Peers: {num_peers}")

        # Color warnings: red > 90%, orange > 70%, normal otherwise
        disk_color = '#F44336' if disk_pct > 90 else '#FF9800' if disk_pct > 70 else '#888888'
        self._disk_label.setStyleSheet(f"color: {disk_color};")

        cpu_color = '#F44336' if cpu_pct > 85 else '#FF9800' if cpu_pct > 60 else '#888888'
        self._cpu_label.setStyleSheet(f"color: {cpu_color};")

    def update_bottlenecks(self, bottlenecks: list[Bottleneck]):
        """Update the bottleneck display."""
        if not bottlenecks:
            self._bottleneck_label.setText("No bottlenecks detected")
            self._bottleneck_frame.setStyleSheet(
                "QFrame { background-color: #1b3a1b; border-radius: 4px; padding: 4px; }"
            )
            return

        # Show the most severe bottleneck
        worst = max(bottlenecks, key=lambda b: b.severity)
        lines = []
        for bn in bottlenecks:
            icon = "!!" if bn.severity > 0.7 else "!"
            lines.append(f"{icon} {bn.message} — {bn.suggestion}")

        self._bottleneck_label.setText("\n".join(lines))

        if worst.severity > 0.7:
            self._bottleneck_frame.setStyleSheet(
                "QFrame { background-color: #3a1b1b; border-radius: 4px; padding: 4px; }"
            )
        else:
            self._bottleneck_frame.setStyleSheet(
                "QFrame { background-color: #3a3a1b; border-radius: 4px; padding: 4px; }"
            )
