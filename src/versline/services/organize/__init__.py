"""Cataloguing, duplicate detection and rule-based re-organization of large file archives.

Design: docs/fa/organize-design.md. Only the standard library (+ loguru) is used so the Windows bundle
needs no extra dependencies.
"""
from versline.services.organize.catalog import WORKSPACE_DIRNAME, Catalog, default_workspace_for
from versline.services.organize.dupes import duplicate_groups, find_duplicates, redundant_folders
from versline.services.organize.reports import export_files, write_duplicates, write_stats
from versline.services.organize.scanner import scan_sources
from versline.services.organize.rules import RuleSet, load_rules, load_taxonomy, parse_rules
from versline.services.organize.planner import build_plan, read_plan, write_plan, write_plan_summary
from versline.services.organize.applier import apply_plan, revert_moves, verify

__all__ = [
    "WORKSPACE_DIRNAME", "Catalog", "default_workspace_for", "scan_sources", "find_duplicates",
    "duplicate_groups", "redundant_folders", "write_stats", "write_duplicates", "export_files",
    "RuleSet", "load_rules", "load_taxonomy", "parse_rules", "build_plan", "read_plan", "write_plan",
    "write_plan_summary", "apply_plan", "revert_moves", "verify",
]
