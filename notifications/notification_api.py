from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel

from notifications.expo_sender import ExpoPushSender
from notifications.notification_scheduler import NotificationScheduler
from notifications.whatsapp_notifier import WhatsAppNotifier
from tasks.notification_tasks import send_push_notification as _send_push_task


router = APIRouter(prefix="/v1/notifications", tags=["notifications"])

expo_sender = ExpoPushSender()
whatsapp_notifier = WhatsAppNotifier()
scheduler = NotificationScheduler(expo_sender=expo_sender, whatsapp_notifier=whatsapp_notifier)


class RegisterDeviceRequest(BaseModel):
    user_id: str
    expo_token: str
    platform: str = "android"


class SendNotificationRequest(BaseModel):
    user_id: str
    notification_type: str
    template_vars: dict = {}


class WindDownScheduleRequest(BaseModel):
    user_id: str
    hour: int = 21
    minute: int = 0


class AlarmScheduleRequest(BaseModel):
    user_id: str
    hour: int
    minute: int


class InactivityCheckRequest(BaseModel):
    user_id: str
    last_active_date: str
    threshold_days: int = 3


class StreakCheckRequest(BaseModel):
    user_id: str
    streak_days: int
    phone: str | None = None


@router.post("/register-device")
def register_device(request: RegisterDeviceRequest) -> dict:
    return expo_sender.register_token(
        user_id=request.user_id,
        expo_token=request.expo_token,
        platform=request.platform,
    )


@router.post("/send")
def send_notification(request: SendNotificationRequest) -> dict:
    job_id = str(uuid4())
    _send_push_task(
        user_id=request.user_id,
        notification_type=request.notification_type,
        template_vars=request.template_vars or {},
    )
    return {"task_id": job_id, "queued": True}


@router.get("/log/{user_id}")
def get_notification_log(user_id: str) -> dict:
    return {"user_id": user_id, "log": expo_sender.get_user_log(user_id)}


@router.post("/schedule/wind-down")
def schedule_wind_down(request: WindDownScheduleRequest) -> dict:
    scheduled = scheduler.schedule_wind_down(
        user_id=request.user_id,
        hour=request.hour,
        minute=request.minute,
    )
    return {"user_id": request.user_id, "wind_down": scheduled}


@router.post("/schedule/alarm")
def schedule_alarm(request: AlarmScheduleRequest) -> dict:
    scheduled = scheduler.schedule_alarm(
        user_id=request.user_id,
        hour=request.hour,
        minute=request.minute,
    )
    return {"user_id": request.user_id, "alarm": scheduled}


@router.get("/scheduled/{user_id}")
def get_scheduled_notifications(user_id: str) -> dict:
    return {"user_id": user_id, "scheduled": scheduler.get_scheduled(user_id)}


@router.post("/check/inactivity")
def check_inactivity(request: InactivityCheckRequest) -> dict:
    return scheduler.check_inactivity(
        user_id=request.user_id,
        last_active_date=request.last_active_date,
        threshold_days=request.threshold_days,
    )


@router.post("/check/streak")
def check_streak(request: StreakCheckRequest) -> dict:
    return scheduler.check_streak(
        user_id=request.user_id,
        streak_days=request.streak_days,
        phone=request.phone,
    )
