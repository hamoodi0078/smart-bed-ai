from pathlib import Path

try:
    import pygame
except Exception:  # pragma: no cover - optional runtime dependency
    pygame = None


class AudioPlaybackController:
    def __init__(self):
        self._ready = False
        if pygame is None:
            return

        try:
            pygame.mixer.init()
            self._ready = True
        except Exception:
            self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    def play_file(self, file_path: str) -> bool:
        if not self._ready:
            return False

        path = Path(file_path)
        if not path.exists() or path.stat().st_size == 0:
            return False

        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.play()
            return True
        except Exception:
            return False

    def queue_file(self, file_path: str) -> bool:
        if not self._ready:
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
        if not self._ready:
            return False
        try:
            return bool(pygame.mixer.music.get_busy())
        except Exception:
            return False

    def stop(self):
        if self._ready:
            try:
                if pygame.mixer.music.get_busy():
                    pygame.mixer.music.fadeout(120)
                else:
                    pygame.mixer.music.stop()
            except Exception:
                pygame.mixer.music.stop()

    def pause(self):
        if self._ready:
            pygame.mixer.music.pause()

    def resume(self):
        if self._ready:
            pygame.mixer.music.unpause()
