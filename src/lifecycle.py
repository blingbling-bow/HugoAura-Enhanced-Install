"""
Global Application Lifecycle
"""

from __future__ import annotations

from typing import Any
import typeDefs.lifecycle as lifecycleTypes

callbacks: dict[str, Any | None] = {}
