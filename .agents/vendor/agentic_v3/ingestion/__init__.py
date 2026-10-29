"""
Ingestion Engine module for Markdown Specs parsing and ctags Symbol Mapping.
"""

from agentic_v3.ingestion.parse_specs import SpecParser
from agentic_v3.ingestion.ctags_indexer import CtagsIndexer

__all__ = ["SpecParser", "CtagsIndexer"]
