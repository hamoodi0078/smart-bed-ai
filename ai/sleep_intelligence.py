from datetime import datetime


class SleepIntelligenceEngine:
    def ensure_shape(self, profile: dict):
        profile.setdefault("preferences", {})
        profile["preferences"].setdefault("morning_brief_last_date", "")
        profile["preferences"].setdefault("evening_brief_last_date", "")
        profile["preferences"].setdefault("sleep_target_hours", 8.0)

        profile.setdefault("sleep", {})
        sleep = profile["sleep"]
        sleep.setdefault("bedtime_history", [])
        sleep.setdefault("wake_history", [])
        sleep.setdefault("recovery_mode", False)
        sleep.setdefault("recovery_reason", "")
        sleep.setdefault("challenge_level", 1)
        sleep.setdefault("challenge_last_adjust_date", "")
        sleep.setdefault("wind_down_enabled", False)
        sleep.setdefault("wind_down_minutes", 45)
        sleep.setdefault("night_wake_count", 0)
        sleep.setdefault("last_night_wake_date", "")
        sleep.setdefault("last_decompression_date", "")
        sleep.setdefault("last_weekly_insights_date", "")
        sleep.setdefault("last_bedtime_drift_alert_date", "")
        sleep.setdefault("last_recovery_score_card_date", "")
        sleep.setdefault("partner_mode", {})
        partner_mode = sleep["partner_mode"] if isinstance(sleep.get("partner_mode"), dict) else {}
        partner_mode.setdefault("enabled", False)
        partner_mode.setdefault(
            "profiles",
            [
                {"name": "Partner 1", "wake_style": "gentle"},
                {"name": "Partner 2", "wake_style": "balanced"},
            ],
        )
        if not isinstance(partner_mode.get("profiles"), list) or len(partner_mode.get("profiles", [])) < 2:
            partner_mode["profiles"] = [
                {"name": "Partner 1", "wake_style": "gentle"},
                {"name": "Partner 2", "wake_style": "balanced"},
            ]
        sleep["partner_mode"] = partner_mode

    def _recent_sleep_durations(self, profile: dict, max_nights: int = 7) -> list[float]:
        self.ensure_shape(profile)
        sleep = profile.get("sleep", {})
        bed_hist = sleep.get("bedtime_history", [])
        wake_hist = sleep.get("wake_history", [])
        pairs = min(len(bed_hist), len(wake_hist))
        out = []
        for idx in range(1, pairs + 1):
            try:
                bed = datetime.fromisoformat(str(bed_hist[-idx]))
                wake = datetime.fromisoformat(str(wake_hist[-idx]))
                if wake <= bed:
                    continue
                dur_h = (wake - bed).total_seconds() / 3600.0
                if 2.0 <= dur_h <= 16.0:
                    out.append(dur_h)
                if len(out) >= max_nights:
                    break
            except Exception:
                continue
        return out

    def _recent_bed_minutes(self, profile: dict, max_nights: int = 14) -> list[int]:
        self.ensure_shape(profile)
        out = []
        for iso_text in profile.get("sleep", {}).get("bedtime_history", [])[-max_nights:]:
            try:
                dt = datetime.fromisoformat(iso_text)
                out.append(dt.hour * 60 + dt.minute)
            except Exception:
                continue
        return out

    def record_bedtime_now(self, profile: dict) -> str:
        self.ensure_shape(profile)
        now = datetime.now().isoformat(timespec="seconds")
        hist = profile["sleep"]["bedtime_history"]
        hist.append(now)
        profile["sleep"]["bedtime_history"] = hist[-60:]
        return f"Bedtime logged at {now}."

    def record_wake_now(self, profile: dict) -> str:
        self.ensure_shape(profile)
        now = datetime.now().isoformat(timespec="seconds")
        hist = profile["sleep"]["wake_history"]
        hist.append(now)
        profile["sleep"]["wake_history"] = hist[-60:]
        return f"Wake time logged at {now}."

    def estimate_bedtime_window(self, profile: dict) -> str:
        self.ensure_shape(profile)
        history = profile["sleep"].get("bedtime_history", [])
        if not history:
            return "22:30-23:00"

        minutes = []
        for iso_text in history[-14:]:
            try:
                dt = datetime.fromisoformat(iso_text)
                minutes.append(dt.hour * 60 + dt.minute)
            except Exception:
                continue

        if not minutes:
            return "22:30-23:00"

        avg = int(sum(minutes) / len(minutes))
        start = max(0, avg - 20)
        end = min(23 * 60 + 59, avg + 20)
        return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"

    def should_send_morning_brief(self, profile: dict, now: datetime = None) -> bool:
        self.ensure_shape(profile)
        now = now or datetime.now()
        if not (5 <= now.hour <= 11):
            return False
        return profile["preferences"].get("morning_brief_last_date", "") != now.date().isoformat()

    def should_send_evening_brief(self, profile: dict, now: datetime = None) -> bool:
        self.ensure_shape(profile)
        now = now or datetime.now()
        if not (18 <= now.hour <= 23):
            return False
        return profile["preferences"].get("evening_brief_last_date", "") != now.date().isoformat()

    def mark_morning_brief_sent(self, profile: dict, now: datetime = None):
        self.ensure_shape(profile)
        now = now or datetime.now()
        profile["preferences"]["morning_brief_last_date"] = now.date().isoformat()

    def mark_evening_brief_sent(self, profile: dict, now: datetime = None):
        self.ensure_shape(profile)
        now = now or datetime.now()
        profile["preferences"]["evening_brief_last_date"] = now.date().isoformat()

    def evaluate_recovery_mode(self, profile: dict, active_goals_count: int):
        self.ensure_shape(profile)
        progress = profile.get("progress", {})
        created = max(0, int(progress.get("goals_created", 0)))
        completed = max(0, int(progress.get("goals_completed", 0)))
        streak = max(0, int(progress.get("current_streak_days", 0)))
        completion_rate = (completed / created * 100.0) if created else 0.0

        recovery_on = created >= 4 and completion_rate < 35 and streak == 0 and active_goals_count >= 3
        sleep = profile["sleep"]

        if recovery_on:
            sleep["recovery_mode"] = True
            sleep["recovery_reason"] = "Low completion trend with high active load."
            return True, sleep["recovery_reason"]

        if sleep.get("recovery_mode") and completion_rate >= 50 and streak >= 2:
            sleep["recovery_mode"] = False
            sleep["recovery_reason"] = ""

        return bool(sleep.get("recovery_mode")), str(sleep.get("recovery_reason", ""))

    def adjust_challenge_level(self, profile: dict, recent_misses: int, current_streak_days: int):
        self.ensure_shape(profile)
        sleep = profile["sleep"]
        level = max(1, min(5, int(sleep.get("challenge_level", 1))))
        today = datetime.now().date().isoformat()
        last_adjust = str(sleep.get("challenge_last_adjust_date", ""))

        if last_adjust == today:
            return level

        if recent_misses >= 2:
            level = max(1, level - 1)
            sleep["challenge_last_adjust_date"] = today
        elif current_streak_days >= 4:
            level = min(5, level + 1)
            sleep["challenge_last_adjust_date"] = today

        sleep["challenge_level"] = level
        return level

    def challenge_guidance(self, profile: dict) -> str:
        self.ensure_shape(profile)
        level = max(1, min(5, int(profile["sleep"].get("challenge_level", 1))))
        if level <= 1:
            return "Challenge ladder level 1: mini routine only (lights down + one 10-minute wind-down action)."
        if level == 2:
            return "Challenge ladder level 2: mini routine + fixed bedtime target window."
        if level == 3:
            return "Challenge ladder level 3: full bedtime routine + one next-day prep action."
        if level == 4:
            return "Challenge ladder level 4: full routine + no-screen buffer before bed."
        return "Challenge ladder level 5: full routine + no-screen buffer + morning consistency check."

    def build_recovery_protocol(self, profile: dict) -> str:
        self.ensure_shape(profile)
        if not profile["sleep"].get("recovery_mode"):
            return "Recovery mode is off."
        return (
            "Recovery mode is active: simplify to one tonight goal, one weekly goal, "
            "and one 10-minute action before sleep."
        )

    def build_morning_brief(
        self,
        profile: dict,
        top_goals: str,
        progress_report: str,
        dream_insights: str = "",
    ) -> str:
        window = self.estimate_bedtime_window(profile)
        dream_line = ""
        if dream_insights and not dream_insights.lower().startswith("no dream journal"):
            dream_line = f" {dream_insights}"
        return (
            f"Good morning. Focus goals: {top_goals}. {progress_report} "
            f"Suggested bedtime window tonight: {window}.{dream_line}"
        )

    def build_evening_brief(self, profile: dict, top_goals: str, progress_report: str) -> str:
        window = self.estimate_bedtime_window(profile)
        recovery_note = ""
        if profile.get("sleep", {}).get("recovery_mode"):
            recovery_note = " Recovery mode is active: keep tasks minimal tonight."
        challenge_note = " " + self.challenge_guidance(profile)
        return (
            f"Evening briefing: top goals now are {top_goals}. {progress_report} "
            f"Best bedtime window: {window}.{recovery_note}{challenge_note}"
        )

    def summary_line(self, profile: dict) -> str:
        self.ensure_shape(profile)
        window = self.estimate_bedtime_window(profile)
        recovery = "on" if profile.get("sleep", {}).get("recovery_mode") else "off"
        level = int(profile.get("sleep", {}).get("challenge_level", 1))
        consistency = self.sleep_consistency_score(profile)
        return (
            f"Sleep intelligence: window={window}, recovery_mode={recovery}, "
            f"challenge_level={level}. {consistency}"
        )

    def build_wind_down_autopilot(self, profile: dict, minutes: int = 45) -> str:
        self.ensure_shape(profile)
        mins = max(10, min(120, int(minutes)))
        profile["sleep"]["wind_down_enabled"] = True
        profile["sleep"]["wind_down_minutes"] = mins
        window = self.estimate_bedtime_window(profile)
        return (
            f"Wind-down autopilot enabled for {mins} minute(s). "
            f"Plan: warm dim lights, breathing rhythm, and low-stimulus audio. "
            f"Tonight target window: {window}."
        )

    def disable_wind_down_autopilot(self, profile: dict) -> str:
        self.ensure_shape(profile)
        profile["sleep"]["wind_down_enabled"] = False
        return "Wind-down autopilot disabled."

    def night_wake_recovery_protocol(self, profile: dict) -> str:
        self.ensure_shape(profile)
        today = datetime.now().date().isoformat()
        sleep = profile["sleep"]
        if sleep.get("last_night_wake_date") != today:
            sleep["last_night_wake_date"] = today
            sleep["night_wake_count"] = int(sleep.get("night_wake_count", 0)) + 1
        return (
            "Night wake recovery mode: lights set very low, voice pacing slowed. "
            "Do 6 rounds of inhale 4s / exhale 6s. Avoid checking phone, and I will keep responses short and calm."
        )

    def sleep_consistency_score(self, profile: dict) -> str:
        self.ensure_shape(profile)
        minutes = self._recent_bed_minutes(profile, max_nights=14)
        if len(minutes) < 3:
            return "Consistency score: collecting data (need at least 3 bedtime logs)."

        diffs = [abs(minutes[i] - minutes[i - 1]) for i in range(1, len(minutes))]
        avg_diff = sum(diffs) / max(1, len(diffs))
        score = max(0, min(100, int(round(100 - avg_diff * 1.3))))
        return f"Consistency score: {score}/100 (average bedtime shift {avg_diff:.0f} min)."

    def sleep_quality_score(self, profile: dict) -> str:
        self.ensure_shape(profile)
        target = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)
        durations = self._recent_sleep_durations(profile, max_nights=7)
        if len(durations) < 2:
            return "Sleep quality score: collecting data (log bedtime and wake for at least 2 nights)."

        avg_duration = sum(durations) / len(durations)
        duration_gap = max(0.0, target - avg_duration)
        duration_score = max(0, min(100, int(round(100 - duration_gap * 30))))

        bed_minutes = self._recent_bed_minutes(profile, max_nights=14)
        if len(bed_minutes) >= 3:
            diffs = [abs(bed_minutes[i] - bed_minutes[i - 1]) for i in range(1, len(bed_minutes))]
            avg_shift = sum(diffs) / max(1, len(diffs))
            consistency_score = max(0, min(100, int(round(100 - avg_shift * 1.3))))
        else:
            avg_shift = None
            consistency_score = 60

        sleep = profile.get("sleep", {})
        night_wakes = max(0, int(sleep.get("night_wake_count", 0) or 0))
        wake_penalty = min(25, night_wakes * 4)
        wake_score = max(0, 100 - wake_penalty)

        debt_hours = max(0.0, target * len(durations) - sum(durations))
        debt_score = max(0, min(100, int(round(100 - min(40, debt_hours * 8)))))

        total_score = int(
            round(
                duration_score * 0.45
                + consistency_score * 0.30
                + wake_score * 0.10
                + debt_score * 0.15
            )
        )
        total_score = max(0, min(100, total_score))

        reasons = []
        if duration_gap >= 0.5:
            reasons.append(f"average sleep is {avg_duration:.1f}h vs target {target:.1f}h")
        if avg_shift is not None and avg_shift >= 35:
            reasons.append(f"bedtime shift is {avg_shift:.0f} min")
        if night_wakes > 0:
            reasons.append(f"night wakes logged: {night_wakes}")
        if debt_hours >= 1.0:
            reasons.append(f"estimated sleep debt is {debt_hours:.1f}h")
        if not reasons:
            reasons.append("you are close to your sleep target and schedule")

        why_line = "; ".join(reasons[:2])
        return f"Sleep quality score: {total_score}/100. Why: {why_line}."

    def bedtime_drift_alert(self, profile: dict, threshold_minutes: int = 45) -> str:
        self.ensure_shape(profile)
        history = profile.get("sleep", {}).get("bedtime_history", [])[-7:]
        if len(history) < 4:
            return "Predictive bedtime drift: collecting data (need at least 4 bedtime logs)."

        bed_minutes = []
        for iso_text in history:
            try:
                dt = datetime.fromisoformat(str(iso_text))
                bed_minutes.append(dt.hour * 60 + dt.minute)
            except Exception:
                continue
        if len(bed_minutes) < 4:
            return "Predictive bedtime drift: collecting data (need at least 4 bedtime logs)."

        signed_deltas = []
        abs_deltas = []
        for idx in range(1, len(bed_minutes)):
            delta = bed_minutes[idx] - bed_minutes[idx - 1]
            if delta > 720:
                delta -= 1440
            elif delta < -720:
                delta += 1440
            signed_deltas.append(delta)
            abs_deltas.append(abs(delta))

        if not signed_deltas:
            return "Predictive bedtime drift: not enough trend data yet."

        avg_signed = sum(signed_deltas) / len(signed_deltas)
        avg_abs = sum(abs_deltas) / len(abs_deltas)
        threshold = max(20, int(threshold_minutes))
        if avg_abs < threshold or avg_signed < max(12, threshold * 0.45):
            return (
                f"Predictive bedtime drift: schedule looks stable (average shift {avg_abs:.0f} min). "
                "Keep your current wind-down timing."
            )

        suggested_earlier = max(15, min(45, int(round(avg_signed * 0.6))))
        target_window = self.estimate_bedtime_window(profile)
        return (
            f"Predictive alert: bedtime is drifting later by about {avg_signed:.0f} min/night "
            f"(average shift {avg_abs:.0f} min). "
            f"Start wind-down {suggested_earlier} minutes earlier tonight and target {target_window}."
        )

    def should_send_bedtime_drift_alert(self, profile: dict, now: datetime = None) -> bool:
        self.ensure_shape(profile)
        now = now or datetime.now()
        if not (17 <= now.hour <= 23):
            return False
        if profile.get("sleep", {}).get("last_bedtime_drift_alert_date", "") == now.date().isoformat():
            return False
        return self.bedtime_drift_alert(profile).startswith("Predictive alert:")

    def mark_bedtime_drift_alert_sent(self, profile: dict, now: datetime = None):
        self.ensure_shape(profile)
        now = now or datetime.now()
        profile["sleep"]["last_bedtime_drift_alert_date"] = now.date().isoformat()

    def should_send_weekly_recovery_score_card(self, profile: dict, now: datetime = None) -> bool:
        self.ensure_shape(profile)
        now = now or datetime.now()
        if not (18 <= now.hour <= 23):
            return False

        durations = self._recent_sleep_durations(profile, max_nights=7)
        if len(durations) < 4:
            return False

        last_date_raw = str(profile.get("sleep", {}).get("last_recovery_score_card_date", "") or "").strip()
        if not last_date_raw:
            return True

        try:
            last_date = datetime.fromisoformat(last_date_raw).date()
        except ValueError:
            return True

        return (last_date.isocalendar().year, last_date.isocalendar().week) != (
            now.date().isocalendar().year,
            now.date().isocalendar().week,
        )

    def mark_weekly_recovery_score_card_sent(self, profile: dict, now: datetime = None):
        self.ensure_shape(profile)
        now = now or datetime.now()
        profile["sleep"]["last_recovery_score_card_date"] = now.date().isoformat()

    def _normalize_wake_style(self, style: str) -> str:
        text = str(style or "").strip().lower()
        if text in {"soft", "calm", "quiet", "slow"}:
            return "gentle"
        if text in {"high", "strong", "fast", "energetic", "energy"}:
            return "energizing"
        if text in {"gentle", "balanced", "energizing"}:
            return text
        return "balanced"

    def set_partner_mode_enabled(self, profile: dict, enabled: bool) -> str:
        self.ensure_shape(profile)
        profile["sleep"]["partner_mode"]["enabled"] = bool(enabled)
        if enabled:
            return "Partner Sleep Mode enabled. I will use conflict-safe routines for both sleepers."
        return "Partner Sleep Mode disabled."

    def set_partner_profile(self, profile: dict, slot: int, name: str = "", wake_style: str = "") -> str:
        self.ensure_shape(profile)
        idx = max(0, min(1, int(slot)))
        profiles = profile["sleep"]["partner_mode"]["profiles"]
        while len(profiles) < 2:
            profiles.append({"name": f"Partner {len(profiles) + 1}", "wake_style": "balanced"})

        entry = profiles[idx]
        if name:
            clean_name = str(name).strip()[:32]
            if clean_name:
                entry["name"] = clean_name
        if wake_style:
            entry["wake_style"] = self._normalize_wake_style(wake_style)
        profiles[idx] = entry
        profile["sleep"]["partner_mode"]["profiles"] = profiles
        return (
            f"Partner {idx + 1} updated: name={entry.get('name', f'Partner {idx + 1}')}, "
            f"wake_style={entry.get('wake_style', 'balanced')}."
        )

    def partner_conflict_safe_routine(self, profile: dict) -> str:
        self.ensure_shape(profile)
        partner = profile["sleep"].get("partner_mode", {})
        profiles = partner.get("profiles", [])
        p1 = profiles[0] if len(profiles) > 0 else {"name": "Partner 1", "wake_style": "gentle"}
        p2 = profiles[1] if len(profiles) > 1 else {"name": "Partner 2", "wake_style": "balanced"}
        s1 = self._normalize_wake_style(p1.get("wake_style", "balanced"))
        s2 = self._normalize_wake_style(p2.get("wake_style", "balanced"))
        n1 = str(p1.get("name", "Partner 1") or "Partner 1")
        n2 = str(p2.get("name", "Partner 2") or "Partner 2")

        if {s1, s2} == {"gentle", "energizing"}:
            return (
                f"Conflict-safe routine: staged wake. Start with dim lights and low audio for {n1} ({s1}), "
                f"then after 12 minutes ramp to brighter lights and optional energizing audio for {n2} ({s2})."
            )
        if s1 == s2:
            return (
                f"Conflict-safe routine: unified wake style '{s1}' for {n1} and {n2}. "
                "Apply equal light ramp and shared audio level."
            )
        return (
            f"Conflict-safe routine: blended wake. Start at balanced intensity for both, "
            f"then bias settings toward {n1} ({s1}) and {n2} ({s2}) with side-safe brightness limits."
        )

    def partner_mode_status(self, profile: dict) -> str:
        self.ensure_shape(profile)
        partner = profile["sleep"].get("partner_mode", {})
        enabled = bool(partner.get("enabled", False))
        profiles = partner.get("profiles", [])
        p1 = profiles[0] if len(profiles) > 0 else {"name": "Partner 1", "wake_style": "gentle"}
        p2 = profiles[1] if len(profiles) > 1 else {"name": "Partner 2", "wake_style": "balanced"}
        state = "on" if enabled else "off"
        return (
            f"Partner Sleep Mode is {state}. "
            f"P1={p1.get('name', 'Partner 1')}({self._normalize_wake_style(p1.get('wake_style', 'balanced'))}), "
            f"P2={p2.get('name', 'Partner 2')}({self._normalize_wake_style(p2.get('wake_style', 'balanced'))}). "
            f"{self.partner_conflict_safe_routine(profile)}"
        )

    def weekly_recovery_score_card(self, profile: dict) -> str:
        self.ensure_shape(profile)
        profile["sleep"]["last_recovery_score_card_date"] = datetime.now().date().isoformat()
        target = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)
        durations = self._recent_sleep_durations(profile, max_nights=7)
        if not durations:
            return (
                "Recovery score card: data is still limited. "
                "Log bedtime and wake for at least 4 nights to unlock trend and trigger analysis."
            )

        avg_duration = sum(durations) / len(durations)
        best_night = max(durations)
        trend_line = " -> ".join(f"{d:.1f}h" for d in durations)

        bed_minutes = self._recent_bed_minutes(profile, max_nights=14)
        if len(bed_minutes) >= 3:
            diffs = [abs(bed_minutes[i] - bed_minutes[i - 1]) for i in range(1, len(bed_minutes))]
            avg_shift = sum(diffs) / max(1, len(diffs))
        else:
            avg_shift = 0.0

        night_wakes = max(0, int(profile.get("sleep", {}).get("night_wake_count", 0) or 0))
        debt_hours = max(0.0, target * len(durations) - sum(durations))

        penalties = {
            "sleep duration below target": max(0.0, target - avg_duration) * 30,
            "bedtime inconsistency": max(0.0, avg_shift - 20) * 0.9,
            "night wake interruptions": float(night_wakes) * 6,
            "sleep debt buildup": debt_hours * 10,
        }
        worst_trigger = max(penalties, key=penalties.get)

        if worst_trigger == "sleep duration below target":
            next_plan = "Add a 25-minute earlier lights-out target on 4 nights this week."
        elif worst_trigger == "bedtime inconsistency":
            next_plan = "Use a fixed bedtime anchor window (plus/minus 20 min) for 7 nights."
        elif worst_trigger == "night wake interruptions":
            next_plan = "Run night wake recovery protocol on first wake and keep room extra dim."
        else:
            next_plan = "Run a 5-night debt reset: move bedtime earlier 20-30 minutes with stable wake time."

        score = max(0, min(100, int(round(100 - penalties[worst_trigger]))))
        return (
            f"Recovery score card (weekly): score={score}/100. "
            f"Trend: {trend_line}. Best night: {best_night:.1f}h. "
            f"Worst trigger: {worst_trigger}. Next week plan: {next_plan}"
        )

    def adaptive_wake_routine_plan(self, profile: dict) -> str:
        self.ensure_shape(profile)
        target = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)
        durations = self._recent_sleep_durations(profile, max_nights=5)
        if not durations:
            return (
                "Adaptive wake routine: start with a 20-minute gentle ramp "
                "(lights from 20% to 80% + soft audio)."
            )

        avg = sum(durations) / len(durations)
        if avg < target - 1.0:
            return (
                f"Adaptive wake routine: average sleep is {avg:.1f}h. "
                "Use a slower 30-minute wake ramp and keep morning prompts gentle."
            )
        return (
            f"Adaptive wake routine: average sleep is {avg:.1f}h. "
            "Use a 15-minute wake ramp with moderate light and optional energizing music."
        )

    def stress_decompression_protocol(self, profile: dict, minutes: int = 5) -> str:
        self.ensure_shape(profile)
        mins = max(3, min(15, int(minutes)))
        profile["sleep"]["last_decompression_date"] = datetime.now().date().isoformat()
        return (
            f"Stress decompression ({mins} min): 1) 60s body scan, 2) inhale 4s/exhale 6s, "
            "3) one-line mind dump, 4) choose one tiny action for tomorrow, then lights down."
        )

    def sleep_debt_recovery_plan(self, profile: dict) -> str:
        self.ensure_shape(profile)
        target = float(profile.get("preferences", {}).get("sleep_target_hours", 8.0) or 8.0)
        durations = self._recent_sleep_durations(profile, max_nights=7)
        if not durations:
            return "Sleep debt planner: not enough data yet. Log bedtime and wake for a few nights first."

        nights = len(durations)
        total = sum(durations)
        debt = max(0.0, target * nights - total)
        if debt <= 0.4:
            return (
                f"Sleep debt planner: no significant debt. Avg {total / nights:.1f}h/night. "
                "Keep schedule steady and avoid late stimulation."
            )

        nightly_add = min(0.75, debt / 3.0)
        return (
            f"Sleep debt planner: about {debt:.1f}h debt over {nights} night(s). "
            f"Recovery plan: for next 3 nights, shift bedtime earlier by ~{int(nightly_add * 60)} minutes "
            "and keep wake time stable."
        )

    def environment_intelligence_tip(self, profile: dict) -> str:
        self.ensure_shape(profile)
        window = self.estimate_bedtime_window(profile)
        recovery_mode = bool(profile.get("sleep", {}).get("recovery_mode", False))
        if recovery_mode:
            return (
                f"Environment intelligence: recovery mode active. Use very low warm light and no pulse effects. "
                f"Target bedtime window {window}."
            )
        return (
            f"Environment intelligence: 60 min before sleep use warm dim lights (<30%), "
            f"quiet audio, and target bedtime window {window}."
        )

    def weekly_sleep_insights(self, profile: dict) -> str:
        self.ensure_shape(profile)
        profile["sleep"]["last_weekly_insights_date"] = datetime.now().date().isoformat()
        durations = self._recent_sleep_durations(profile, max_nights=7)
        consistency_line = self.sleep_consistency_score(profile)
        if not durations:
            return (
                "Weekly sleep insights: data is still limited. "
                "This week action: log bedtime and wake daily for better coaching."
            )

        avg = sum(durations) / len(durations)
        best = max(durations)
        worst = min(durations)
        action = "keep bedtime within a 30-minute window"
        if avg < 7.0:
            action = "move bedtime 20-30 minutes earlier for the next 3 nights"
        return (
            f"Weekly sleep insights: avg={avg:.1f}h, best={best:.1f}h, lowest={worst:.1f}h. "
            f"{consistency_line} Next action: {action}."
        )
