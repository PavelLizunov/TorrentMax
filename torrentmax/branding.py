"""Centralized branding constants — single source of truth for version.

Maps to VPNRouter.GUI/AppBranding.cs
"""


class AppBranding:
    """Application identity constants."""

    APP_NAME = "TorrentMax"
    PUBLISHER = "NiniTux"
    VERSION = "1.0.0"

    @classmethod
    def window_title(cls) -> str:
        return f"{cls.APP_NAME}  v{cls.VERSION}"

    @classmethod
    def tray_tooltip(cls) -> str:
        return f"{cls.APP_NAME} v{cls.VERSION}"

    @classmethod
    def user_agent(cls) -> str:
        return f"{cls.APP_NAME}/{cls.VERSION}"
