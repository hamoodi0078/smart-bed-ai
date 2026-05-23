# Router modules — each domain owns its routes and depends only on api/deps.py
from .health import router as health_router
from .metrics import router as metrics_router
from .islamic import router as islamic_router
from .auth import router as auth_router
from .alarms import router as alarms_router
from .sleep import router as sleep_router
from .scenes import router as scenes_router
from .subscriptions import router as subscriptions_router
from .spotify import router as spotify_router
from .devices import router as devices_router
from .profile import router as profile_router
from .chat import router as chat_router
from .integrations import router as integrations_router
from .reports import router as reports_router
from .admin import router as admin_router
from .automations import router as automations_router

__all__ = [
    "health_router",
    "metrics_router",
    "islamic_router",
    "auth_router",
    "alarms_router",
    "sleep_router",
    "scenes_router",
    "subscriptions_router",
    "spotify_router",
    "devices_router",
    "profile_router",
    "chat_router",
    "integrations_router",
    "reports_router",
    "admin_router",
    "automations_router",
]
