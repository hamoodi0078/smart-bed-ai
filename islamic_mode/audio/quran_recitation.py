"""Quran recitation service with audio playback and downloads."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional
import requests

from config import RUNTIME_DATA_DIR
from .reciter_catalog import ReciterCatalog

try:
    import pygame
    PYGAME_AVAILABLE = True
except ImportError:
    PYGAME_AVAILABLE = False
    pygame = None


logger = logging.getLogger(__name__)


class QuranRecitationService:
    """
    Service for managing Quran audio recitations.
    
    Features:
    - Stream audio directly
    - Download and cache audio files
    - Playlist management
    - Playback control
    """
    
    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or RUNTIME_DATA_DIR / "islamic_content" / "quran" / "audio"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.timeout = 30
        self._player_ready = False
        self._current_playlist = []
        self._current_index = -1
        self._init_player()
    
    def _init_player(self):
        """Initialize pygame mixer for audio playback."""
        if not PYGAME_AVAILABLE:
            logger.warning("pygame not available, audio playback disabled")
            return
        
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            self._player_ready = True
            logger.info("Audio player initialized")
        except Exception as e:
            logger.error(f"Failed to initialize audio player: {e}")
            self._player_ready = False
    
    def is_player_ready(self) -> bool:
        """Check if audio player is ready."""
        return self._player_ready
    
    def _get_cache_path(self, reciter_id: str, surah: int, ayah: int) -> Path:
        """Get cache file path for an ayah."""
        reciter_dir = self.cache_dir / reciter_id
        reciter_dir.mkdir(exist_ok=True)
        return reciter_dir / f"{surah:03d}{ayah:03d}.mp3"
    
    def is_cached(self, reciter_id: str, surah: int, ayah: int) -> bool:
        """Check if audio file is already cached."""
        cache_path = self._get_cache_path(reciter_id, surah, ayah)
        return cache_path.exists() and cache_path.stat().st_size > 0
    
    def download_ayah(self, reciter_id: str, surah: int, ayah: int) -> tuple[bool, str]:
        """
        Download and cache a single ayah audio file.
        
        Returns:
            Tuple of (success, message)
        """
        url = ReciterCatalog.get_audio_url(reciter_id, surah, ayah)
        if not url:
            return False, "Invalid reciter or ayah numbers"
        
        cache_path = self._get_cache_path(reciter_id, surah, ayah)
        
        # Check if already cached
        if cache_path.exists() and cache_path.stat().st_size > 0:
            logger.debug(f"Ayah {surah}:{ayah} already cached")
            return True, "Already cached"
        
        # Download
        try:
            logger.info(f"Downloading {reciter_id} - Surah {surah} Ayah {ayah}")
            response = requests.get(url, timeout=self.timeout, stream=True)
            response.raise_for_status()
            
            with open(cache_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            
            logger.info(f"Downloaded to {cache_path}")
            return True, "Downloaded successfully"
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download {url}: {e}")
            return False, f"Download failed: {str(e)}"
        except Exception as e:
            logger.error(f"Error during download: {e}")
            return False, f"Error: {str(e)}"
    
    def download_surah(self, reciter_id: str, surah: int, total_ayahs: int) -> dict:
        """
        Download all ayahs in a surah.
        
        Returns:
            Dictionary with download statistics
        """
        results = {
            "reciter": reciter_id,
            "surah": surah,
            "total_ayahs": total_ayahs,
            "downloaded": 0,
            "already_cached": 0,
            "failed": 0,
            "failed_ayahs": []
        }
        
        for ayah in range(1, total_ayahs + 1):
            success, msg = self.download_ayah(reciter_id, surah, ayah)
            if success:
                if "Already cached" in msg:
                    results["already_cached"] += 1
                else:
                    results["downloaded"] += 1
            else:
                results["failed"] += 1
                results["failed_ayahs"].append(ayah)
        
        return results
    
    def get_cached_audio_path(self, reciter_id: str, surah: int, ayah: int) -> Optional[Path]:
        """Get path to cached audio file if it exists."""
        cache_path = self._get_cache_path(reciter_id, surah, ayah)
        if cache_path.exists() and cache_path.stat().st_size > 0:
            return cache_path
        return None
    
    def play_ayah(self, reciter_id: str, surah: int, ayah: int, download_if_missing: bool = True) -> tuple[bool, str]:
        """
        Play a single ayah.
        
        Args:
            reciter_id: Reciter identifier
            surah: Surah number
            ayah: Ayah number
            download_if_missing: Download if not cached
        
        Returns:
            Tuple of (success, message)
        """
        if not self._player_ready:
            return False, "Audio player not available"
        
        # Get cached file or download
        cache_path = self.get_cached_audio_path(reciter_id, surah, ayah)
        if not cache_path and download_if_missing:
            success, msg = self.download_ayah(reciter_id, surah, ayah)
            if not success:
                return False, f"Failed to download: {msg}"
            cache_path = self.get_cached_audio_path(reciter_id, surah, ayah)
        
        if not cache_path:
            return False, "Audio file not available"
        
        # Play
        try:
            pygame.mixer.music.load(str(cache_path))
            pygame.mixer.music.play()
            logger.info(f"Playing {reciter_id} - Surah {surah} Ayah {ayah}")
            return True, "Playing"
        except Exception as e:
            logger.error(f"Failed to play audio: {e}")
            return False, f"Playback error: {str(e)}"
    
    def create_surah_playlist(self, reciter_id: str, surah: int, total_ayahs: int) -> tuple[bool, str]:
        """
        Create a playlist for a full surah.
        
        Returns:
            Tuple of (success, message)
        """
        self._current_playlist = []
        for ayah in range(1, total_ayahs + 1):
            self._current_playlist.append({
                "reciter": reciter_id,
                "surah": surah,
                "ayah": ayah
            })
        
        self._current_index = -1
        return True, f"Playlist created with {total_ayahs} ayahs"
    
    def play_next(self, download_if_missing: bool = True) -> tuple[bool, str]:
        """Play next ayah in playlist."""
        if not self._current_playlist:
            return False, "No playlist loaded"
        
        self._current_index += 1
        if self._current_index >= len(self._current_playlist):
            self._current_index = 0  # Loop back
        
        item = self._current_playlist[self._current_index]
        return self.play_ayah(
            item["reciter"],
            item["surah"],
            item["ayah"],
            download_if_missing=download_if_missing
        )
    
    def play_previous(self, download_if_missing: bool = True) -> tuple[bool, str]:
        """Play previous ayah in playlist."""
        if not self._current_playlist:
            return False, "No playlist loaded"
        
        self._current_index -= 1
        if self._current_index < 0:
            self._current_index = len(self._current_playlist) - 1
        
        item = self._current_playlist[self._current_index]
        return self.play_ayah(
            item["reciter"],
            item["surah"],
            item["ayah"],
            download_if_missing=download_if_missing
        )
    
    def pause(self) -> tuple[bool, str]:
        """Pause playback."""
        if not self._player_ready:
            return False, "Player not ready"
        
        try:
            pygame.mixer.music.pause()
            return True, "Paused"
        except Exception as e:
            return False, f"Pause failed: {str(e)}"
    
    def resume(self) -> tuple[bool, str]:
        """Resume playback."""
        if not self._player_ready:
            return False, "Player not ready"
        
        try:
            pygame.mixer.music.unpause()
            return True, "Resumed"
        except Exception as e:
            return False, f"Resume failed: {str(e)}"
    
    def stop(self) -> tuple[bool, str]:
        """Stop playback."""
        if not self._player_ready:
            return False, "Player not ready"
        
        try:
            pygame.mixer.music.stop()
            return True, "Stopped"
        except Exception as e:
            return False, f"Stop failed: {str(e)}"
    
    def is_playing(self) -> bool:
        """Check if audio is currently playing."""
        if not self._player_ready:
            return False
        return pygame.mixer.music.get_busy()
    
    def get_current_playback_info(self) -> Optional[dict]:
        """Get information about current playback."""
        if self._current_index >= 0 and self._current_index < len(self._current_playlist):
            return self._current_playlist[self._current_index]
        return None
    
    def clear_cache(self, reciter_id: Optional[str] = None) -> dict:
        """
        Clear cached audio files.
        
        Args:
            reciter_id: Clear specific reciter (None = clear all)
        
        Returns:
            Dictionary with deletion statistics
        """
        deleted = 0
        failed = 0
        
        if reciter_id:
            reciter_dir = self.cache_dir / reciter_id
            if reciter_dir.exists():
                for file in reciter_dir.glob("*.mp3"):
                    try:
                        file.unlink()
                        deleted += 1
                    except Exception:
                        failed += 1
        else:
            for reciter_dir in self.cache_dir.iterdir():
                if reciter_dir.is_dir():
                    for file in reciter_dir.glob("*.mp3"):
                        try:
                            file.unlink()
                            deleted += 1
                        except Exception:
                            failed += 1
        
        return {
            "deleted": deleted,
            "failed": failed,
            "reciter": reciter_id or "all"
        }
    
    def get_cache_stats(self, reciter_id: Optional[str] = None) -> dict:
        """Get statistics about cached audio files."""
        total_files = 0
        total_size = 0
        
        search_dir = self.cache_dir
        if reciter_id:
            search_dir = self.cache_dir / reciter_id
        
        if search_dir.exists():
            for audio_file in search_dir.rglob("*.mp3"):
                total_files += 1
                total_size += audio_file.stat().st_size
        
        return {
            "cache_dir": str(self.cache_dir),
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "reciter": reciter_id or "all"
        }
