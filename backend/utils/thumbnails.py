"""
影片縮圖生成器
支持從 GCS 影片文件生成縮圖
"""

import tempfile
import os
import hashlib
import asyncio
import logging
import re
from pathlib import Path
from typing import Optional, Tuple
from services.gcs_service import GCSService

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """影片縮圖生成器"""
    
    def __init__(self, storage: GCSService):
        """
        初始化縮圖生成器
        
        Args:
            storage: GCS Storage 服務實例
        """
        self.storage = storage
        self.thumbnail_prefix = "thumbnails/"
        self.ffmpeg_path = None
        
        # 檢查 FFmpeg 是否可用
        self._check_ffmpeg()
        
        logger.info("✅ Thumbnail Generator 初始化完成")
    
    def _check_ffmpeg(self) -> None:
        """檢查 FFmpeg 是否安裝"""
        try:
            import shutil
            
            # 檢查 ffmpeg 是否在 PATH 中
            ffmpeg_path = shutil.which('ffmpeg')
            
            if ffmpeg_path:
                self.ffmpeg_path = ffmpeg_path
                logger.info(f"✅ FFmpeg 找到: {ffmpeg_path}")
                
                # 可選：嘗試快速驗證（但不阻塞）
                try:
                    import subprocess
                    result = subprocess.run(
                        [ffmpeg_path, '-version'],
                        capture_output=True,
                        text=True,
                        timeout=2  # 短超時
                    )
                    if result.returncode == 0:
                        version = result.stdout.split('\n')[0]
                        logger.info(f"   版本: {version}")
                except Exception as e:
                    logger.warning(f"⚠️  FFmpeg 版本檢查失敗（將繼續使用）: {e}")
                    
            else:
                logger.error("❌ FFmpeg 未找到在 PATH 中")
                logger.error("   當前 PATH:")
                import os as os_module
                logger.error(f"   {os_module.environ.get('PATH', 'N/A')}")
                raise RuntimeError(
                    "FFmpeg 不可用。請確認已安裝並在 PATH 中。\n"
                    "安裝方法: brew install ffmpeg"
                )
                
        except Exception as e:
            logger.error(f"❌ FFmpeg 檢查失敗: {e}")
            raise
    
    def _clean_video_path(self, video_path: str) -> str:
        """
        清理影片路徑
        
        處理規則:
        1. Sample 文件 ({uuid}/video.mp4/{timestamp}/sample_N.mp4) - 保持不變
        2. 普通文件 - 確保有擴展名
        
        Args:
            video_path: 原始路徑
            
        Returns:
            str: 清理後的路徑
        """
        # 移除開頭和結尾的斜線
        original = video_path
        video_path = video_path.strip('/')
        
        logger.debug(f"🧹 清理路徑: {original}")
        
        # 如果是 sample 文件，直接返回
        # 格式: {uuid}/video.mp4/{timestamp}/sample_N.mp4
        sample_pattern = r'^[^/]+/[^/]+\.mp4/\d+/sample_\d+\.mp4$'
        if re.match(sample_pattern, video_path):
            logger.debug(f"   類型: Sample 文件（保持原樣）")
            logger.debug(f"   結果: {video_path}")
            return video_path
        
        # 確保有有效的影片擴展名
        valid_extensions = ('.mp4', '.mov', '.avi', '.mkv', '.webm', '.flv', '.wmv', '.m4v')
        if not video_path.lower().endswith(valid_extensions):
            if '.' not in Path(video_path).name:
                video_path += '.mp4'
                logger.info(f"➕ 添加擴展名: {video_path}")
        
        logger.debug(f"   類型: 普通文件")
        logger.debug(f"   結果: {video_path}")
        
        return video_path
    
    def _generate_thumbnail_key(
        self,
        video_path: str,
        width: int,
        height: int,
        time_offset: float
    ) -> str:
        """
        生成縮圖的 GCS 鍵
        
        Args:
            video_path: 影片路徑
            width: 寬度
            height: 高度
            time_offset: 時間偏移
            
        Returns:
            str: 縮圖的 GCS 路徑
        """
        # 生成唯一的哈希值
        hash_input = f"{video_path}_{width}_{height}_{time_offset}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()[:12]
        
        # 構建縮圖路徑
        video_name = Path(video_path).stem
        thumbnail_name = f"{video_name}_{width}x{height}_t{time_offset}_{hash_value}.jpg"
        
        return f"{self.thumbnail_prefix}{thumbnail_name}"
    
    async def _generate_thumbnail_with_ffmpeg(
        self,
        video_path: str,
        width: int,
        height: int,
        time_offset: float,
        quality: int = 85
    ) -> bytes:
        """
        使用 FFmpeg 生成縮圖
        
        Args:
            video_path: 本地影片文件路徑
            width: 縮圖寬度
            height: 縮圖高度
            time_offset: 時間偏移（秒）
            quality: JPEG 質量 (1-100)
            
        Returns:
            bytes: JPEG 縮圖數據
        """
        # 使用已檢查的 ffmpeg 路徑
        ffmpeg_cmd = self.ffmpeg_path or 'ffmpeg'
        
        # 創建臨時輸出文件
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp_output:
            output_path = tmp_output.name
        
        try:
            # FFmpeg 質量轉換 (1-100 -> 2-31, 數字越小質量越高)
            ffmpeg_quality = max(2, min(31, int((100 - quality) * 0.29 + 2)))
            
            cmd = [
                ffmpeg_cmd,
                '-ss', str(time_offset),
                '-i', video_path,
                '-vframes', '1',
                '-vf', f'scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2',
                '-q:v', str(ffmpeg_quality),
                '-y',  # 覆蓋輸出文件
                output_path
            ]
            
            logger.info(f"🎬 執行 FFmpeg 命令")
            logger.debug(f"   命令: {' '.join(cmd)}")
            
            # 執行 FFmpeg（使用 asyncio）
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                error_msg = stderr.decode('utf-8', errors='ignore')
                logger.error(f"❌ FFmpeg 錯誤:")
                logger.error(f"   返回碼: {process.returncode}")
                logger.error(f"   錯誤信息: {error_msg[:500]}")
                raise RuntimeError(f"FFmpeg 失敗: {error_msg[:200]}")
            
            # 讀取生成的縮圖
            if not os.path.exists(output_path):
                raise RuntimeError("FFmpeg 未生成輸出文件")
            
            with open(output_path, 'rb') as f:
                thumbnail_data = f.read()
            
            if not thumbnail_data:
                raise RuntimeError("生成的縮圖為空")
            
            logger.info(f"✅ FFmpeg 生成縮圖成功: {len(thumbnail_data)} bytes")
            
            return thumbnail_data
            
        finally:
            # 清理臨時文件
            try:
                if os.path.exists(output_path):
                    os.unlink(output_path)
            except Exception as e:
                logger.warning(f"⚠️  清理臨時文件失敗: {e}")
    
    async def get_or_create_thumbnail(
        self,
        video_path: str,
        width: int = 320,
        height: int = 180,
        time_offset: float = 1.0,
        quality: int = 85,
        force_regenerate: bool = False
    ) -> Tuple[bytes, bool]:
        """
        獲取或創建縮圖
        
        Args:
            video_path: 影片文件路徑
            width: 縮圖寬度
            height: 縮圖高度
            time_offset: 時間偏移（秒）
            quality: JPEG 質量 (1-100)
            force_regenerate: 是否強制重新生成（忽略快取）
            
        Returns:
            Tuple[bytes, bool]: (縮圖數據, 是否新生成)
            
        Raises:
            FileNotFoundError: 影片文件不存在
            Exception: 生成縮圖失敗
        """
        try:
            # 記錄原始路徑
            original_path = video_path
            
            logger.info(f"🎬 獲取或創建縮圖:")
            logger.info(f"   原始路徑: {original_path}")
            
            # 清理路徑
            video_path = self._clean_video_path(video_path)
            
            if video_path != original_path.strip('/'):
                logger.info(f"   清理後路徑: {video_path}")
            
            logger.info(f"   尺寸: {width}x{height}")
            logger.info(f"   時間: {time_offset}s")
            logger.info(f"   質量: {quality}")
            logger.info(f"   強制重新生成: {force_regenerate}")
            
            # 檢查影片文件是否存在
            if not self.storage.file_exists(video_path):
                logger.error(f"❌ 影片文件不存在: {video_path}")
                
                # 🔍 詳細調試：列出可能的文件
                parts = video_path.split('/')
                if len(parts) > 0:
                    uuid_part = parts[0]  # 第一部分應該是 UUID
                    
                    logger.info(f"🔍 搜索 UUID: {uuid_part}")
                    logger.info(f"🔍 嘗試列出該 UUID 下的所有文件...")
                    
                    try:
                        # 列出該 UUID 目錄下的所有文件
                        files = self.storage.list_files(prefix=uuid_part)
                        logger.info(f"📁 找到 {len(files)} 個文件:")
                        
                        for i, f in enumerate(files[:10]):  # 只顯示前10個
                            file_name = f.get('name', 'unknown')
                            file_size = f.get('size', 0)
                            logger.info(f"   {i+1}. {file_name} ({file_size} bytes)")
                        
                        if len(files) > 10:
                            logger.info(f"   ... 還有 {len(files) - 10} 個文件")
                        
                        # 🎯 嘗試找到實際的影片文件
                        video_files = [f for f in files if f.get('name', '').endswith(('.mp4', '.mov', '.avi'))]
                        if video_files:
                            logger.info(f"🎥 找到 {len(video_files)} 個影片文件:")
                            for vf in video_files[:5]:
                                logger.info(f"   - {vf.get('name')}")
                            
                            # 建議正確的路徑
                            if video_files:
                                suggested_path = video_files[0].get('name')
                                logger.info(f"💡 建議使用路徑: {suggested_path}")
                        
                    except Exception as e:
                        logger.error(f"❌ 列出文件失敗: {e}")
                
                raise FileNotFoundError(f"影片文件不存在: {video_path}")
            
            # 生成縮圖鍵
            thumbnail_key = self._generate_thumbnail_key(
                video_path, width, height, time_offset
            )
            
            logger.info(f"🔑 縮圖鍵: {thumbnail_key}")
            
            # 檢查快取（除非強制重新生成）
            if not force_regenerate and self.storage.file_exists(thumbnail_key):
                logger.info(f"✅ 使用快取縮圖: {thumbnail_key}")
                cached_data = self.storage.download_file(thumbnail_key)
                logger.info(f"📦 快取縮圖大小: {len(cached_data)} bytes")
                return cached_data, False  # 返回快取數據，is_new=False
            
            # 生成新縮圖
            if force_regenerate:
                logger.info(f"🔄 強制重新生成縮圖...")
            else:
                logger.info(f"🎨 生成新縮圖...")
            
            # 下載影片文件
            logger.info(f"⬇️  下載影片: {video_path}")
            video_data = self.storage.download_file(video_path)
            logger.info(f"📦 影片大小: {len(video_data)} bytes ({len(video_data) / 1024 / 1024:.2f} MB)")
            
            # 保存到臨時文件
            with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp_video:
                tmp_video.write(video_data)
                tmp_video_path = tmp_video.name
            
            logger.info(f"💾 臨時文件: {tmp_video_path}")
            
            try:
                # 使用 FFmpeg 生成縮圖
                thumbnail_data = await self._generate_thumbnail_with_ffmpeg(
                    tmp_video_path,
                    width,
                    height,
                    time_offset,
                    quality
                )
                
                # 上傳到 GCS（覆蓋現有文件）
                logger.info(f"⬆️  上傳縮圖到 GCS: {thumbnail_key}")
                self.storage.upload_bytes(
                    thumbnail_key,
                    thumbnail_data,
                    content_type='image/jpeg'
                )
                
                logger.info(f"✅ 縮圖已生成並上傳: {thumbnail_key} ({len(thumbnail_data)} bytes)")
                
                return thumbnail_data, True  # 返回新數據，is_new=True
                
            finally:
                # 清理臨時文件
                try:
                    if os.path.exists(tmp_video_path):
                        os.unlink(tmp_video_path)
                        logger.info(f"🗑️  已清理臨時文件: {tmp_video_path}")
                except Exception as e:
                    logger.warning(f"⚠️  清理臨時文件失敗: {e}")
                    
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(f"❌ 獲取或創建縮圖失敗: {e}", exc_info=True)
            raise Exception(f"無法獲取或創建縮圖: {str(e)}")
    
    async def generate_thumbnail(
        self,
        video_path: str,
        width: int = 320,
        height: int = 180,
        time_offset: float = 1.0,
        quality: int = 85
    ) -> bytes:
        """
        生成影片縮圖（簡化版本，只返回數據）
        
        Args:
            video_path: 影片文件路徑
            width: 縮圖寬度
            height: 縮圖高度
            time_offset: 時間偏移（秒）
            quality: JPEG 質量 (1-100)
            
        Returns:
            bytes: JPEG 縮圖數據
            
        Raises:
            FileNotFoundError: 影片文件不存在
            Exception: 生成縮圖失敗
        """
        thumbnail_data, _ = await self.get_or_create_thumbnail(
            video_path=video_path,
            width=width,
            height=height,
            time_offset=time_offset,
            quality=quality,
            force_regenerate=False
        )
        return thumbnail_data
    
    async def delete_thumbnail(
        self,
        video_path: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        time_offset: Optional[float] = None
    ) -> None:
        """
        刪除特定的縮圖
        
        Args:
            video_path: 影片路徑
            width: 寬度（可選，如果指定則只刪除特定尺寸）
            height: 高度（可選）
            time_offset: 時間偏移（可選）
        """
        try:
            # 清理路徑
            video_path = self._clean_video_path(video_path)
            
            if width and height and time_offset is not None:
                # 刪除特定縮圖
                thumbnail_key = self._generate_thumbnail_key(
                    video_path, width, height, time_offset
                )
                logger.info(f"🗑️  刪除縮圖: {thumbnail_key}")
                
                if self.storage.file_exists(thumbnail_key):
                    self.storage.delete_file(thumbnail_key)
                    logger.info(f"✅ 已刪除: {thumbnail_key}")
                else:
                    logger.warning(f"⚠️  縮圖不存在: {thumbnail_key}")
            else:
                # 刪除所有相關縮圖
                await self.delete_thumbnails(video_path)
                
        except Exception as e:
            logger.error(f"❌ 刪除縮圖失敗: {e}")
            raise
    
    async def delete_thumbnails(self, video_path: str) -> None:
        """
        刪除影片的所有縮圖
        
        Args:
            video_path: 影片路徑
        """
        try:
            # 清理路徑
            video_path = self._clean_video_path(video_path)
            
            logger.info(f"🗑️  刪除所有縮圖: {video_path}")
            
            # 列出所有相關的縮圖
            video_name = Path(video_path).stem
            prefix = f"{self.thumbnail_prefix}{video_name}_"
            
            thumbnails = self.storage.list_files(prefix=prefix)
            
            logger.info(f"📋 找到 {len(thumbnails)} 個縮圖")
            
            # 刪除所有縮圖
            deleted_count = 0
            for thumb in thumbnails:
                try:
                    self.storage.delete_file(thumb['name'])
                    deleted_count += 1
                    logger.info(f"✅ 已刪除: {thumb['name']}")
                except Exception as e:
                    logger.error(f"❌ 刪除失敗 {thumb['name']}: {e}")
            
            logger.info(f"✅ 縮圖刪除完成: {deleted_count}/{len(thumbnails)}")
            
        except Exception as e:
            logger.error(f"❌ 刪除縮圖失敗: {e}")
            raise
    
    def get_thumbnail_info(self, video_path: str) -> dict:
        """
        獲取影片縮圖信息
        
        Args:
            video_path: 影片路徑
            
        Returns:
            dict: 縮圖信息
        """
        try:
            # 清理路徑
            video_path = self._clean_video_path(video_path)
            
            # 列出所有相關的縮圖
            video_name = Path(video_path).stem
            prefix = f"{self.thumbnail_prefix}{video_name}_"
            
            thumbnails = self.storage.list_files(prefix=prefix)
            
            return {
                "video_path": video_path,
                "thumbnail_count": len(thumbnails),
                "thumbnails": [
                    {
                        "name": thumb['name'],
                        "size": thumb['size'],
                        "url": thumb.get('public_url'),
                        "updated": thumb.get('updated')
                    }
                    for thumb in thumbnails
                ]
            }
            
        except Exception as e:
            logger.error(f"❌ 獲取縮圖信息失敗: {e}")
            return {
                "video_path": video_path,
                "error": str(e)
            }


