from pathlib import Path
from typing import List, Tuple

try:
    import pygame
except Exception:  # pragma: no cover - optional runtime dependency
    pygame = None


SUPPORTED_EXTENSIONS = {".mp3", ".wav", ".ogg"}


class LocalMusicManager:
    def __init__(self, music_dir: str = "local_music"):
        self.music_dir = Path(music_dir)
        self.music_dir.mkdir(parents=True, exist_ok=True)
        self._tracks: List[Path] = []
        self._current_index = -1
        self._is_paused = False
        self._ready = False
        self._init_player()
        self.refresh_library()

    def _init_player(self):
        if pygame is None:
            self._ready = False
            return

        try:
            pygame.mixer.init()
            self._ready = True
        except Exception:
            self._ready = False

    def is_ready(self) -> bool:
        return self._ready

    def refresh_library(self):
        files = [
            p
            for p in self.music_dir.glob("**/*")
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        self._tracks = sorted(files, key=lambda x: x.name.lower())

    def list_tracks(self) -> List[str]:
        self.refresh_library()
        return [p.name for p in self._tracks]

    def play_query(self, query: str = "") -> Tuple[bool, str]:
        if not self._ready:
            return False, "Local music is unavailable. Install pygame first: pip install pygame"

        self.refresh_library()
        if not self._tracks:
            return (
                False,
                "No local songs found. Add .mp3/.wav/.ogg files to the local_music folder.",
            )

        query = query.strip().lower()
        match_index = 0
        if query:
            for idx, track in enumerate(self._tracks):
                if query in track.stem.lower() or query in track.name.lower():
                    match_index = idx
                    break
            else:
                return False, f"No local song matched '{query}'."

        self._current_index = match_index
        return self._play_current()

    def _play_current(self) -> Tuple[bool, str]:
        if self._current_index < 0 or self._current_index >= len(self._tracks):
            return False, "No local track selected."

        try:
            track = self._tracks[self._current_index]
            pygame.mixer.music.load(str(track))
            pygame.mixer.music.play()
            self._is_paused = False
            return True, f"Playing local song: {track.name}"
        except Exception:
            return False, "Failed to play local song. Check the audio file format."

    def pause(self) -> Tuple[bool, str]:
        if not self._ready:
            return False, "Local music is unavailable."
        if not pygame.mixer.music.get_busy():
            return False, "No local song is currently playing."

        pygame.mixer.music.pause()
        self._is_paused = True
        return True, "Paused local music."

    def resume(self) -> Tuple[bool, str]:
        if not self._ready:
            return False, "Local music is unavailable."
        if not self._is_paused:
            return False, "No paused local song to resume."

        pygame.mixer.music.unpause()
        self._is_paused = False
        return True, "Resumed local music."

    def previous_track(self) -> Tuple[bool, str]:
        if not self._ready:
            return False, "Local music is unavailable."

        self.refresh_library()
        if not self._tracks:
            return False, "No local songs found."

        if self._current_index < 0:
            self._current_index = 0
        else:
            self._current_index = (self._current_index - 1) % len(self._tracks)

        return self._play_current()

    def next_track(self) -> Tuple[bool, str]:
        if not self._ready:
            return False, "Local music is unavailable."

        self.refresh_library()
        if not self._tracks:
            return False, "No local songs found."

        if self._current_index < 0:
            self._current_index = 0
        else:
            self._current_index = (self._current_index + 1) % len(self._tracks)

        return self._play_current()

    def stop(self) -> Tuple[bool, str]:
        if not self._ready:
            return False, "Local music is unavailable."

        pygame.mixer.music.stop()
        self._is_paused = False
        return True, "Stopped local music."
