"""Auto-update system — GitHub Releases checker, downloader, and self-updater.

Maps to VPNRouter.Core/Services/UpdateChecker.cs

Architecture:
  UpdateChecker — pure Python logic (no Qt dependency), blocking methods
  UpdateWorker  — QThread wrapper with pyqtSignal for thread-safe UI updates
"""

import fnmatch
import json
import logging
import os
import shutil
import subprocess
import sys
import zipfile
from urllib.request import Request, urlopen
from urllib.error import URLError

from packaging.version import Version, InvalidVersion

from torrentmax.branding import AppBranding
from torrentmax.core.models import UpdateInfo

logger = logging.getLogger(__name__)

# Buffer size for streaming downloads (80 KB, same as VPNRouter)
DOWNLOAD_BUFFER = 81920


class UpdateChecker:
    """Checks GitHub Releases, downloads, stages, and applies updates.

    All methods are synchronous (blocking) — designed to run in a QThread.
    Maps to VPNRouter.Core.Services.UpdateChecker.
    """

    def __init__(self, github_repo: str, current_version: str,
                 staging_dir: str | None = None):
        self.github_repo = github_repo
        self.current_version = current_version
        self.staging_dir = staging_dir or os.path.join(
            os.environ.get('LOCALAPPDATA', '.'), 'TorrentMax', 'update-staging'
        )

    # ── Check ────────────────────────────────────────────────────────

    def check_for_update(self) -> UpdateInfo | None:
        """Query GitHub Releases API for newer versions.

        Maps to UpdateChecker.CheckForUpdateAsync() lines 36-109.
        Returns UpdateInfo if a newer version exists, None otherwise.
        """
        try:
            current = Version(self.current_version)
        except InvalidVersion:
            logger.error("Cannot parse current version: %s", self.current_version)
            return None

        url = f"https://api.github.com/repos/{self.github_repo}/releases?per_page=30"
        req = Request(url, headers={
            'User-Agent': AppBranding.user_agent(),
            'Accept': 'application/vnd.github+json',
        })

        try:
            with urlopen(req, timeout=30) as resp:
                releases = json.loads(resp.read().decode('utf-8'))
        except (URLError, OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to fetch releases: %s", e)
            return None

        if not isinstance(releases, list):
            return None

        # Filter & parse versions — identical to VPNRouter logic
        parsed_releases = []
        for r in releases:
            if r.get('draft') or r.get('prerelease'):
                continue
            tag = r.get('tag_name', '')
            ver_str = tag.lstrip('vV')
            try:
                ver = Version(ver_str)
            except InvalidVersion:
                continue
            if ver > current:
                parsed_releases.append((ver, r))

        if not parsed_releases:
            return None

        # Sort newest first
        parsed_releases.sort(key=lambda x: x[0], reverse=True)
        latest_ver, latest_release = parsed_releases[0]

        # Find matching asset: TorrentMax-v*.zip
        download_url = ""
        size_bytes = 0
        for asset in latest_release.get('assets', []):
            name = asset.get('name', '')
            if fnmatch.fnmatch(name.lower(), 'torrentmax-v*.zip'):
                download_url = asset.get('browser_download_url', '')
                size_bytes = asset.get('size', 0)
                break

        if not download_url:
            logger.warning("No matching ZIP asset in release v%s", latest_ver)
            return None

        # Aggregate changelogs from ALL skipped versions (newest first)
        # Maps to VPNRouter lines 93-98
        all_notes = []
        for _, r in parsed_releases:
            body = (r.get('body') or '').strip()
            if body:
                all_notes.append(body)
        combined_notes = "\n\n".join(all_notes)

        return UpdateInfo(
            current_version=self.current_version,
            latest_version=str(latest_ver),
            download_url=download_url,
            release_notes=combined_notes,
            html_url=latest_release.get('html_url', ''),
            size_bytes=size_bytes,
            is_newer=True,
        )

    # ── Download & Stage ─────────────────────────────────────────────

    def download_and_stage(self, info: UpdateInfo,
                           progress_callback=None,
                           status_callback=None) -> str:
        """Download update ZIP, validate, extract. Returns extracted dir path.

        Maps to UpdateChecker.DownloadAndStageAsync() lines 111-161.
        """
        # Clean staging dir
        if os.path.exists(self.staging_dir):
            shutil.rmtree(self.staging_dir, ignore_errors=True)
        os.makedirs(self.staging_dir, exist_ok=True)

        zip_path = os.path.join(self.staging_dir,
                                f"TorrentMax-v{info.latest_version}.zip")

        # Download with progress
        if status_callback:
            status_callback("Downloading update...")

        req = Request(info.download_url, headers={
            'User-Agent': AppBranding.user_agent(),
        })

        try:
            with urlopen(req, timeout=120) as resp:
                total = int(resp.headers.get('Content-Length', 0)) or info.size_bytes
                downloaded = 0
                with open(zip_path, 'wb') as f:
                    while True:
                        chunk = resp.read(DOWNLOAD_BUFFER)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total > 0 and progress_callback:
                            pct = min(int(downloaded * 100 / total), 100)
                            progress_callback(pct)
        except (URLError, OSError) as e:
            raise RuntimeError(f"Download failed: {e}") from e

        # Validate size — same 90% threshold as VPNRouter (line 147)
        actual_size = os.path.getsize(zip_path)
        if info.size_bytes > 0 and actual_size < info.size_bytes * 0.9:
            raise RuntimeError(
                f"Downloaded file too small "
                f"({actual_size // 1024 // 1024} MB vs "
                f"expected {info.size_bytes // 1024 // 1024} MB). "
                f"Download may be corrupted."
            )

        # Extract
        if status_callback:
            status_callback("Extracting update...")

        extract_dir = os.path.join(self.staging_dir, 'extracted')
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                zf.extractall(extract_dir)
        except zipfile.BadZipFile as e:
            raise RuntimeError(f"Invalid ZIP file: {e}") from e

        # Handle nested folder: if extracted dir contains a single subfolder
        # with TorrentMax.exe inside, use that as the root
        items = os.listdir(extract_dir)
        if (len(items) == 1
                and os.path.isdir(os.path.join(extract_dir, items[0]))
                and os.path.isfile(os.path.join(extract_dir, items[0], 'TorrentMax.exe'))):
            extract_dir = os.path.join(extract_dir, items[0])

        # Validate: TorrentMax.exe must exist
        exe_path = os.path.join(extract_dir, 'TorrentMax.exe')
        if not os.path.isfile(exe_path):
            raise RuntimeError(
                "Invalid update package: TorrentMax.exe not found."
            )

        if status_callback:
            status_callback("Update ready to apply.")

        logger.info("Update staged at %s", extract_dir)
        return extract_dir

    # ── Apply ────────────────────────────────────────────────────────

    def apply_update(self, extracted_dir: str):
        """Copy new files over current installation, handle locked files.

        Maps to UpdateChecker.ApplyUpdate() lines 199-239.

        On Windows, running .exe/.dll can be RENAMED but not overwritten.
        Pattern: try copy → on PermissionError → rename old to .bak → copy new.
        Then launch new exe and caller exits.
        """
        app_dir = os.path.dirname(sys.executable)
        gui_exe = os.path.join(app_dir, 'TorrentMax.exe')

        copied = 0
        renamed = 0

        for root, _dirs, files in os.walk(extracted_dir):
            for filename in files:
                src = os.path.join(root, filename)
                rel_path = os.path.relpath(src, extracted_dir)
                dest = os.path.join(app_dir, rel_path)

                dest_dir = os.path.dirname(dest)
                os.makedirs(dest_dir, exist_ok=True)

                try:
                    shutil.copy2(src, dest)
                    copied += 1
                except PermissionError:
                    # File is locked — rename old, then copy new
                    bak_path = dest + '.bak'
                    try:
                        if os.path.exists(bak_path):
                            os.remove(bak_path)
                    except OSError:
                        pass
                    try:
                        os.rename(dest, bak_path)
                        shutil.copy2(src, dest)
                        copied += 1
                        renamed += 1
                    except OSError as e:
                        logger.error("Failed to update file %s: %s", rel_path, e)

        logger.info("Update applied: %d files copied, %d renamed", copied, renamed)

        # Launch new exe (detached so it survives parent exit)
        subprocess.Popen(
            [gui_exe],
            cwd=app_dir,
            creationflags=(
                subprocess.DETACHED_PROCESS
                | subprocess.CREATE_NEW_PROCESS_GROUP
            ),
        )

    # ── Cleanup ──────────────────────────────────────────────────────

    def cleanup_staging_dir(self):
        """Delete staging dir and leftover .bak files from previous update.

        Maps to UpdateChecker.CleanupStagingDir() lines 169-188.
        Called on startup before checking for updates.
        """
        # Remove staging directory
        try:
            if os.path.exists(self.staging_dir):
                shutil.rmtree(self.staging_dir, ignore_errors=True)
        except OSError:
            pass

        # Clean up .bak files left from in-process update
        try:
            app_dir = os.path.dirname(sys.executable)
            for root, _dirs, files in os.walk(app_dir):
                for f in files:
                    if f.endswith('.bak'):
                        try:
                            os.remove(os.path.join(root, f))
                        except OSError:
                            pass
        except OSError:
            pass


# ── QThread Worker ───────────────────────────────────────────────────

# Import PyQt6 only when the worker is actually used (lazy import
# to keep UpdateChecker itself free of Qt dependency)

def _get_worker_class():
    """Lazy import to avoid PyQt6 at module level."""
    from PyQt6.QtCore import QThread, pyqtSignal

    class UpdateWorker(QThread):
        """Background worker for update operations.

        Emits signals that are automatically dispatched to the main thread.
        Maps to VPNRouter's event pattern: DownloadProgress, StatusChanged, etc.
        """

        # Signals — all thread-safe via Qt's signal/slot mechanism
        update_available = pyqtSignal(object)    # UpdateInfo
        download_progress = pyqtSignal(int)      # 0-100
        status_changed = pyqtSignal(str)         # Status message
        check_failed = pyqtSignal(str)           # Error (logged, not shown)
        download_finished = pyqtSignal(str)      # Path to extracted dir
        download_failed = pyqtSignal(str)        # Error message

        def __init__(self, checker: UpdateChecker, parent=None):
            super().__init__(parent)
            self._checker = checker
            self._mode: str = ""        # "check" or "download"
            self._info: UpdateInfo | None = None

        def check(self):
            """Start background update check."""
            self._mode = "check"
            self.start()

        def download(self, info: UpdateInfo):
            """Start background download."""
            self._mode = "download"
            self._info = info
            self.start()

        def run(self):
            """Thread entry point — dispatch to check or download."""
            if self._mode == "check":
                self._do_check()
            elif self._mode == "download":
                self._do_download()

        def _do_check(self):
            try:
                info = self._checker.check_for_update()
                if info and info.is_newer:
                    self.update_available.emit(info)
            except Exception as e:
                self.check_failed.emit(str(e))
                logger.warning("Update check failed: %s", e)

        def _do_download(self):
            if not self._info:
                return
            try:
                extracted = self._checker.download_and_stage(
                    self._info,
                    progress_callback=self.download_progress.emit,
                    status_callback=self.status_changed.emit,
                )
                self.download_finished.emit(extracted)
            except Exception as e:
                self.download_failed.emit(str(e))
                logger.error("Update download failed: %s", e)

    return UpdateWorker


# Module-level accessor
_UpdateWorkerClass = None


def get_update_worker_class():
    """Get the UpdateWorker class (lazy-imported to avoid PyQt6 at import time)."""
    global _UpdateWorkerClass
    if _UpdateWorkerClass is None:
        _UpdateWorkerClass = _get_worker_class()
    return _UpdateWorkerClass