# ==================== 單例模式 ====================

_thumbnail_generator_instance: Optional[ThumbnailGenerator] = None


def get_thumbnail_generator() -> ThumbnailGenerator:
    """
    獲取 Thumbnail Generator 單例
    
    Returns:
        ThumbnailGenerator: Thumbnail Generator 實例
    """
    global _thumbnail_generator_instance
    
    if _thumbnail_generator_instance is None:
        from services.gcs_service import get_gcs_service
        storage = get_gcs_service()
        _thumbnail_generator_instance = ThumbnailGenerator(storage)
        logger.info("✅ Thumbnail Generator 單例已創建")
    
    return _thumbnail_generator_instance


def set_thumbnail_generator(generator: ThumbnailGenerator) -> None:
    """
    設置 Thumbnail Generator 實例（用於測試或手動配置）
    
    Args:
        generator: ThumbnailGenerator 實例
    """
    global _thumbnail_generator_instance
    _thumbnail_generator_instance = generator
    logger.info("✅ Thumbnail Generator 已設置")


def reset_thumbnail_generator() -> None:
    """重置 Thumbnail Generator 單例（用於測試）"""
    global _thumbnail_generator_instance
    _thumbnail_generator_instance = None
    logger.info("🔄 Thumbnail Generator 已重置")
