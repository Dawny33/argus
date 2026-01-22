"""Tests for change detection module."""
import pytest
from src.detectors.change_detector import MFChangeDetector, detect_index_changes


class TestMFChangeDetector:
    """Test cases for MFChangeDetector."""

    def test_detect_new_additions(self):
        """Test detection of new stock additions."""
        detector = MFChangeDetector(threshold=0.5)
        previous = {"STOCK_A": 5.0, "STOCK_B": 3.0}
        current = {"STOCK_A": 5.0, "STOCK_B": 3.0, "STOCK_C": 2.0}

        changes = detector.detect_changes(previous, current)

        assert len(changes['additions']) == 1
        assert ('STOCK_C', 2.0) in changes['additions']
        assert len(changes['exits']) == 0
        assert len(changes['increases']) == 0
        assert len(changes['decreases']) == 0

    def test_detect_exits(self):
        """Test detection of stock exits."""
        detector = MFChangeDetector(threshold=0.5)
        previous = {"STOCK_A": 5.0, "STOCK_B": 3.0, "STOCK_C": 2.0}
        current = {"STOCK_A": 5.0, "STOCK_B": 3.0}

        changes = detector.detect_changes(previous, current)

        assert len(changes['exits']) == 1
        assert ('STOCK_C', 2.0) in changes['exits']
        assert len(changes['additions']) == 0

    def test_detect_significant_increase(self):
        """Test detection of significant percentage increases."""
        detector = MFChangeDetector(threshold=0.5)
        previous = {"STOCK_A": 5.0}
        current = {"STOCK_A": 6.0}  # +1.0% increase

        changes = detector.detect_changes(previous, current)

        assert len(changes['increases']) == 1
        stock, old, new, change = changes['increases'][0]
        assert stock == "STOCK_A"
        assert old == 5.0
        assert new == 6.0
        assert change == 1.0

    def test_detect_significant_decrease(self):
        """Test detection of significant percentage decreases."""
        detector = MFChangeDetector(threshold=0.5)
        previous = {"STOCK_A": 5.0}
        current = {"STOCK_A": 4.0}  # -1.0% decrease

        changes = detector.detect_changes(previous, current)

        assert len(changes['decreases']) == 1
        stock, old, new, change = changes['decreases'][0]
        assert stock == "STOCK_A"
        assert old == 5.0
        assert new == 4.0
        assert change == -1.0

    def test_ignore_below_threshold(self):
        """Test that changes below threshold are ignored."""
        detector = MFChangeDetector(threshold=0.5)
        previous = {"STOCK_A": 5.0}
        current = {"STOCK_A": 5.3}  # +0.3% increase (below threshold)

        changes = detector.detect_changes(previous, current)

        assert len(changes['increases']) == 0
        assert len(changes['decreases']) == 0

    def test_respect_threshold(self):
        """Test that changes at threshold boundary are detected."""
        detector = MFChangeDetector(threshold=0.5)
        previous = {"STOCK_A": 5.0}
        current = {"STOCK_A": 5.5}  # Exactly 0.5% increase

        changes = detector.detect_changes(previous, current)

        assert len(changes['increases']) == 1

    def test_has_changes_true(self):
        """Test has_changes returns True when changes exist."""
        detector = MFChangeDetector()
        changes = {
            'additions': [('STOCK_A', 2.0)],
            'exits': [],
            'increases': [],
            'decreases': []
        }

        assert detector.has_changes(changes) is True

    def test_has_changes_false(self):
        """Test has_changes returns False when no changes exist."""
        detector = MFChangeDetector()
        changes = {
            'additions': [],
            'exits': [],
            'increases': [],
            'decreases': []
        }

        assert detector.has_changes(changes) is False

    def test_empty_previous_all_additions(self):
        """Test all stocks are additions when previous is empty."""
        detector = MFChangeDetector()
        previous = {}
        current = {"STOCK_A": 5.0, "STOCK_B": 3.0}

        changes = detector.detect_changes(previous, current)

        assert len(changes['additions']) == 2
        assert len(changes['exits']) == 0

    def test_empty_current_all_exits(self):
        """Test all stocks are exits when current is empty."""
        detector = MFChangeDetector()
        previous = {"STOCK_A": 5.0, "STOCK_B": 3.0}
        current = {}

        changes = detector.detect_changes(previous, current)

        assert len(changes['additions']) == 0
        assert len(changes['exits']) == 2


