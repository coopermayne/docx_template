import re
from typing import Tuple, Optional


class BatesDetector:
    """Detect Bates numbers from filenames."""

    # Common Bates patterns
    PATTERNS = [
        # ABC_001-ABC_050 or ABC001-ABC050
        r'([A-Z]{2,6})[\s_-]?(\d{3,6})[\s_-]+\1[\s_-]?(\d{3,6})',
        # ABC_001-050 (prefix + range)
        r'([A-Z]{2,6})[\s_-]?(\d{3,6})[\s_-]+(\d{3,6})',
        # 001-050 (numbers only range)
        r'(?:^|[_\s-])(\d{3,6})[\s_-]+(\d{3,6})(?:[_\s.-]|$)',
        # ABC_001 or ABC001 (single Bates)
        r'([A-Z]{2,6})[\s_-]?(\d{3,6})',
    ]

    def __init__(self):
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE)
            for p in self.PATTERNS
        ]

    def detect_from_filename(self, filename: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract Bates range from filename.

        Returns:
            Tuple of (bates_start, bates_end) or (None, None) if not detected
        """
        # Remove extension for cleaner matching
        name_without_ext = re.sub(r'\.[^.]+$', '', filename)

        for i, pattern in enumerate(self.compiled_patterns):
            match = pattern.search(name_without_ext)
            if match:
                groups = match.groups()

                if i == 0:
                    # Pattern: ABC_001-ABC_050
                    prefix = groups[0].upper()
                    return (f"{prefix}_{groups[1]}", f"{prefix}_{groups[2]}")
                elif i == 1:
                    # Pattern: ABC_001-050
                    prefix = groups[0].upper()
                    return (f"{prefix}_{groups[1]}", f"{prefix}_{groups[2]}")
                elif i == 2:
                    # Pattern: 001-050 (numbers only)
                    return (groups[0], groups[1])
                elif i == 3:
                    # Pattern: ABC_001 (single Bates)
                    prefix = groups[0].upper()
                    return (f"{prefix}_{groups[1]}", None)

        return (None, None)

    def format_bates_range(self, start: Optional[str], end: Optional[str]) -> str:
        """Format Bates range for display."""
        if not start:
            return ""
        if not end:
            return start
        return f"{start} - {end}"


# Global instance
bates_detector = BatesDetector()


def detect_bates(filename: str) -> Tuple[Optional[str], Optional[str]]:
    """Convenience function to detect Bates from filename."""
    return bates_detector.detect_from_filename(filename)
