"""PyInstaller runtime hook: Force-load libtorrent DLLs BEFORE PyQt6.

libtorrent initializes OpenSSL on its background threads. If Qt (which also
uses OpenSSL) initializes first, the two conflict and cause a segfault.
This hook forces the libtorrent shared library to load first.
"""
# Just importing libtorrent forces the DLL/SO load and OpenSSL init.
# No need to create a session — that would open a port unnecessarily.
import libtorrent  # noqa: F401
