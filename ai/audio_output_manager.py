import re
import subprocess
from typing import List, Optional, Tuple


class AudioOutputManager:
    def __init__(self):
        self._last_scan: List[dict] = []

    @staticmethod
    def _is_mac(text: str) -> bool:
        return bool(re.match(r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$", (text or "").strip()))

    def _run(self, args: List[str], timeout: int = 10) -> Tuple[bool, str]:
        try:
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            if proc.returncode != 0:
                return False, (proc.stderr or proc.stdout or "").strip()
            return True, (proc.stdout or "").strip()
        except Exception as e:
            return False, str(e)

    def _list_known_devices(self) -> List[dict]:
        ok, out = self._run(["bluetoothctl", "devices"], timeout=8)
        if not ok:
            return []
        devices = []
        for line in out.splitlines():
            line = line.strip()
            if not line.startswith("Device "):
                continue
            parts = line.split(" ", 2)
            if len(parts) < 3:
                continue
            devices.append({"mac": parts[1].strip(), "name": parts[2].strip()})
        return devices

    def scan_speakers(self) -> Tuple[bool, str, List[dict]]:
        self._run(["bluetoothctl", "power", "on"], timeout=6)
        devices = self._list_known_devices()
        self._last_scan = devices
        if not devices:
            return False, "No Bluetooth speakers found yet. Put speaker in pairing mode, then retry.", []
        names = ", ".join(f"{d['name']} ({d['mac']})" for d in devices[:8])
        return True, f"Found Bluetooth devices: {names}", devices

    def _find_target_device(self, target: str) -> Optional[dict]:
        q = (target or "").strip()
        if not q:
            return None

        devices = self._last_scan or self._list_known_devices()
        if self._is_mac(q):
            q_lower = q.lower()
            for d in devices:
                if d.get("mac", "").lower() == q_lower:
                    return d
            return {"mac": q, "name": "Bluetooth Speaker"}

        q_lower = q.lower()
        for d in devices:
            if q_lower in d.get("name", "").lower():
                return d
        return None

    def connect_bluetooth_speaker(self, target: str, profile: dict) -> Tuple[bool, str]:
        device = self._find_target_device(target)
        if not device:
            return (
                False,
                "Speaker not found. Use 'scan bluetooth speakers' then 'connect bluetooth speaker <name or mac>'.",
            )

        mac = device.get("mac", "").strip()
        if not mac:
            return False, "Missing Bluetooth speaker MAC address."

        self._run(["bluetoothctl", "power", "on"], timeout=6)
        self._run(["bluetoothctl", "trust", mac], timeout=8)
        self._run(["bluetoothctl", "pair", mac], timeout=12)
        ok_conn, out_conn = self._run(["bluetoothctl", "connect", mac], timeout=12)
        if not ok_conn:
            return False, f"Failed to connect Bluetooth speaker: {out_conn or 'unknown error'}"

        prefs = profile.setdefault("preferences", {})
        prefs["audio_output_mode"] = "bluetooth_speaker"
        prefs["bluetooth_speaker_mac"] = mac
        prefs["bluetooth_speaker_name"] = device.get("name", "Bluetooth Speaker")
        return True, f"Connected to Bluetooth speaker: {prefs['bluetooth_speaker_name']}."

    def disconnect_bluetooth_speaker(self, profile: dict) -> Tuple[bool, str]:
        prefs = profile.setdefault("preferences", {})
        mac = str(prefs.get("bluetooth_speaker_mac", "") or "").strip()
        if mac:
            self._run(["bluetoothctl", "disconnect", mac], timeout=8)

        prefs["audio_output_mode"] = "bed_speaker"
        return True, "Switched to bed speaker. Bluetooth speaker disconnected."

    def set_bed_speaker(self, profile: dict) -> Tuple[bool, str]:
        prefs = profile.setdefault("preferences", {})
        prefs["audio_output_mode"] = "bed_speaker"
        return True, "Audio output set to bed speaker (default)."

    def ensure_output(self, profile: dict) -> Tuple[bool, str]:
        prefs = profile.setdefault("preferences", {})
        mode = str(prefs.get("audio_output_mode", "bed_speaker") or "bed_speaker").strip().lower()
        if mode != "bluetooth_speaker":
            prefs["audio_output_mode"] = "bed_speaker"
            return True, "Bed speaker active."

        mac = str(prefs.get("bluetooth_speaker_mac", "") or "").strip()
        if not mac:
            prefs["audio_output_mode"] = "bed_speaker"
            return False, "No Bluetooth speaker saved. Falling back to bed speaker."

        ok_conn, _ = self._run(["bluetoothctl", "connect", mac], timeout=8)
        if ok_conn:
            return True, f"Bluetooth speaker connected: {prefs.get('bluetooth_speaker_name', mac)}"

        prefs["audio_output_mode"] = "bed_speaker"
        return False, "Bluetooth speaker unavailable. Falling back to bed speaker."

    def output_status(self, profile: dict) -> str:
        prefs = profile.setdefault("preferences", {})
        mode = str(prefs.get("audio_output_mode", "bed_speaker") or "bed_speaker").strip().lower()
        if mode == "bluetooth_speaker":
            name = prefs.get("bluetooth_speaker_name", "Bluetooth Speaker")
            mac = prefs.get("bluetooth_speaker_mac", "")
            return f"Audio output: Bluetooth speaker ({name}, {mac})."
        return "Audio output: Bed speaker (default)."
