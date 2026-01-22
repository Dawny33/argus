#!/usr/bin/env python3
"""
Change Detector Module
Detects changes in portfolio holdings (mutual funds and indexes).
"""

import logging
from typing import Dict, List, Set

# Setup module-level logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MFChangeDetector:
    """
    Detect changes in mutual fund holdings.

    Tracks:
    - New additions (stocks not in previous holdings)
    - Complete exits (stocks removed from portfolio)
    - Significant increases (≥threshold% increase)
    - Significant decreases (≥threshold% decrease)
    """

    def __init__(self, threshold: float = 0.5):
        """
        Initialize the MFChangeDetector.

        Args:
            threshold: Minimum percentage point change to report (default: 0.5)
        """
        self.threshold = threshold

    def detect_changes(self, previous: Dict[str, float],
                       current: Dict[str, float]) -> Dict[str, List]:
        """
        Compare previous and current holdings.

        Args:
            previous: Previous month's holdings {stock: %}
            current: Current month's holdings {stock: %}

        Returns:
            Dict with keys:
            - 'additions': [(stock, pct), ...]
            - 'exits': [(stock, old_pct), ...]
            - 'increases': [(stock, old_pct, new_pct, change), ...]
            - 'decreases': [(stock, old_pct, new_pct, change), ...]
        """

        changes = {
            'additions': [],
            'exits': [],
            'increases': [],
            'decreases': []
        }

        prev_stocks = set(previous.keys())
        curr_stocks = set(current.keys())

        # New additions (not in previous)
        for stock in curr_stocks - prev_stocks:
            changes['additions'].append((stock, current[stock]))

        # Complete exits (not in current)
        for stock in prev_stocks - curr_stocks:
            changes['exits'].append((stock, previous[stock]))

        # Rebalances (present in both)
        for stock in prev_stocks & curr_stocks:
            old_pct = previous[stock]
            new_pct = current[stock]
            change = new_pct - old_pct

            # Only report if change meets threshold
            if abs(change) >= self.threshold:
                entry = (stock, old_pct, new_pct, change)

                if change > 0:
                    changes['increases'].append(entry)
                else:
                    changes['decreases'].append(entry)

        return changes

    def has_changes(self, changes: Dict[str, List]) -> bool:
        """
        Check if any changes were detected.

        Args:
            changes: Changes dict from detect_changes()

        Returns:
            True if any changes exist, False otherwise
        """
        return any(len(v) > 0 for v in changes.values())


def detect_index_changes(previous: Dict[str, List[str]],
                         current: Dict[str, List[str]]) -> Dict[str, Dict[str, List[str]]]:
    """
    Detect changes between previous and current index constituents.

    Args:
        previous: Previous state {index_name: [constituents]}
        current: Current state {index_name: [constituents]}

    Returns:
        Dict mapping index names to changes:
        {
            'index_name': {
                'added': [symbols],
                'removed': [symbols]
            }
        }
    """
    changes = {}

    for index in current.keys():
        prev_set = set(previous.get(index, []))
        curr_set = set(current[index])

        added = curr_set - prev_set
        removed = prev_set - curr_set

        if added or removed:
            changes[index] = {
                'added': sorted(list(added)),
                'removed': sorted(list(removed))
            }

    logger.info(f"Detected changes in {len(changes)} index(es)")
    return changes
