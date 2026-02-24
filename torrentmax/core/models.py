"""Update system data models.

Maps to VPNRouter.Core/Models/UpdateInfo.cs
"""

from dataclasses import dataclass


@dataclass
class UpdateInfo:
    """Metadata about an available update."""

    current_version: str
    latest_version: str
    download_url: str       # browser_download_url from GitHub
    release_notes: str      # Aggregated changelogs from all skipped versions
    html_url: str           # Link to GitHub release page
    size_bytes: int         # Expected asset size
    is_newer: bool
