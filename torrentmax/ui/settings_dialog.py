"""Settings dialog."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QCheckBox, QPushButton, QFileDialog, QDialogButtonBox, QTabWidget,
    QWidget, QFormLayout,
)

from torrentmax.config.settings import AppSettings


class SettingsDialog(QDialog):
    """Application settings dialog with tabs."""

    def __init__(self, parent=None, settings: AppSettings = None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(450)
        self._settings = settings or AppSettings()

        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        tabs.addTab(self._create_general_tab(), "General")
        tabs.addTab(self._create_speed_tab(), "Speed")
        tabs.addTab(self._create_network_tab(), "Network")
        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _create_general_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        # Download path
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit(self._settings.download_path)
        path_layout.addWidget(self._path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse_path)
        path_layout.addWidget(browse_btn)
        form.addRow("Download path:", path_layout)

        # Minimize to tray
        self._tray_check = QCheckBox("Minimize to system tray on close")
        self._tray_check.setChecked(self._settings.minimize_to_tray)
        form.addRow(self._tray_check)

        # Start minimized
        self._start_min_check = QCheckBox("Start minimized")
        self._start_min_check.setChecked(self._settings.start_minimized)
        form.addRow(self._start_min_check)

        return widget

    def _create_speed_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        # Download limit (KB/s, 0 = unlimited)
        self._dl_limit = QSpinBox()
        self._dl_limit.setRange(0, 999999)
        self._dl_limit.setSuffix(" KB/s")
        self._dl_limit.setSpecialValueText("Unlimited")
        self._dl_limit.setValue(self._settings.max_download_rate // 1024)
        form.addRow("Max download speed:", self._dl_limit)

        # Upload limit
        self._ul_limit = QSpinBox()
        self._ul_limit.setRange(0, 999999)
        self._ul_limit.setSuffix(" KB/s")
        self._ul_limit.setSpecialValueText("Unlimited")
        self._ul_limit.setValue(self._settings.max_upload_rate // 1024)
        form.addRow("Max upload speed:", self._ul_limit)

        return widget

    def _create_network_tab(self) -> QWidget:
        widget = QWidget()
        form = QFormLayout(widget)

        # Listen port
        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(self._settings.listen_port)
        form.addRow("Listen port:", self._port_spin)

        # Auto profile
        self._auto_profile_check = QCheckBox("Automatically detect connection type")
        self._auto_profile_check.setChecked(self._settings.auto_profile)
        form.addRow(self._auto_profile_check)

        return widget

    def _browse_path(self):
        path = QFileDialog.getExistingDirectory(self, "Select download directory")
        if path:
            self._path_edit.setText(path)

    def get_settings(self) -> AppSettings:
        """Return updated settings."""
        self._settings.download_path = self._path_edit.text()
        self._settings.max_download_rate = self._dl_limit.value() * 1024
        self._settings.max_upload_rate = self._ul_limit.value() * 1024
        self._settings.listen_port = self._port_spin.value()
        self._settings.auto_profile = self._auto_profile_check.isChecked()
        self._settings.minimize_to_tray = self._tray_check.isChecked()
        self._settings.start_minimized = self._start_min_check.isChecked()
        return self._settings
