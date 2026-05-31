"""
Database archive system — moves old operational data to a separate archive database.
"""

from archive.manager import ArchiveManager

__all__ = ['ArchiveManager', 'get_archive_manager', 'init_archive']

_archive_manager = None


def init_archive(app):
    """Initialize archive database bind and manager."""
    global _archive_manager
    from archive.models import ensure_archive_tables
    ensure_archive_tables(app)
    config_path = app.config.get('ARCHIVE_CONFIG_PATH', 'archive/config.json')
    _archive_manager = ArchiveManager(config_path)
    return _archive_manager


def get_archive_manager():
    return _archive_manager
