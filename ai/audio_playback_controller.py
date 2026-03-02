from pathlib import Path
import time

try:
    import pygame
except Exception:  # pragma: no cover - optional runtime dependency
    pygame = None


class AudioPlaybackController:
    def __init__(self):
        self._ready = False
        if pygame is None:
            return

        self._try_init_mixer()

    def _try_init_mixer(self) -> bool:
        if pygame is None:
            self._ready = False
            return False
        if self._ready:
            return True
        try:
            pygame.mixer.init()
            self._ready = True
            return True
        except Exception:
            self._ready = False
            return False

    def is_ready(self) -> bool:
        return self._ready or self._try_init_mixer()

    def play_file(self, file_path: str) -> bool:
        if not self.is_ready():
            print("[AUDIO] pygame mixer not ready; playback skipped.")
            return False

        path = Path(file_path)
        resolved_path = path.resolve()
        if not resolved_path.exists() or resolved_path.stat().st_size == 0:
            print(f"[AUDIO] audio file missing or empty: {resolved_path}")
            return False

        try:
            pygame.mixer.music.load(str(resolved_path))
            pygame.mixer.music.play()
            start_deadline = time.time() + 2.0
            played = False
            while time.time() < start_deadline:
                if pygame.mixer.music.get_busy():
                    played = True
                    print(f"[AUDIO] pygame playback started: {resolved_path}")
                    break
                time.sleep(0.02)
            if not played:
                print(f"[AUDIO] pygame playback did not start within 2.0s: {resolved_path}")
                return False

            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            print(f"[AUDIO] pygame playback ended: {resolved_path}")
            return played
        except Exception as e:
            print(f"[AUDIO] pygame playback error for {resolved_path}: {e}")
            return False
        finally:
            # Explicitly release the file handle so the next TTS write can overwrite this path.
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass
            try:
                pygame.mixer.music.unload()
            except Exception:
                pass

    def queue_file(self, file_path: str) -> bool:
        if not self.is_ready():
            return False

        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            return False

        try:
            if not pygame.mixer.music.get_busy():
                return False
            pygame.mixer.music.queue(str(path))
            return True
        except Exception:
            return False

    def is_playing(self) -> bool:
        if not self.is_ready():
            return False
        try:
            return bool(pygame.mixer.music.get_busy())
        except Exception:
            return False

    def stop(self):
        if self.is_ready():
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.fadeout(120)
                else:
                    pygame.mixer.music.stop()
            except Exception:
                try:
                    pygame.mixer.music.stop()
                except Exception:
                    pass

    def pause(self):
        if self.is_ready():
            try:
                pygame.mixer.music.pause()
            except Exception:
                pass

    def resume(self):
        if self.is_ready():
            try:
                pygame.mixer.music.unpause()
            except Exception:
                pass
