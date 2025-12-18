# backend/utils/__init__.py

"""
Utils 模組
統一使用 services.gcs_service.GCSService
"""

from services.gcs_service import GCSService, get_gcs_service

# 為了向後兼容，提供別名
GCSManager = GCSService

# 導出所有需要的類和函數
__all__ = [
    'GCSService',
    'GCSManager',  # 別名，向後兼容
    'get_gcs_service',
]
