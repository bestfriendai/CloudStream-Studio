"""
Storage 模組 - 統一使用 services.gcs_service
此模組僅作為兼容層，實際功能由 GCSService 提供
"""

from services.gcs_service import get_gcs_service, GCSService
import logging

logger = logging.getLogger(__name__)

# 為了向後兼容，提供別名
StorageManager = GCSService


def get_storage_manager() -> GCSService:
    """
    獲取 Storage Manager（實際返回 GCSService）
    
    Returns:
        GCSService: GCS Service 實例
    """
    return get_gcs_service()


# 導出主要類和函數
__all__ = [
    'GCSService',
    'StorageManager',
    'get_storage_manager',
    'get_gcs_service'
]
