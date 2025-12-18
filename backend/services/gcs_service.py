# backend/services/gcs_service.py

from google.cloud import storage
from google.cloud.exceptions import NotFound
from google.oauth2 import service_account
from config import get_settings
import logging
import os
from typing import Optional, List, Dict

logger = logging.getLogger(__name__)
settings = get_settings()


class GCSService:
    """Google Cloud Storage 服務"""
    
    def __init__(self):
        try:
            # 方法 1: 使用 Service Account JSON 檔案
            credentials_path = settings.GOOGLE_APPLICATION_CREDENTIALS
            
            if credentials_path and os.path.exists(credentials_path):
                logger.info(f"Loading credentials from: {credentials_path}")
                
                # 從 JSON 檔案載入憑證
                credentials = service_account.Credentials.from_service_account_file(
                    credentials_path,
                    scopes=['https://www.googleapis.com/auth/cloud-platform']
                )
                
                # 使用憑證創建 client
                self.client = storage.Client(
                    credentials=credentials,
                    project=settings.project_id
                )
                
                logger.info(f"✅ GCS Client initialized with Service Account")
                
            else:
                # 方法 2: 使用環境變數 (fallback)
                logger.warning(f"Service Account file not found: {credentials_path}")
                logger.info("Attempting to use Application Default Credentials...")
                
                self.client = storage.Client(project=settings.project_id)
            
            self.bucket = self.client.bucket(settings.GCS_BUCKET_NAME)
            self.bucket_name = settings.GCS_BUCKET_NAME
            
            # 測試連線
            if self.bucket.exists():
                logger.info(f"✅ Connected to bucket: {settings.GCS_BUCKET_NAME}")
            else:
                logger.error(f"❌ Bucket does not exist: {settings.GCS_BUCKET_NAME}")
                raise ValueError(f"Bucket not found: {settings.GCS_BUCKET_NAME}")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize GCS Service: {e}")
            raise
    
    def get_file_metadata(self, file_path: str) -> dict:
        """
        獲取文件元數據
        
        Args:
            file_path: 文件路徑
            
        Returns:
            dict: 文件元數據
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        try:
            blob = self.bucket.blob(file_path)
            
            if not blob.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")
            
            # 重新加載 blob 以獲取最新元數據
            blob.reload()
            
            return {
                'name': blob.name,
                'size': blob.size,
                'content_type': blob.content_type,
                'created': blob.time_created.isoformat() if blob.time_created else None,
                'updated': blob.updated.isoformat() if blob.updated else None,
                'md5_hash': blob.md5_hash,
                'public_url': blob.public_url,
                'metadata': blob.metadata or {}
            }
            
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"❌ 獲取文件元數據失敗 {file_path}: {e}")
            raise

    def upload_file(self, local_path: str, gcs_path: str) -> str:
        """
        上傳檔案到 GCS
        
        Args:
            local_path: 本地檔案路徑
            gcs_path: GCS 目標路徑
            
        Returns:
            GCS 公開 URL
        """
        try:
            blob = self.bucket.blob(gcs_path)
            blob.upload_from_filename(local_path)
            
            logger.info(f"✅ Uploaded {local_path} to gs://{self.bucket_name}/{gcs_path}")
            
            return self.get_public_url(gcs_path)
            
        except Exception as e:
            logger.error(f"❌ Failed to upload {local_path}: {e}")
            raise
    
    def upload_bytes(self, gcs_path: str, data: bytes, content_type: str = None) -> None:
        """
        上傳字節數據到 GCS
        
        Args:
            gcs_path: GCS 目標路徑
            data: 字節數據
            content_type: 內容類型
        """
        try:
            blob = self.bucket.blob(gcs_path)
            blob.upload_from_string(data, content_type=content_type)
            
            logger.info(f"✅ Uploaded {len(data)} bytes to gs://{self.bucket_name}/{gcs_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to upload bytes to {gcs_path}: {e}")
            raise
    
    def download_file(self, gcs_path: str, local_path: str = None) -> Optional[bytes]:
        """
        從 GCS 下載檔案
        
        Args:
            gcs_path: GCS 檔案路徑
            local_path: 本地目標路徑 (可選，如果不提供則返回字節)
            
        Returns:
            bytes: 如果沒有指定 local_path，返回文件內容
            None: 如果指定了 local_path
        """
        try:
            blob = self.bucket.blob(gcs_path)
            
            if not blob.exists():
                raise NotFound(f"File not found: gs://{self.bucket_name}/{gcs_path}")
            
            if local_path:
                blob.download_to_filename(local_path)
                logger.info(f"✅ Downloaded gs://{self.bucket_name}/{gcs_path} to {local_path}")
                return None
            else:
                content = blob.download_as_bytes()
                logger.info(f"✅ Downloaded gs://{self.bucket_name}/{gcs_path} ({len(content)} bytes)")
                return content
            
        except NotFound:
            logger.error(f"❌ File not found: gs://{self.bucket_name}/{gcs_path}")
            raise FileNotFoundError(f"GCS file not found: {gcs_path}")
        except Exception as e:
            logger.error(f"❌ Failed to download {gcs_path}: {e}")
            raise
    
    def delete_file(self, gcs_path: str) -> None:
        """刪除 GCS 檔案"""
        try:
            blob = self.bucket.blob(gcs_path)
            
            if blob.exists():
                blob.delete()
                logger.info(f"🗑️  Deleted gs://{self.bucket_name}/{gcs_path}")
            else:
                logger.warning(f"⚠️  File not found for deletion: {gcs_path}")
            
        except Exception as e:
            logger.error(f"❌ Failed to delete {gcs_path}: {e}")
            raise
    
    def file_exists(self, gcs_path: str) -> bool:
        """檢查檔案是否存在"""
        try:
            blob = self.bucket.blob(gcs_path)
            return blob.exists()
        except Exception as e:
            logger.error(f"❌ Error checking file existence: {e}")
            return False
    
    def get_public_url(self, gcs_path: str) -> str:
        """獲取檔案的公開 URL"""
        return f"https://storage.googleapis.com/{self.bucket_name}/{gcs_path}"
    
    def get_signed_url(self, gcs_path: str, expiration: int = 3600) -> str:
        """
        獲取簽名 URL（用於私有檔案）
        
        Args:
            gcs_path: GCS 檔案路徑
            expiration: 過期時間（秒）
        """
        try:
            blob = self.bucket.blob(gcs_path)
            url = blob.generate_signed_url(expiration=expiration)
            return url
        except Exception as e:
            logger.error(f"❌ Failed to generate signed URL: {e}")
            raise
    
    def list_files(self, prefix: str = "", delimiter: str = None) -> List[Dict]:
        """
        列出檔案
        
        Args:
            prefix: 路徑前綴
            delimiter: 分隔符（用於模擬目錄結構）
        """
        try:
            blobs = self.bucket.list_blobs(prefix=prefix, delimiter=delimiter)
            
            return [
                {
                    "name": blob.name,
                    "size": blob.size,
                    "content_type": blob.content_type,
                    "updated": blob.updated,
                    "public_url": self.get_public_url(blob.name)
                }
                for blob in blobs
            ]
        except Exception as e:
            logger.error(f"❌ Failed to list files: {e}")
            raise
    
    def get_file_info(self, gcs_path: str) -> Dict:
        """
        獲取檔案元數據
        
        Args:
            gcs_path: GCS 檔案路徑
            
        Returns:
            Dict: 檔案元數據
        """
        try:
            blob = self.bucket.blob(gcs_path)
            
            if not blob.exists():
                raise NotFound(f"File not found: gs://{self.bucket_name}/{gcs_path}")
            
            blob.reload()
            
            return {
                "name": blob.name,
                "size": blob.size,
                "content_type": blob.content_type,
                "created": blob.time_created,
                "updated": blob.updated,
                "md5_hash": blob.md5_hash,
                "public_url": self.get_public_url(blob.name)
            }
        except NotFound:
            raise FileNotFoundError(f"File not found: {gcs_path}")
        except Exception as e:
            logger.error(f"❌ Failed to get file metadata: {e}")
            raise


# ==================== 單例模式 ====================

_gcs_service_instance = None


def get_gcs_service() -> GCSService:
    """
    獲取 GCS Service 單例
    
    Returns:
        GCSService: GCS Service 實例
    """
    global _gcs_service_instance
    
    if _gcs_service_instance is None:
        _gcs_service_instance = GCSService()
        logger.info("✅ GCS Service 單例已創建")
    
    return _gcs_service_instance
