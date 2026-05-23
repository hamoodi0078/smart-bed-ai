"""Content manager for unified access to Islamic content."""

from __future__ import annotations

from typing import Optional

from .quran_text import QuranTextService
from .prophet_stories import ProphetStoriesService


class ContentManager:
    """Unified manager for all Islamic content (Quran, stories, books)."""
    
    def __init__(self):
        self.quran = QuranTextService()
        self.prophet_stories = ProphetStoriesService()
    
    def search_all(self, query: str, limit: int = 20) -> dict:
        """
        Search across all Islamic content.
        
        Returns:
            Dictionary with results categorized by content type
        """
        results = {
            "query": query,
            "quran_verses": [],
            "prophet_stories": [],
            "total_results": 0
        }
        
        # Search Quran
        quran_results = self.quran.search_quran(query, edition="english", limit=limit)
        results["quran_verses"] = quran_results
        
        # Search prophet stories
        story_results = self.prophet_stories.search_stories(query)
        results["prophet_stories"] = story_results
        
        results["total_results"] = len(quran_results) + len(story_results)
        
        return results
    
    def get_daily_content(self) -> dict:
        """Get recommended daily Islamic content."""
        # Could implement logic to return varied daily content
        # For now, return a random prophet story
        import random
        prophets = self.prophet_stories.get_all_prophets()
        daily_prophet = random.choice(prophets)
        
        return {
            "type": "prophet_story",
            "content": daily_prophet
        }
