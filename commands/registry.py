from collections.abc import Callable, Iterable
from dataclasses import dataclass


Handler = Callable[[str], str]


@dataclass(frozen=True)
class CommandRoute:
    name: str
    handler: Handler
    aliases: tuple[str, ...]


_ROUTES: dict[str, CommandRoute] = {}


def _normalize_text(value: str) -> str:
    lowered = str(value or "").strip().lower()
    cleaned = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in lowered)
    return " ".join(cleaned.split())


def _contains_phrase(normalized_text: str, normalized_phrase: str) -> bool:
    if not normalized_text or not normalized_phrase:
        return False
    haystack = f" {normalized_text} "
    needle = f" {normalized_phrase} "
    return needle in haystack


def register(name: str, handler: Handler, aliases: Iterable[str] = ()) -> None:
    """Register or replace a command route by name.

    Matching is phrase-based over normalized text for the route name and aliases.
    """
    route_name = _normalize_text(name)
    if not route_name:
        raise ValueError("Command name cannot be empty")

    normalized_aliases: list[str] = []
    for alias in aliases:
        normalized = _normalize_text(alias)
        if normalized and normalized not in normalized_aliases:
            normalized_aliases.append(normalized)

    _ROUTES[route_name] = CommandRoute(
        name=route_name,
        handler=handler,
        aliases=tuple(normalized_aliases),
    )


def match(text: str) -> Handler | None:
    """Return the first matching command handler for user text, if any."""
    normalized = _normalize_text(text)
    if not normalized:
        return None

    for route in _ROUTES.values():
        if _contains_phrase(normalized, route.name):
            return route.handler
        for alias in route.aliases:
            if _contains_phrase(normalized, alias):
                return route.handler
    return None
