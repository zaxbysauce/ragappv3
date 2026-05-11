"""Chat mode enumeration for Instant/Thinking dispatch."""
from enum import Enum


class ChatMode(str, Enum):
    INSTANT = "instant"
    THINKING = "thinking"
