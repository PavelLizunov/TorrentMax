"""Add torrent dialog — magnet link input."""

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QDialogButtonBox,
)


class AddTorrentDialog(QDialog):
    """Dialog for adding a torrent via magnet link."""

    def __init__(self, parent=None, default_save_path: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Add Magnet Link")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        # Magnet link input
        layout.addWidget(QLabel("Magnet link:"))
        self._magnet_edit = QLineEdit()
        self._magnet_edit.setPlaceholderText("magnet:?xt=urn:btih:...")
        layout.addWidget(self._magnet_edit)

        # Save path
        layout.addWidget(QLabel("Save to:"))
        path_layout = QHBoxLayout()
        self._path_edit = QLineEdit(default_save_path)
        path_layout.addWidget(self._path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)
        layout.addLayout(path_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._validate_and_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Try to paste from clipboard
        from PyQt6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        if clipboard:
            text = clipboard.text()
            if text and text.strip().startswith('magnet:'):
                self._magnet_edit.setText(text.strip())

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Select download directory")
        if path:
            self._path_edit.setText(path)

    def _validate_and_accept(self):
        magnet = self._magnet_edit.text().strip()
        if not magnet.startswith('magnet:'):
            self._magnet_edit.setFocus()
            return
        self.accept()

    def get_magnet(self) -> str:
        return self._magnet_edit.text().strip()

    def get_save_path(self) -> str:
        return self._path_edit.text().strip()
