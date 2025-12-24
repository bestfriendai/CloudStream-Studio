from google.cloud import storage
from google.oauth2 import service_account
from google.auth.exceptions import RefreshError
from google.cloud.exceptions import NotFound
import logging
import os
import time
from typing import Optional, Dict
from threading import Lock
from collections import OrderedDict
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class MetadataCache:
    """自定義 Metadata 快取，支援單項失效"""
    
    def __init__(self, maxsize: int = 1000, ttl: int = 300):
        """
        Args:
            maxsize: 最大快取數量
            ttl: 快取存活時間（秒）
        """
        self._cache: OrderedDict[str, Dict] = OrderedDict()
        self._lock = Lock()
        self._maxsize = maxsize
        self._ttl = ttl
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Dict]:
        """獲取快取項目"""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None
            
            item = self._cache[key]
            
            # 檢查是否過期
            if time.time() - item['timestamp'] > self._ttl:
                del self._cache[key]
                self._misses += 1
                logger.debug(f"⏰ Cache expired: {key}")
                return None
            
            # 移到最後（LRU）
            self._cache.move_to_end(key)
            self._hits += 1
            
            return item['data']
    
    def set(self, key: str, data: Dict):
        """設置快取項目"""
        with self._lock:
            # 如果已存在，先刪除
            if key in self._cache:
                del self._cache[key]
            
            # 檢查容量
            while len(self._cache) >= self._maxsize:
                self._cache.popitem(last=False)
            
            self._cache[key] = {
                'data': data,
                'timestamp': time.time()
            }
    
    def invalidate(self, key: str) -> bool:
        """使特定項目失效"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.info(f"🗑️ Cache invalidated: {key}")
                return True
            return False
    
    def invalidate_prefix(self, prefix: str) -> int:
        """使所有符合前綴的項目失效"""
        with self._lock:
            keys_to_delete = [k for k in self._cache if k.startswith(prefix)]
            for key in keys_to_delete:
                del self._cache[key]
            
            if keys_to_delete:
                logger.info(f"🗑️ Invalidated {len(keys_to_delete)} items with prefix: {prefix}")
            
            return len(keys_to_delete)
    
    def clear(self):
        """清除所有快取"""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            self._hits = 0
            self._misses = 0
            logger.info(f"🗑️ Cache cleared: {count} items")
    
    def get_info(self) -> Dict:
        """獲取快取統計"""
        with self._lock:
            total = self._hits + self._misses
            return {
                'hits': self._hits,
                'misses': self._misses,
                'maxsize': self._maxsize,
                'currsize': len(self._cache),
                'hit_rate': self._hits / total if total > 0 else 0,
                'ttl': self._ttl
            }


class GCSConnectionPool:
    """GCS 連接池，支援服務帳號認證、自動重連和 metadata 快取"""
    
    def __init__(self):
        self._client: Optional[storage.Client] = None
        self._bucket: Optional[storage.Bucket] = None
        self._credentials = None
        self._initialized = False
        self._lock = Lock()
        
        # ✅ 使用自定義快取（支援單項失效）
        self._metadata_cache = MetadataCache(maxsize=1000, ttl=300)
        
    def _create_client(self) -> storage.Client:
        """創建 GCS client，優先使用服務帳號"""
        try:
            # ✅ 方法 1: 使用 Service Account JSON 檔案
            credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
            
            if credentials_path and os.path.exists(credentials_path):
                logger.info(f"🔐 Loading credentials from: {credentials_path}")
                
                # 從 JSON 檔案載入憑證
                self._credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                
                # 使用憑證創建 client
                client = storage.Client(
                    credentials=self._credentials,
                    project=settings.project_id
                )
                
                logger.info(f"✅ GCS Client initialized with Service Account (Project: {settings.project_id})")
                return client
                
            else:
                # ✅ 方法 2: 使用環境變數 (fallback)
                if credentials_path:
                    logger.warning(f"⚠️ Service Account file not found: {credentials_path}")
                
                logger.info("🔐 Attempting to use Application Default Credentials...")
                
                client = storage.Client(project=settings.project_id)
                logger.info("✅ GCS Client initialized with Application Default Credentials")
                return client
                
        except Exception as e:
            logger.error(f"❌ Failed to create GCS client: {e}", exc_info=True)
            raise
    
    @property
    def client(self) -> storage.Client:
        """獲取或創建 GCS client"""
        if self._client is None:
            logger.info("🔌 Initializing GCS client")
            self._client = self._create_client()
        
        return self._client
    
    def _reset_connection(self):
        """重置連接（用於認證過期時）"""
        logger.warning("🔄 Resetting GCS connection")
        self._client = None
        self._bucket = None
        self._credentials = None
        self._initialized = False
        # 清除快取
        self._metadata_cache.clear()
    
    def get_bucket(self, bucket_name: str) -> storage.Bucket:
        """獲取或創建 bucket 連接，支援自動重連"""
        try:
            if self._bucket is None or self._bucket.name != bucket_name:
                logger.info(f"🪣 Connecting to bucket: {bucket_name}")
                self._bucket = self.client.bucket(bucket_name)
                
                # 驗證 bucket 是否存在
                if not self._bucket.exists():
                    logger.error(f"❌ Bucket does not exist: {bucket_name}")
                    raise ValueError(f"Bucket not found: {bucket_name}")
                
                logger.info(f"✅ Connected to bucket: {bucket_name}")
                self._initialized = True
            
            return self._bucket
            
        except RefreshError as e:
            # ✅ 認證過期，重新創建連接
            logger.warning(f"⚠️ Authentication expired, attempting to reconnect: {e}")
            self._reset_connection()
            
            # 重試一次
            logger.info("🔄 Retrying connection...")
            self._bucket = self.client.bucket(bucket_name)
            
            if not self._bucket.exists():
                raise ValueError(f"Bucket does not exist: {bucket_name}")
            
            logger.info(f"✅ Reconnection successful: {bucket_name}")
            self._initialized = True
            return self._bucket
            
        except Exception as e:
            logger.error(f"❌ Failed to get bucket: {e}", exc_info=True)
            raise
    
    def get_blob_metadata(self, bucket_name: str, blob_name: str) -> Optional[Dict]:
        """
        獲取 blob metadata（帶快取）
        
        Args:
            bucket_name: GCS bucket 名稱
            blob_name: blob 路徑
            
        Returns:
            metadata dict 或 None（如果不存在）
        """
        cache_key = f"{bucket_name}:{blob_name}"
        
        # ✅ 先檢查快取
        cached = self._metadata_cache.get(cache_key)
        if cached is not None:
            logger.debug(f"📋 Metadata cache HIT: {blob_name}")
            return cached
        
        # ✅ 快取未命中，從 GCS 獲取
        try:
            bucket = self.get_bucket(bucket_name)
            blob = bucket.blob(blob_name)
            
            # 檢查是否存在
            if not blob.exists():
                logger.debug(f"📂 Blob not found: {blob_name}")
                return None
            
            # 重新載入以獲取最新 metadata
            blob.reload()
            
            metadata = {
                'name': blob.name,
                'size': blob.size,
                'content_type': blob.content_type,
                'created': blob.time_created.isoformat() if blob.time_created else None,
                'updated': blob.updated.isoformat() if blob.updated else None,
                'md5_hash': blob.md5_hash,
                'etag': blob.etag,
                'public_url': f"https://storage.googleapis.com/{bucket_name}/{blob.name}",
                'metadata': blob.metadata or {}
            }
            
            # ✅ 儲存到快取
            self._metadata_cache.set(cache_key, metadata)
            
            logger.debug(f"📋 Metadata cached: {blob_name} ({blob.size:,} bytes)")
            return metadata
            
        except RefreshError as e:
            # ✅ 認證過期，清除快取並重試
            logger.warning(f"⚠️ Authentication expired, clearing cache and retrying: {e}")
            
            self._reset_connection()
            
            # 重試一次
            try:
                bucket = self.get_bucket(bucket_name)
                blob = bucket.blob(blob_name)
                
                if not blob.exists():
                    return None
                
                blob.reload()
                
                metadata = {
                    'name': blob.name,
                    'size': blob.size,
                    'content_type': blob.content_type,
                    'created': blob.time_created.isoformat() if blob.time_created else None,
                    'updated': blob.updated.isoformat() if blob.updated else None,
                    'md5_hash': blob.md5_hash,
                    'etag': blob.etag,
                    'public_url': f"https://storage.googleapis.com/{bucket_name}/{blob.name}",
                    'metadata': blob.metadata or {}
                }
                
                self._metadata_cache.set(cache_key, metadata)
                
                logger.info(f"✅ Retry successful, metadata retrieved: {blob_name}")
                return metadata
                
            except Exception as retry_error:
                logger.error(f"❌ Retry failed: {retry_error}", exc_info=True)
                raise
            
        except NotFound:
            logger.debug(f"📂 File not found: {blob_name}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to get metadata ({blob_name}): {e}", exc_info=True)
            raise
    
    def invalidate_metadata_cache(self, bucket_name: str, blob_name: str):
        """
        使特定 blob 的 metadata 快取失效
        
        Args:
            bucket_name: GCS bucket 名稱
            blob_name: blob 路徑
        """
        cache_key = f"{bucket_name}:{blob_name}"
        self._metadata_cache.invalidate(cache_key)
    
    def invalidate_all_metadata_cache(self, bucket_name: str = None):
        """
        使所有 metadata 快取失效
        
        Args:
            bucket_name: 如果指定，只清除該 bucket 的快取
        """
        if bucket_name:
            self._metadata_cache.invalidate_prefix(f"{bucket_name}:")
        else:
            self._metadata_cache.clear()
    
    def file_exists(self, bucket_name: str, blob_name: str) -> bool:
        """
        檢查檔案是否存在
        
        Args:
            bucket_name: GCS bucket 名稱
            blob_name: blob 路徑
            
        Returns:
            bool: 檔案是否存在
        """
        try:
            metadata = self.get_blob_metadata(bucket_name, blob_name)
            return metadata is not None
        except Exception as e:
            logger.error(f"❌ Error checking file existence: {e}")
            return False
    
    def get_public_url(self, bucket_name: str, blob_name: str) -> str:
        """
        獲取檔案的公開 URL
        
        Args:
            bucket_name: GCS bucket 名稱
            blob_name: blob 路徑
            
        Returns:
            str: 公開 URL
        """
        return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"
    
    def clear_cache(self):
        """清除所有快取"""
        logger.info("🗑️ Clearing metadata cache")
        self._metadata_cache.clear()
    
    def get_cache_info(self) -> Dict:
        """
        獲取快取統計資訊
        
        Returns:
            Dict: 快取統計
        """
        return self._metadata_cache.get_info()
    
    def health_check(self) -> bool:
        """
        健康檢查：驗證連接是否正常
        
        Returns:
            bool: 連接是否正常
        """
        try:
            bucket = self.get_bucket(settings.GCS_BUCKET_NAME)
            # 嘗試列出一個 blob（限制 1 個）
            list(bucket.list_blobs(max_results=1))
            logger.info("✅ GCS connection health check passed")
            return True
        except Exception as e:
            logger.error(f"❌ GCS connection health check failed: {e}")
            return False
    
    def get_status(self) -> Dict:
        """
        獲取連接池狀態
        
        Returns:
            Dict: 狀態資訊
        """
        return {
            'initialized': self._initialized,
            'bucket_name': self._bucket.name if self._bucket else None,
            'project_id': settings.project_id,
            'using_service_account': self._credentials is not None,
            'cache_info': self.get_cache_info()
        }


# ==================== 全域連接池（單例模式）====================

_connection_pool: Optional[GCSConnectionPool] = None


def get_connection_pool() -> GCSConnectionPool:
    """
    獲取全域 GCS 連接池（單例模式）
    
    Returns:
        GCSConnectionPool: 連接池實例
    """
    global _connection_pool
    
    if _connection_pool is None:
        logger.info("🚀 Initializing global GCS connection pool")
        _connection_pool = GCSConnectionPool()
        
        # 執行健康檢查
        try:
            if _connection_pool.health_check():
                logger.info("✅ GCS connection pool initialized successfully")
            else:
                logger.warning("⚠️ GCS connection health check failed, but pool created")
        except Exception as e:
            logger.error(f"❌ Failed to perform initial health check: {e}")
    
    return _connection_pool


def reset_connection_pool():
    """
    重置全域連接池（用於測試或錯誤恢復）
    """
    global _connection_pool
    
    if _connection_pool:
        logger.info("🔄 Resetting global GCS connection pool")
        _connection_pool._reset_connection()
        _connection_pool = None


def get_pool_status() -> Dict:
    """
    獲取連接池狀態
    
    Returns:
        Dict: 狀態資訊
    """
    if _connection_pool is None:
        return {
            'initialized': False,
            'message': 'Connection pool not initialized'
        }
    
    return _connection_pool.get_status()
