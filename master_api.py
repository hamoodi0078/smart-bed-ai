from __future__ import annotations

from datetime import datetime

from fastapi import FastAPI

from dana.dana_api import router as dana_router
from guest_mode.guest_api import router as guest_router
from islamic_mode.islamic_api import router as islamic_router
from master_controller import MasterController
from qr_code.qr_api import router as qr_router
from spotify.spotify_api import router as spotify_router


app = FastAPI(title="Danah Abu Halifa")

app.include_router(dana_router)
app.include_router(islamic_router)
app.include_router(spotify_router)
app.include_router(guest_router)
app.include_router(qr_router)


@app.get("/")
def root():
    return {
        "app": "Danah Abu Halifa",
        "version": "1.0.0",
        "status": "running",
        "dana": "ready",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/v1/system/status")
def system_status():
    controller = MasterController()
    return controller.get_system_status()
