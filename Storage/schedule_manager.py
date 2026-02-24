import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional
from uuid import uuid4


SCHEDULE_PATH = Path("data/alarms.json")


@dataclass
class AlarmItem:
    id: str
    time_24h: str
    label: str
    enabled: bool
    next_trigger_iso: str
    repeat_days: str = ""


class ScheduleManager:
    def __init__(self):
        SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._alarms = self._load()

    def _load(self) -> List[AlarmItem]:
        if not SCHEDULE_PATH.exists():
            return []

        try:
            body = json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
            alarms = []
            for item in body:
                alarms.append(AlarmItem(**item))
            return alarms
        except Exception:
            return []

    def _save(self):
        payload = [asdict(alarm) for alarm in self._alarms]
        SCHEDULE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add_alarm(self, time_24h: str, label: str = "Alarm", repeat_days: str = "") -> AlarmItem:
        parsed_repeat = self._parse_repeat_days(repeat_days)
        if parsed_repeat:
            trigger = self._next_trigger_for_repeat(time_24h, parsed_repeat, datetime.now())
        else:
            trigger = self._next_trigger_datetime(time_24h)
        alarm = AlarmItem(
            id=uuid4().hex[:8],
            time_24h=time_24h,
            label=label,
            enabled=True,
            next_trigger_iso=trigger.isoformat(),
            repeat_days=repeat_days,
        )
        self._alarms.append(alarm)
        self._save()
        return alarm

    def list_alarms(self) -> List[AlarmItem]:
        return sorted(self._alarms, key=lambda a: a.next_trigger_iso)

    def remove_alarm(self, alarm_id: str) -> bool:
        before = len(self._alarms)
        self._alarms = [a for a in self._alarms if a.id != alarm_id]
        changed = len(self._alarms) != before
        if changed:
            self._save()
        return changed

    def pop_due_alarms(self, now: Optional[datetime] = None) -> List[AlarmItem]:
        now = now or datetime.now()
        due = []
        keep = []

        for alarm in self._alarms:
            try:
                trigger_dt = datetime.fromisoformat(alarm.next_trigger_iso)
            except ValueError:
                continue

            if alarm.enabled and trigger_dt <= now:
                due.append(alarm)
                repeat_days = self._parse_repeat_days(alarm.repeat_days)
                if repeat_days:
                    next_dt = self._next_trigger_for_repeat(alarm.time_24h, repeat_days, now)
                    alarm.next_trigger_iso = next_dt.isoformat()
                    keep.append(alarm)
                continue
            keep.append(alarm)

        if due:
            self._alarms = keep
            self._save()

        return due

    @staticmethod
    def _next_trigger_datetime(time_24h: str, now: Optional[datetime] = None) -> datetime:
        now = now or datetime.now()
        hour, minute = [int(x) for x in time_24h.split(":", 1)]
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate = candidate + timedelta(days=1)
        return candidate

    @staticmethod
    def _parse_repeat_days(value: str) -> List[int]:
        if not value:
            return []
        out = []
        for part in value.split(","):
            part = part.strip()
            if part.isdigit():
                d = int(part)
                if 0 <= d <= 6:
                    out.append(d)
        return sorted(set(out))

    @staticmethod
    def _next_trigger_for_repeat(time_24h: str, repeat_days: List[int], now: datetime) -> datetime:
        hour, minute = [int(x) for x in time_24h.split(":", 1)]
        base = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        for delta in range(0, 8):
            candidate = base + timedelta(days=delta)
            if candidate.weekday() in repeat_days and candidate > now:
                return candidate
        return base + timedelta(days=1)


def is_valid_time_24h(value: str) -> bool:
    try:
        hour, minute = [int(x) for x in value.strip().split(":", 1)]
        return 0 <= hour <= 23 and 0 <= minute <= 59
    except Exception:
        return False
