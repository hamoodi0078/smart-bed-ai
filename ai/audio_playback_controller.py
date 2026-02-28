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
            return False

        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            return False

        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            # Wait for audio to start (max 0.5 seconds)
            start_time = time.time()
            while not pygame.mixer.music.get_busy() and (time.time() - start_time) < 0.5:
                time.sleep(0.01)
            # Block until audio fully finishes playing
            while pygame.mixer.music.get_busy():
                time.sleep(0.1)
            return True
        except Exception:
            return False

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