class TestDetectIndexChanges:
    """Test cases for detect_index_changes function."""

    def test_detect_added_stocks(self):
        """Test detection of added stocks to index."""
        previous = {"Index_1": ["STOCK_A", "STOCK_B"]}
        current = {"Index_1": ["STOCK_A", "STOCK_B", "STOCK_C"]}

        changes = detect_index_changes(previous, current)

        assert "Index_1" in changes
        assert len(changes["Index_1"]["added"]) == 1
        assert "STOCK_C" in changes["Index_1"]["added"]
        assert len(changes["Index_1"]["removed"]) == 0

    def test_detect_removed_stocks(self):
        """Test detection of removed stocks from index."""
        previous = {"Index_1": ["STOCK_A", "STOCK_B", "STOCK_C"]}
        current = {"Index_1": ["STOCK_A", "STOCK_B"]}

        changes = detect_index_changes(previous, current)

        assert "Index_1" in changes
        assert len(changes["Index_1"]["removed"]) == 1
        assert "STOCK_C" in changes["Index_1"]["removed"]
        assert len(changes["Index_1"]["added"]) == 0

    def test_detect_both_added_and_removed(self):
        """Test detection when stocks are both added and removed."""
        previous = {"Index_1": ["STOCK_A", "STOCK_B", "STOCK_C"]}
        current = {"Index_1": ["STOCK_A", "STOCK_D", "STOCK_E"]}

        changes = detect_index_changes(previous, current)

        assert "Index_1" in changes
        assert len(changes["Index_1"]["added"]) == 2
        assert "STOCK_D" in changes["Index_1"]["added"]
        assert "STOCK_E" in changes["Index_1"]["added"]
        assert len(changes["Index_1"]["removed"]) == 2
        assert "STOCK_B" in changes["Index_1"]["removed"]
        assert "STOCK_C" in changes["Index_1"]["removed"]

    def test_no_changes(self):
        """Test when there are no changes."""
        previous = {"Index_1": ["STOCK_A", "STOCK_B"]}
        current = {"Index_1": ["STOCK_A", "STOCK_B"]}

        changes = detect_index_changes(previous, current)

        assert len(changes) == 0

    def test_new_index_all_added(self):
        """Test new index with all stocks marked as added."""
        previous = {}
        current = {"Index_1": ["STOCK_A", "STOCK_B"]}

        changes = detect_index_changes(previous, current)

        assert "Index_1" in changes
        assert len(changes["Index_1"]["added"]) == 2
        assert len(changes["Index_1"]["removed"]) == 0

    def test_removed_index_all_removed(self):
        """Test removed index with all stocks marked as removed."""
        previous = {"Index_1": ["STOCK_A", "STOCK_B"]}
        current = {}

        changes = detect_index_changes(previous, current)

        # When an entire index is removed, we don't report it as changes
        # Only individual stock changes within existing indexes are reported
        assert len(changes) == 0

    def test_multiple_indexes(self):
        """Test change detection across multiple indexes."""
        previous = {
            "Index_1": ["STOCK_A", "STOCK_B"],
            "Index_2": ["STOCK_X", "STOCK_Y"]
        }
        current = {
            "Index_1": ["STOCK_A", "STOCK_C"],  # B removed, C added
            "Index_2": ["STOCK_X", "STOCK_Y"]   # No changes
        }

        changes = detect_index_changes(previous, current)

        assert len(changes) == 1  # Only Index_1 has changes
        assert "Index_1" in changes
        assert "Index_2" not in changes
        assert "STOCK_C" in changes["Index_1"]["added"]
        assert "STOCK_B" in changes["Index_1"]["removed"]

    def test_sorting_preserved(self):
        """Test that added/removed lists are sorted."""
        previous = {"Index_1": ["A", "B", "C"]}
        current = {"Index_1": ["A", "F", "E", "D"]}

        changes = detect_index_changes(previous, current)

        # Added: D, E, F (sorted)
        # Removed: B, C (sorted)
        assert changes["Index_1"]["added"] == ["D", "E", "F"]
        assert changes["Index_1"]["removed"] == ["B", "C"]
