"""Service registry for dependency management and service discovery."""

from __future__ import annotations

import logging
from typing import Any, TypeVar, Generic

from core.errors import ConfigurationError

logger = logging.getLogger("service_registry")

T = TypeVar("T")


class ServiceRegistry:
    """Central registry for application services with type safety and lifecycle management."""

    def __init__(self) -> None:
        self._services: dict[str, Any] = {}
        self._initialized: set[str] = set()

    def register(self, name: str, service: Any) -> None:
        """Register a service by name.

        Args:
            name: Unique service identifier
            service: Service instance to register

        Raises:
            ConfigurationError: If service name is already registered
        """
        if name in self._services:
            logger.warning("Service '%s' already registered, overwriting", name)
        
        self._services[name] = service
        self._initialized.add(name)
        logger.info("Registered service: %s (%s)", name, type(service).__name__)

    def get(self, name: str) -> Any:
        """Retrieve a service by name.

        Args:
            name: Service identifier

        Returns:
            The registered service instance

        Raises:
            ConfigurationError: If service is not registered
        """
        if name not in self._services:
            raise ConfigurationError(
                key=name,
                message=f"Service '{name}' not initialized. Available: {list(self._services.keys())}",
            )
        return self._services[name]

    def get_optional(self, name: str) -> Any | None:
        """Retrieve a service by name, returning None if not found.

        Args:
            name: Service identifier

        Returns:
            The registered service instance or None
        """
        return self._services.get(name)

    def has(self, name: str) -> bool:
        """Check if a service is registered.

        Args:
            name: Service identifier

        Returns:
            True if service is registered
        """
        return name in self._services

    def list_services(self) -> list[str]:
        """Get list of all registered service names.

        Returns:
            List of service names
        """
        return list(self._services.keys())

    def clear(self) -> None:
        """Clear all registered services (useful for testing)."""
        count = len(self._services)
        self._services.clear()
        self._initialized.clear()
        logger.info("Cleared %d services from registry", count)

    def health_check(self) -> dict[str, bool]:
        """Check health status of registered services.

        Returns:
            Dict mapping service names to health status
        """
        health = {}
        for name, service in self._services.items():
            if hasattr(service, "health_check"):
                try:
                    health[name] = bool(service.health_check())
                except Exception as exc:
                    logger.warning("Health check failed for %s: %s", name, exc)
                    health[name] = False
            else:
                health[name] = True
        return health


_global_registry: ServiceRegistry | None = None


def get_global_registry() -> ServiceRegistry:
    """Get or create the global service registry.

    Returns:
        Global ServiceRegistry instance
    """
    global _global_registry
    if _global_registry is None:
        _global_registry = ServiceRegistry()
    return _global_registry


def reset_global_registry() -> None:
    """Reset the global registry (for testing)."""
    global _global_registry
    _global_registry = None
