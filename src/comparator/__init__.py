"""comparator - compare two directory trees and sync source -> target one way."""

from comparator.compare import CompareMode, build_plan, has_differences
from comparator.models import Action, Change, Entry, EntryKind
from comparator.scan import scan_tree
from comparator.sync import ApplyResult, apply_plan

__version__ = "0.2.0"

__all__ = [
    "Action",
    "ApplyResult",
    "Change",
    "CompareMode",
    "Entry",
    "EntryKind",
    "apply_plan",
    "build_plan",
    "has_differences",
    "scan_tree",
    "__version__",
]
