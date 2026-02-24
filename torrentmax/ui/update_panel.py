"""Update notification bar — mirrors VPNRouter's _updatePanel.

Maps to the update panel section in VPNRouter.GUI/MainForm.cs (lines 269-317).
Amber-styled notification bar with status label, Update button, and progress bar.
"""

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton, QProgressBar,
)

from torrentmax.core.models import UpdateInfo


class UpdatePanel(QWidget):
    """Dockable update notification bar — shown when an update is available."""

    update_requested = pyqtSignal()  # Emitted when user clicks "Update"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setVisible(False)

        # Brand amber style — matches VPNRouter's update panel colors
        self.setStyleSheet(
            "UpdatePanel { background-color: #451A03; "
            "border-bottom: 1px solid #92400E; }"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 14, 0)
        layout.setSpacing(12)

        # Status label
        self._label = QLabel("")
        self._label.setStyleSheet(
            "color: #FDE68A; font-weight: bold; font-size: 12px; "
            "background: transparent; border: none;"
        )
        layout.addWidget(self._label, 1)

        # Progress bar (hidden by default)
        self._progress = QProgressBar()
        self._progress.setFixedWidth(200)
        self._progress.setFixedHeight(18)
        self._progress.setRange(0, 100)
        self._progress.setValue(0)
        self._progress.setVisible(False)
        self._progress.setStyleSheet(
            "QProgressBar { background-color: #27272A; border: 1px solid #92400E; "
            "border-radius: 4px; text-align: center; color: #FDE68A; font-size: 10px; } "
            "QProgressBar::chunk { background-color: #F59E0B; border-radius: 3px; }"
        )
        layout.addWidget(self._progress)

        # Update button — amber brand color
        self._btn = QPushButton("Update")
        self._btn.setFixedSize(90, 28)
        self._btn.setStyleSheet(
            "QPushButton { background-color: #F59E0B; color: #FFFFFF; "
            "font-weight: bold; border: none; border-radius: 4px; } "
            "QPushButton:hover { background-color: #D97706; } "
            "QPushButton:pressed { background-color: #B45309; }"
        )
        self._btn.clicked.connect(self.update_requested.emit)
        layout.addWidget(self._btn)

    def show_update(self, info: UpdateInfo):
        """Show update notification — maps to VPNRouter ShowUpdateNotification()."""
        size_mb = f"  ({info.size_bytes // 1024 // 1024} MB)" if info.size_bytes > 0 else ""
        self._label.setText(f"Update available: v{info.latest_version}{size_mb}")
        self._btn.setVisible(True)
        self._btn.setEnabled(True)
        self._progress.setVisible(False)
        self.setVisible(True)

    def set_progress(self, percent: int):
        """Update download progress bar."""
        self._btn.setVisible(False)
        self._progress.setVisible(True)
        self._progress.setValue(percent)

    def set_status(self, text: str):
        """Update status label text."""
        self._label.setText(text)

    def reset(self):
        """Reset to notification state (on error)."""
        self._btn.setVisible(True)
        self._btn.setEnabled(True)
        self._progress.setVisible(False)
        self._progress.setValue(0)

    def hide_panel(self):
        """Hide the panel entirely."""
        self.setVisible(False)
