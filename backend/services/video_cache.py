import os
import hashlib
import logging
import time
from pathlib import Path
from typing import Optional, Dict, List
from collections import OrderedDict
from threading import Lock

logger = logging.getLogger(__name__)


class VideoCache:
    """本地影片快取（檔案系統 + 記憶體索引）"""
    
    def __init__(self, cache_dir: str = "/tmp/video_cache", max_size_mb: int = 1000):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size_bytes = max_size_mb * 1024 * 1024
        
        # ✅ 記憶體索引（用於快速查找和 LRU 管理）
        self.index: OrderedDict[str, Dict] = OrderedDict()
        
        # ✅ 反向索引：video_path -> [cache_keys]
        self.path_index: Dict[str, List[str]] = {}
        
        self.lock = Lock()
        
        # ✅ 初始化時掃描現有快取
        self._load_existing_cache()
        
        logger.info(f"🎬 Video cache initialized: {cache_dir} (max: {max_size_mb} MB)")
    
    def _load_existing_cache(self):
        """載入現有快取檔案到索引"""
        try:
            total_size = 0
            cache_files = list(self.cache_dir.glob("*.chunk"))
            
            for cache_path in cache_files:
                try:
                    stat = cache_path.stat()
                    cache_key = cache_path.stem
                    
                    # 嘗試讀取 metadata 檔案
                    meta_path = cache_path.with_suffix('.meta')
                    video_path = None
                    
                    if meta_path.exists():
                        try:
                            with open(meta_path, 'r') as f:
                                video_path = f.read().strip()
                        except:
                            pass
                    
                    self.index[cache_key] = {
                        'path': cache_path,
                        'size': stat.st_size,
                        'created': stat.st_ctime,
                        'last_access': stat.st_atime,
                        'hits': 0,
                        'video_path': video_path
                    }
                    
                    # 更新反向索引
                    if video_path:
                        if video_path not in self.path_index:
                            self.path_index[video_path] = []
                        self.path_index[video_path].append(cache_key)
                    
                    total_size += stat.st_size
                    
                except Exception as e:
                    logger.error(f"❌ Failed to load cache file {cache_path}: {e}")
            
            logger.info(f"📦 Loaded {len(self.index)} cache files ({total_size / 1024 / 1024:.2f} MB)")
            
            # ✅ 如果超過限制，清理舊檔案
            if total_size > self.max_size_bytes:
                self._cleanup_old_cache()
                
        except Exception as e:
            logger.error(f"❌ Failed to load existing cache: {e}")
    
    def _get_cache_key(self, video_path: str, start: int, end: int) -> str:
        """生成快取鍵"""
        key_str = f"{video_path}:{start}:{end}"
        return hashlib.md5(key_str.encode()).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> Path:
        """獲取快取檔案路徑"""
        return self.cache_dir / f"{cache_key}.chunk"
    
    def _get_meta_path(self, cache_key: str) -> Path:
        """獲取 metadata 檔案路徑"""
        return self.cache_dir / f"{cache_key}.meta"
    
    def _get_current_size(self) -> int:
        """獲取當前快取總大小"""
        with self.lock:
            return sum(item['size'] for item in self.index.values())
    
    def get(self, video_path: str, start: int, end: int) -> Optional[bytes]:
        """
        從快取獲取資料
        
        Args:
            video_path: 影片路徑
            start: 起始位置
            end: 結束位置
            
        Returns:
            bytes 或 None
        """
        cache_key = self._get_cache_key(video_path, start, end)
        
        with self.lock:
            if cache_key not in self.index:
                logger.debug(f"❌ Cache MISS: {cache_key[:16]}...")
                return None
            
            # ✅ 更新訪問時間和命中次數
            item = self.index[cache_key]
            item['last_access'] = time.time()
            item['hits'] += 1
            
            # ✅ 移到最後（標記為最近使用）
            self.index.move_to_end(cache_key)
        
        # ✅ 讀取檔案（在鎖外執行，避免阻塞）
        cache_path = item['path']
        
        if not cache_path.exists():
            logger.warning(f"⚠️ Cache file missing: {cache_path}")
            with self.lock:
                self._remove_from_index(cache_key)
            return None
        
        try:
            with open(cache_path, 'rb') as f:
                data = f.read()
            
            logger.debug(f"✅ Cache HIT: {cache_key[:16]}... ({len(data) / 1024:.1f} KB, hits: {item['hits']})")
            return data
            
        except Exception as e:
            logger.error(f"❌ Failed to read cache: {e}")
            # 清理損壞的快取
            with self.lock:
                self._remove_from_index(cache_key)
            try:
                cache_path.unlink()
            except:
                pass
            return None
    
    def _remove_from_index(self, cache_key: str):
        """從索引中移除項目（需要在鎖內呼叫）"""
        if cache_key in self.index:
            item = self.index.pop(cache_key)
            video_path = item.get('video_path')
            
            # 更新反向索引
            if video_path and video_path in self.path_index:
                try:
                    self.path_index[video_path].remove(cache_key)
                    if not self.path_index[video_path]:
                        del self.path_index[video_path]
                except ValueError:
                    pass
    
    def set(self, video_path: str, start: int, end: int, data: bytes):
        """
        儲存到快取
        
        Args:
            video_path: 影片路徑
            start: 起始位置
            end: 結束位置
            data: 影片數據
        """
        cache_key = self._get_cache_key(video_path, start, end)
        cache_path = self._get_cache_path(cache_key)
        meta_path = self._get_meta_path(cache_key)
        data_size = len(data)
        
        # ✅ 檢查是否需要清理空間
        current_size = self._get_current_size()
        
        if current_size + data_size > self.max_size_bytes:
            logger.info(f"🗑️ Cache full ({current_size / 1024 / 1024:.1f} MB), cleaning up...")
            self._cleanup_old_cache(required_space=data_size)
        
        # ✅ 寫入檔案
        try:
            with open(cache_path, 'wb') as f:
                f.write(data)
            
            # ✅ 寫入 metadata（儲存原始路徑）
            with open(meta_path, 'w') as f:
                f.write(video_path)
            
            # ✅ 更新索引
            with self.lock:
                self.index[cache_key] = {
                    'path': cache_path,
                    'size': data_size,
                    'created': time.time(),
                    'last_access': time.time(),
                    'hits': 0,
                    'video_path': video_path
                }
                
                # ✅ 更新反向索引
                if video_path not in self.path_index:
                    self.path_index[video_path] = []
                self.path_index[video_path].append(cache_key)
            
            logger.info(f"💾 Cached: {cache_key[:16]}... ({data_size / 1024:.1f} KB) - Total: {self._get_current_size() / 1024 / 1024:.1f} MB")
            
        except Exception as e:
            logger.error(f"❌ Failed to save cache: {e}")
    
    def invalidate(self, video_path: str) -> int:
        """
        使特定影片的所有快取失效
        
        Args:
            video_path: 影片路徑
            
        Returns:
            int: 被刪除的快取項目數量
        """
        removed_count = 0
        removed_size = 0
        
        with self.lock:
            # ✅ 使用反向索引快速找到相關快取
            cache_keys = self.path_index.get(video_path, []).copy()
            
            for cache_key in cache_keys:
                if cache_key in self.index:
                    item = self.index.pop(cache_key)
                    
                    try:
                        # 刪除快取檔案
                        item['path'].unlink(missing_ok=True)
                        
                        # 刪除 metadata 檔案
                        meta_path = self._get_meta_path(cache_key)
                        meta_path.unlink(missing_ok=True)
                        
                        removed_count += 1
                        removed_size += item['size']
                        
                    except Exception as e:
                        logger.error(f"❌ Failed to delete cache file: {e}")
            
            # ✅ 清除反向索引
            if video_path in self.path_index:
                del self.path_index[video_path]
        
        if removed_count > 0:
            logger.info(f"🗑️ Invalidated {removed_count} cache items ({removed_size / 1024 / 1024:.2f} MB) for: {video_path}")
        else:
            logger.info(f"ℹ️ No cache items found for: {video_path}")
        
        return removed_count
    
    def _cleanup_old_cache(self, required_space: int = 0):
        """
        清理舊快取（LRU 策略）
        
        Args:
            required_space: 需要的額外空間（bytes）
        """
        with self.lock:
            current_size = sum(item['size'] for item in self.index.values())
            target_size = self.max_size_bytes * 0.8  # 清理到 80%
            
            if required_space > 0:
                target_size = min(target_size, self.max_size_bytes - required_space)
            
            removed_count = 0
            removed_size = 0
            
            # ✅ 按照最少使用順序刪除（OrderedDict 的順序就是 LRU 順序）
            while current_size > target_size and self.index:
                # 取出最舊的項目
                cache_key, item = self.index.popitem(last=False)
                
                try:
                    item['path'].unlink(missing_ok=True)
                    
                    # 刪除 metadata 檔案
                    meta_path = self._get_meta_path(cache_key)
                    meta_path.unlink(missing_ok=True)
                    
                    # 更新反向索引
                    video_path = item.get('video_path')
                    if video_path and video_path in self.path_index:
                        try:
                            self.path_index[video_path].remove(cache_key)
                            if not self.path_index[video_path]:
                                del self.path_index[video_path]
                        except ValueError:
                            pass
                    
                    removed_size += item['size']
                    removed_count += 1
                    current_size -= item['size']
                    
                except Exception as e:
                    logger.error(f"❌ Failed to delete cache file: {e}")
            
            if removed_count > 0:
                logger.info(f"🗑️ Cleaned up {removed_count} files ({removed_size / 1024 / 1024:.1f} MB)")
    
    def clear(self):
        """清除所有快取"""
        with self.lock:
            removed_count = 0
            removed_size = 0
            
            for cache_key, item in list(self.index.items()):
                try:
                    item['path'].unlink(missing_ok=True)
                    
                    meta_path = self._get_meta_path(cache_key)
                    meta_path.unlink(missing_ok=True)
                    
                    removed_size += item['size']
                    removed_count += 1
                except Exception as e:
                    logger.error(f"❌ Failed to delete cache file: {e}")
            
            self.index.clear()
            self.path_index.clear()
            
            logger.info(f"🗑️ Cache cleared: {removed_count} files ({removed_size / 1024 / 1024:.1f} MB)")
    
    def get_stats(self) -> Dict:
        """
        獲取快取統計
        
        Returns:
            Dict: 統計資訊
        """
        with self.lock:
            total_size = sum(item['size'] for item in self.index.values())
            total_hits = sum(item['hits'] for item in self.index.values())
            total_accesses = sum(item['hits'] + 1 for item in self.index.values())  # +1 for initial set
            
            return {
                'items': len(self.index),
                'unique_videos': len(self.path_index),
                'size_mb': round(total_size / 1024 / 1024, 2),
                'max_size_mb': round(self.max_size_bytes / 1024 / 1024, 2),
                'utilization': round((total_size / self.max_size_bytes) * 100, 2),
                'total_hits': total_hits,
                'total_accesses': total_accesses,
                'hit_rate': round((total_hits / total_accesses * 100), 2) if total_accesses > 0 else 0,
                'cache_dir': str(self.cache_dir)
            }
    
    def get_detailed_stats(self) -> Dict:
        """
        獲取詳細統計（包含每個快取項目）
        
        Returns:
            Dict: 詳細統計
        """
        with self.lock:
            items = []
            
            for cache_key, item in self.index.items():
                items.append({
                    'key': cache_key[:16] + '...',
                    'video': item.get('video_path', 'unknown')[:50],
                    'size_kb': round(item['size'] / 1024, 2),
                    'hits': item['hits'],
                    'age_seconds': round(time.time() - item['created'], 2),
                    'last_access_seconds_ago': round(time.time() - item['last_access'], 2)
                })
            
            # 按照命中次數排序
            items.sort(key=lambda x: x['hits'], reverse=True)
            
            return {
                'summary': self.get_stats(),
                'top_items': items[:10]  # 只返回前 10 個
            }


# ==================== 全域快取實例 ====================

_video_cache: Optional[VideoCache] = None


def get_video_cache(cache_dir: str = "/tmp/video_cache", max_size_mb: int = 1000) -> VideoCache:
    """
    獲取全域影片快取實例（單例模式）
    
    Args:
        cache_dir: 快取目錄
        max_size_mb: 最大快取大小（MB）
        
    Returns:
        VideoCache 實例
    """
    global _video_cache
    
    if _video_cache is None:
        logger.info(f"🚀 Initializing global video cache")
        _video_cache = VideoCache(cache_dir=cache_dir, max_size_mb=max_size_mb)
    
    return _video_cache


def reset_video_cache():
    """重置全域快取"""
    global _video_cache
    
    if _video_cache:
        logger.info("🔄 Resetting video cache")
        _video_cache.clear()
        _video_cache = None
