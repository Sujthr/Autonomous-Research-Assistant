"""Thin re-export of the llm_gatewayV3 client so agent modules import cleanly."""
from __future__ import annotations
import sys
from pathlib import Path

_GATEWAY = Path(__file__).parent / "5e4a8833-292d-4ce5-be97-749c7656bdbf" / "llm_gatewayV3"
if str(_GATEWAY) not in sys.path:
    sys.path.append(str(_GATEWAY))

from client import LLM, ask  # noqa: F401  re-exported

__all__ = ["LLM", "ask"]
