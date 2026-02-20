"""
Audio Cache Module
Persistent disk-based cache for generated TTS audio to avoid regenerating identical text.
"""
import json
import hashlib
import time
import threading
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from collections import OrderedDict

logger = logging.getLogger(__name__)


class AudioCache:
    """
    Persistent audio cache for TTS generation.
    
    Stores generated audio files on disk with metadata for LRU eviction.
    Cache keys are generated from text, voice, rate, volume, and pitch parameters.
    """
    
    DEFAULT_CACHE_DIR = Path.home() / ".critts" / "audio_cache"
    DEFAULT_MAX_SIZE_MB = 500
    CACHE_VERSION = 1  # Increment when cache format changes
    
    # Batching configuration for index persistence
    FLUSH_INTERVAL_STORES = 10  # Flush index every N store operations
    FLUSH_INTERVAL_SECONDS = 30  # Flush index every N seconds (timer-based)
    
    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        max_size_mb: int = DEFAULT_MAX_SIZE_MB,
        enabled: bool = True
    ):
        """
        Initialize the audio cache.
        
        Args:
            cache_dir: Directory to store cache files (default: ~/.critts/audio_cache/)
            max_size_mb: Maximum cache size in megabytes
            enabled: Whether caching is enabled
        """
        self.cache_dir = Path(cache_dir) if cache_dir else self.DEFAULT_CACHE_DIR
        self.max_size_mb = max_size_mb
        self.enabled = enabled
        self._lock = threading.Lock()
        self._dirty = False  # Track if index needs to be persisted
        
        # Batching state for index persistence
        self._store_count = 0  # Counter for batch flushing
        self._last_flush_time = time.time()  # Timestamp for timer-based flushing
        self._flush_timer: Optional[threading.Timer] = None  # Background timer for periodic flush
        
        # Statistics
        self._hits = 0
        self._misses = 0
        self._total_saved_time = 0.0
        
        # In-memory index for fast lookups
        self._index: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        
        # Initialize cache directory and load index
        self._initialize_cache()
        
        # Start periodic flush timer
        self._start_flush_timer()
    
    def _start_flush_timer(self):
        """Start the background timer for periodic index flushing."""
        if not self.enabled:
            return
        
        def timer_callback():
            """Callback for the flush timer."""
            try:
                self._flush_if_dirty()
            finally:
                # Restart timer if still enabled
                if self.enabled:
                    self._start_flush_timer()
        
        self._flush_timer = threading.Timer(self.FLUSH_INTERVAL_SECONDS, timer_callback)
        self._flush_timer.daemon = True
        self._flush_timer.start()
    
    def _stop_flush_timer(self):
        """Stop the background flush timer."""
        if self._flush_timer:
            self._flush_timer.cancel()
            self._flush_timer = None
    
    def _flush_if_dirty(self):
        """
        Flush the index to disk if it has been modified.
        
        This is called by the batch trigger (store count) and timer.
        Note: _store_count is NOT reset here to avoid interfering with batch
        threshold logic in store(). The counter is only reset in store() after
        a batch flush.
        """
        with self._lock:
            if self._dirty:
                self._save_index()
                self._dirty = False
                self._last_flush_time = time.time()
                logger.debug("Flushed audio cache index to disk")
    
    def _initialize_cache(self):
        """Create cache directory if needed and load existing index."""
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_index()
            self._cleanup_if_needed()
        except Exception as e:
            logger.warning("Failed to initialize audio cache: %s", e)
            self.enabled = False
    
    def _get_index_path(self) -> Path:
        """Get path to the cache index file."""
        return self.cache_dir / "cache_index.json"
    
    def _load_index(self):
        """Load cache index from disk."""
        index_path = self._get_index_path()
        if not index_path.exists():
            self._index = OrderedDict()
            return
        
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check version compatibility
            if data.get("version", 0) != self.CACHE_VERSION:
                logger.info("Cache version mismatch, rebuilding index")
                self._rebuild_index()
                return
            
            # Load entries
            self._index = OrderedDict()
            entries = data.get("entries", {})
            
            # Sort by last access time (LRU order)
            sorted_entries = sorted(
                entries.items(),
                key=lambda x: x[1].get("last_access", 0)
            )
            
            for key, entry in sorted_entries:
                # Verify file exists
                cache_path = self.cache_dir / f"{key}.mp3"
                if cache_path.exists():
                    self._index[key] = entry
                else:
                    # Remove stale entry
                    meta_path = self.cache_dir / f"{key}.meta.json"
                    if meta_path.exists():
                        try:
                            meta_path.unlink()
                        except OSError:
                            pass
            
            logger.info("Loaded %d cached audio entries", len(self._index))
            
        except Exception as e:
            logger.warning("Failed to load cache index: %s", e)
            self._index = OrderedDict()
    
    def _save_index(self):
        """Save cache index to disk."""
        index_path = self._get_index_path()
        try:
            data = {
                "version": self.CACHE_VERSION,
                "entries": dict(self._index),
                "stats": {
                    "hits": self._hits,
                    "misses": self._misses,
                    "total_saved_time": self._total_saved_time
                }
            }
            with open(index_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.warning("Failed to save cache index: %s", e)
    
    def _rebuild_index(self):
        """Rebuild cache index from disk files."""
        self._index = OrderedDict()
        
        try:
            for meta_file in self.cache_dir.glob("*.meta.json"):
                try:
                    with open(meta_file, 'r', encoding='utf-8') as f:
                        entry = json.load(f)
                    
                    key = meta_file.stem.replace(".meta", "")
                    cache_path = self.cache_dir / f"{key}.mp3"
                    
                    if cache_path.exists():
                        self._index[key] = entry
                    else:
                        # Remove orphaned meta file
                        meta_file.unlink()
                        
                except Exception as e:
                    logger.debug("Failed to load meta file %s: %s", meta_file, e)
            
            self._save_index()
            logger.info("Rebuilt cache index with %d entries", len(self._index))
            
        except Exception as e:
            logger.warning("Failed to rebuild cache index: %s", e)
    
    def _generate_key(self, text: str, voice: str, rate: int, volume: int, pitch: int) -> str:
        """
        Generate a cache key from TTS parameters.
        
        Args:
            text: Text to synthesize
            voice: Voice identifier
            rate: Speech rate
            volume: Volume level
            pitch: Pitch adjustment
            
        Returns:
            Hash key for the parameters
        """
        # Normalize text
        normalized_text = text.strip().lower()
        
        # Create key string
        key_string = f"{normalized_text}|{voice}|{rate}|{volume}|{pitch}"
        
        # Generate hash
        return hashlib.sha256(key_string.encode('utf-8')).hexdigest()[:32]
    
    def lookup(self, text: str, voice: str, rate: int = 0, volume: int = 100, pitch: int = 0) -> Optional[bytes]:
        """
        Look up cached audio for the given parameters.
        
        Args:
            text: Text to synthesize
            voice: Voice identifier
            rate: Speech rate
            volume: Volume level
            pitch: Pitch adjustment
            
        Returns:
            Cached audio bytes or None if not found
        """
        if not self.enabled:
            return None
        
        with self._lock:
            key = self._generate_key(text, voice, rate, volume, pitch)
            
            if key not in self._index:
                self._misses += 1
                return None
            
            # Load audio from disk
            cache_path = self.cache_dir / f"{key}.mp3"
            try:
                with open(cache_path, 'rb') as f:
                    audio_data = f.read()
                
                # Update access time and move to end (most recently used)
                self._index[key]["last_access"] = time.time()
                self._index[key]["access_count"] = self._index[key].get("access_count", 0) + 1
                self._index.move_to_end(key)
                self._dirty = True  # Mark index as modified
                
                self._hits += 1
                self._total_saved_time += self._index[key].get("generation_time", 0)
                
                logger.debug("Cache hit for key %s...", key[:8])
                return audio_data
                
            except Exception as e:
                logger.debug("Failed to read cached audio: %s", e)
                # Remove stale entry
                del self._index[key]
                self._misses += 1
                return None
    
    def store(
        self,
        audio_data: bytes,
        text: str,
        voice: str,
        rate: int = 0,
        volume: int = 100,
        pitch: int = 0,
        generation_time: float = 0.0
    ) -> bool:
        """
        Store generated audio in the cache.
        
        Args:
            audio_data: Audio bytes to cache
            text: Text that was synthesized
            voice: Voice identifier
            rate: Speech rate
            volume: Volume level
            pitch: Pitch adjustment
            generation_time: Time taken to generate the audio
            
        Returns:
            True if stored successfully
        """
        if not self.enabled or not audio_data:
            return False
        
        with self._lock:
            key = self._generate_key(text, voice, rate, volume, pitch)
            
            try:
                # Save audio file
                cache_path = self.cache_dir / f"{key}.mp3"
                with open(cache_path, 'wb') as f:
                    f.write(audio_data)
                
                # Create metadata
                meta = {
                    "text": text[:200],  # Truncate for storage
                    "voice": voice,
                    "rate": rate,
                    "volume": volume,
                    "pitch": pitch,
                    "size_bytes": len(audio_data),
                    "created": time.time(),
                    "last_access": time.time(),
                    "access_count": 0,
                    "generation_time": generation_time
                }
                
                # Save metadata
                meta_path = self.cache_dir / f"{key}.meta.json"
                with open(meta_path, 'w', encoding='utf-8') as f:
                    json.dump(meta, f, indent=2)
                
                # Update index
                self._index[key] = meta
                self._index.move_to_end(key)
                self._dirty = True  # Mark index as modified
                
                # Increment store counter for batch flushing
                self._store_count += 1
                
                logger.debug("Cached audio for key %s...", key[:8])
                
                # Flush if batch threshold reached
                if self._store_count >= self.FLUSH_INTERVAL_STORES:
                    self._save_index()
                    self._dirty = False
                    self._store_count = 0
                    self._last_flush_time = time.time()
                    logger.debug("Flushed audio cache index (batch threshold reached)")
                
                # Check if cleanup needed
                self._cleanup_if_needed()
                
                return True
                
            except Exception as e:
                logger.warning("Failed to cache audio: %s", e)
                return False
    
    def _get_cache_size(self) -> int:
        """Get total cache size in bytes."""
        total = 0
        for entry in self._index.values():
            total += entry.get("size_bytes", 0)
        return total
    
    def get_cache_size_mb(self) -> float:
        """Get total cache size in megabytes."""
        return self._get_cache_size() / (1024 * 1024)
    
    def _cleanup_if_needed(self):
        """Remove oldest entries if cache exceeds max size."""
        max_bytes = self.max_size_mb * 1024 * 1024
        current_size = self._get_cache_size()
        
        if current_size <= max_bytes:
            return
        
        # Remove oldest entries (LRU eviction)
        removed_count = 0
        removed_size = 0
        
        while current_size > max_bytes * 0.9 and self._index:  # Clean to 90% of max
            # Remove oldest (first in OrderedDict)
            key, entry = self._index.popitem(last=False)
            
            try:
                # Delete files
                cache_path = self.cache_dir / f"{key}.mp3"
                meta_path = self.cache_dir / f"{key}.meta.json"
                
                if cache_path.exists():
                    cache_path.unlink()
                if meta_path.exists():
                    meta_path.unlink()
                
                removed_size += entry.get("size_bytes", 0)
                removed_count += 1
                
            except Exception as e:
                logger.debug("Failed to remove cache entry: %s", e)
            
            current_size = self._get_cache_size()
        
        if removed_count > 0:
            logger.info("Cache cleanup: removed %d entries, freed %.2f MB", removed_count, removed_size / (1024*1024))
            self._save_index()
    
    def clear(self) -> bool:
        """
        Clear all cached audio.
        
        Returns:
            True if cleared successfully
        """
        with self._lock:
            try:
                for key in list(self._index.keys()):
                    cache_path = self.cache_dir / f"{key}.mp3"
                    meta_path = self.cache_dir / f"{key}.meta.json"
                    
                    try:
                        if cache_path.exists():
                            cache_path.unlink()
                        if meta_path.exists():
                            meta_path.unlink()
                    except OSError:
                        pass
                
                self._index.clear()
                self._save_index()
                
                # Reset statistics
                self._hits = 0
                self._misses = 0
                self._total_saved_time = 0.0
                
                logger.info("Audio cache cleared")
                return True
                
            except Exception as e:
                logger.warning("Failed to clear cache: %s", e)
                return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0
        
        return {
            "enabled": self.enabled,
            "entries": len(self._index),
            "size_mb": self.get_cache_size_mb(),
            "max_size_mb": self.max_size_mb,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
            "total_saved_time": self._total_saved_time,
            "cache_dir": str(self.cache_dir)
        }
    
    def prune_by_age(self, max_age_days: int = 30) -> int:
        """
        Remove entries older than specified age.
        
        Args:
            max_age_days: Maximum age in days
            
        Returns:
            Number of entries removed
        """
        with self._lock:
            cutoff_time = time.time() - (max_age_days * 24 * 60 * 60)
            removed = 0
            
            keys_to_remove = [
                key for key, entry in self._index.items()
                if entry.get("created", 0) < cutoff_time
            ]
            
            for key in keys_to_remove:
                try:
                    cache_path = self.cache_dir / f"{key}.mp3"
                    meta_path = self.cache_dir / f"{key}.meta.json"
                    
                    if cache_path.exists():
                        cache_path.unlink()
                    if meta_path.exists():
                        meta_path.unlink()
                    
                    del self._index[key]
                    removed += 1
                    
                except Exception as e:
                    logger.debug("Failed to remove old cache entry: %s", e)
            
            if removed > 0:
                self._save_index()
                logger.info("Pruned %d cache entries older than %d days", removed, max_age_days)
            
            return removed
    
    def set_max_size(self, max_size_mb: int):
        """
        Set maximum cache size and cleanup if needed.
        
        Args:
            max_size_mb: New maximum size in megabytes
        """
        with self._lock:
            self.max_size_mb = max_size_mb
            self._cleanup_if_needed()
    
    def shutdown(self):
        """
        Shutdown the cache and persist the index if modified.
        
        This provides a clean final flush on graceful exit and also
        persists any LRU last_access updates that lookup() makes.
        Only writes to disk if the index has been modified.
        """
        # Disable first to prevent timer callback from restarting timer
        self.enabled = False
        
        # Stop the periodic flush timer
        self._stop_flush_timer()
        
        with self._lock:
            if self._dirty:
                self._save_index()
                self._dirty = False
            logger.debug("Audio cache shutdown complete")


class PhraseTracker:
    """
    Tracks phrase usage frequency for pre-generation optimization.
    """
    
    DEFAULT_STATS_PATH = Path.home() / ".critts" / "phrase_stats.json"
    
    def __init__(self, stats_path: Optional[Path] = None):
        """
        Initialize phrase tracker.
        
        Args:
            stats_path: Path to phrase statistics file
        """
        self.stats_path = Path(stats_path) if stats_path else self.DEFAULT_STATS_PATH
        self._stats: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.Lock()
        self._load_stats()
    
    def _load_stats(self):
        """Load phrase statistics from disk."""
        if not self.stats_path.exists():
            return
        
        try:
            with open(self.stats_path, 'r', encoding='utf-8') as f:
                self._stats = json.load(f)
        except Exception as e:
            logger.debug("Failed to load phrase stats: %s", e)
            self._stats = {}
    
    def _save_stats(self):
        """Save phrase statistics to disk."""
        try:
            self.stats_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.stats_path, 'w', encoding='utf-8') as f:
                json.dump(self._stats, f, indent=2)
        except Exception as e:
            logger.debug("Failed to save phrase stats: %s", e)
    
    def track_usage(self, text: str, voice: str):
        """
        Track usage of a phrase.
        
        Args:
            text: The text that was used
            voice: The voice that was used
        """
        if not text or len(text.strip()) < 3:
            return
        
        text = text.strip()
        
        with self._lock:
            key = f"{text}|{voice}"
            
            if key not in self._stats:
                self._stats[key] = {
                    "text": text,
                    "voice": voice,
                    "count": 0,
                    "first_used": time.time(),
                    "last_used": time.time()
                }
            
            self._stats[key]["count"] += 1
            self._stats[key]["last_used"] = time.time()
            
            # Save periodically (every 10 uses)
            if self._stats[key]["count"] % 10 == 0:
                self._save_stats()
    
    def get_common_phrases(self, min_uses: int = 3, limit: int = 20) -> list:
        """
        Get most commonly used phrases.
        
        Args:
            min_uses: Minimum number of uses to be considered common
            limit: Maximum number of phrases to return
            
        Returns:
            List of (text, voice, count) tuples
        """
        with self._lock:
            phrases = [
                (entry["text"], entry["voice"], entry["count"])
                for entry in self._stats.values()
                if entry["count"] >= min_uses
            ]
            
            # Sort by count descending
            phrases.sort(key=lambda x: x[2], reverse=True)
            
            return phrases[:limit]
    
    def clear_stats(self):
        """Clear all phrase statistics."""
        with self._lock:
            self._stats.clear()
            self._save_stats()
    
    def shutdown(self):
        """
        Shutdown the phrase tracker and persist stats.
        
        This ensures any tracked phrases that haven't been saved yet
        (due to the periodic save every 10 uses) are persisted.
        """
        with self._lock:
            self._save_stats()
            logger.debug("Phrase tracker shutdown complete")
