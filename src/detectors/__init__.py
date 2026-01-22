"""Change detection for indexes and mutual funds."""
from .change_detector import MFChangeDetector, detect_index_changes

__all__ = ['MFChangeDetector', 'detect_index_changes']
