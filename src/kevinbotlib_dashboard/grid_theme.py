from dataclasses import dataclass
from enum import Enum


@dataclass
class ThemeOptions:
    background: str
    item_background: str
    foreground: str
    primary: str
    border: str
    padding: int = 4


class Themes(Enum):
    Dark = ThemeOptions(
        background="#1A1A1A",
        item_background="#2E2E2E",
        foreground="#E0E0E0",
        primary="#005C9F",
        border="#292929",
    )
