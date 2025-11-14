"""Route definitions for the routerless orchestrator."""

from enum import Enum


class Route(str, Enum):
    """Query routing destinations."""

    CHAT = "CHAT"
    SHELL = "SHELL"
    CACHED = "CACHED"
    PLANNER = "PLANNER"
