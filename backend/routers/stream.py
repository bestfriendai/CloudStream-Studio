from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from services.gcs_service import GCSService
from services.gcs_cache import get_connection_pool, get_pool_status
from services.video_cache import get_video_cache
from config import get_settings
import mimetypes
import logging
import time
from typing import Optional
import re

router = APIRouter(prefix="/api", tags=["Video Streaming"])
logger = logging.getLogger(__name__)
settings = get_settings()
gcs_pool = get_connection_pool()
gcs_service = GCSService()
video_cache = get_video_cache(cache_dir="/tmp/video_cache", max_size_mb=1000)

# ==================== Range 請求解析 ====================
def parse_range_header(range_header: str, file_size: int) -> tuple:
    """
    解析 HTTP Range 請求頭
    
    Returns:
        (start, end, content_length)
        
    Note:
        - HTTP Range: "bytes=0-1023" 表示請求 bytes 0 到 1023（包含）
        - GCS download_as_bytes(start, end): 實測發現 end 也是 inclusive（包含）
    """
    range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    
    if not range_match:
        return 0, file_size - 1, file_size
    
    start = int(range_match.group(1))
    
    if range_match.group(2):
        end = int(range_match.group(2))  # HTTP Range 的 end 是 inclusive
    else:
        # 如果沒有指定 end，限制單次請求最多 20MB
        end = min(start + 20 * 1024 * 1024 - 1, file_size - 1)
    
    # 確保範圍有效
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    
    # Content-Length 是實際要傳輸的 bytes 數量
    content_length = end - start + 1
    
    logger.info(f"   📊 Range: bytes={start}-{end}/{file_size} (請求 {content_length:,} bytes)")
    
    return start, end, content_length

def get_content_type(filename: str) -> str:
    """根據檔案副檔名判斷 Content-Type"""
    content_type, _ = mimetypes.guess_type(filename)
    if content_type:
        return content_type
    
    # 手動處理常見影片格式
    ext = filename.lower().split('.')[-1]
    video_types = {
        'mp4': 'video/mp4',
        'webm': 'video/webm',
        'ogg': 'video/ogg',
        'mov': 'video/quicktime',
        'avi': 'video/x-msvideo',
        'mkv': 'video/x-matroska',
    }
    return video_types.get(ext, 'application/octet-stream')


# ==================== 影片串流 ====================
# ✅ GET 路由 - 注意這裡
@router.get("/stream/{filename:path}")
async def stream_video(filename: str, request: Request):
    """串流影片（支援 Range 請求）"""
    try:
        logger.info(f"📹 串流請求: {filename}")
        
        # 取得 bucket 和 blob
        bucket = gcs_pool.get_bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        
        # 檢查檔案是否存在
        if not blob.exists():
            logger.error(f"   ❌ 檔案不存在: {filename}")
            raise HTTPException(status_code=404, detail="檔案不存在")
        
        # 取得檔案資訊
        blob.reload()
        file_size = blob.size
        content_type = get_content_type(filename)
        
        logger.info(f"   檔案大小: {file_size:,} bytes")
        logger.info(f"   Content-Type: {content_type}")
        
        # 檢查 Range header
        range_header = request.headers.get("range")
        
        if not range_header:
            # 完整檔案請求
            logger.info(f"   📦 完整檔案請求")
            
            content = blob.download_as_bytes()
            
            headers = {
                "Content-Type": content_type,
                "Content-Length": str(len(content)),
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
            }
            
            logger.info(f"   ✅ 返回完整檔案: {len(content):,} bytes")
            
            return Response(
                content=content,
                status_code=200,
                headers=headers,
                media_type=content_type
            )
        
        # Range 請求
        logger.info(f"   📊 Range 請求: {range_header}")
        
        range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
        if not range_match:
            logger.error(f"   ❌ 無效的 Range header: {range_header}")
            raise HTTPException(status_code=400, detail="無效的 Range header")
        
        start = int(range_match.group(1))
        end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
        
        if start >= file_size or end >= file_size or start > end:
            logger.error(f"   ❌ 無效的範圍: {start}-{end} (檔案大小: {file_size})")
            raise HTTPException(
                status_code=416,
                detail="請求的範圍無效",
                headers={"Content-Range": f"bytes */{file_size}"}
            )
        
        length = end - start + 1
        logger.info(f"   範圍: {start:,}-{end:,} ({length:,} bytes)")
        
        content = blob.download_as_bytes(start=start, end=end + 1)
        
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(length),
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
        }
        
        logger.info(f"   ✅ 返回 206 Partial Content: {length:,} bytes")
        
        return Response(
            content=content,
            status_code=206,
            headers=headers,
            media_type=content_type
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 串流錯誤: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"串流錯誤: {str(e)}")


# ✅ HEAD 路由
@router.head("/stream/{filename:path}")
async def stream_head(filename: str):
    """處理 HEAD 請求"""
    try:
        bucket = gcs_pool.get_bucket(settings.GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        
        if not blob.exists():
            raise HTTPException(status_code=404, detail="檔案不存在")
        
        blob.reload()
        content_type = get_content_type(filename)
        
        headers = {
            "Content-Type": content_type,
            "Content-Length": str(blob.size),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Expose-Headers": "Content-Length, Accept-Ranges",
        }
        
        return Response(status_code=200, headers=headers)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ HEAD 錯誤: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ OPTIONS 路由（CORS）
@router.options("/stream/{filename:path}")
async def stream_options(filename: str):
    """處理 CORS preflight 請求"""
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "Range, Content-Type",
            "Access-Control-Expose-Headers": "Content-Length, Content-Range, Accept-Ranges",
            "Access-Control-Max-Age": "3600",
        }
    )
# ==================== HEAD 請求支援 ====================
@router.head("/stream/{filename:path}")
async def head_video(filename: str):
    """HEAD 請求：獲取影片 metadata"""
    try:
        metadata = gcs_pool.get_blob_metadata(settings.GCS_BUCKET_NAME, filename)
        
        if not metadata:
            raise HTTPException(status_code=404, detail="Video not found")
        
        headers = {
            "Content-Type": metadata.get("content_type", "video/mp4"),
            "Content-Length": str(metadata["size"]),
            "Accept-Ranges": "bytes",
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*"
        }
        
        return Response(
            status_code=200,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ HEAD request failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== 獲取影片縮圖 ====================
@router.get("/thumbnail/{filename:path}")
async def get_thumbnail(filename: str):
    """
    獲取影片縮圖
    """
    try:
        thumbnail_path = f"thumbnails/{filename}.jpg"
        
        if not gcs_service.file_exists(thumbnail_path):
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        
        bucket = gcs_service.bucket
        blob = bucket.blob(thumbnail_path)
        content = blob.download_as_bytes()
        
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=86400",
                "Access-Control-Allow-Origin": "*"
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 縮圖錯誤: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/cache/video/stats")
async def get_video_cache_stats():
    """獲取影片快取統計"""
    try:
        return video_cache.get_stats()
    except Exception as e:
        logger.error(f"❌ Failed to get video cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/cache/video/detailed")
async def get_video_cache_detailed():
    """獲取詳細快取統計"""
    try:
        return video_cache.get_detailed_stats()
    except Exception as e:
        logger.error(f"❌ Failed to get detailed stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/video/clear")
async def clear_video_cache():
    """清除影片快取"""
    try:
        video_cache.clear()
        return {
            "message": "Video cache cleared successfully",
            "stats": video_cache.get_stats()
        }
    except Exception as e:
        logger.error(f"❌ Failed to clear video cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ✅ 更新完整健康檢查
@router.get("/health/full")
async def full_health_check():
    """完整健康檢查"""
    try:
        gcs_healthy = gcs_pool.health_check()
        gcs_status = get_pool_status()
        video_cache_stats = video_cache.get_stats()
        
        return {
            "status": "healthy" if gcs_healthy else "unhealthy",
            "gcs": {
                "healthy": gcs_healthy,
                "pool_status": gcs_status
            },
            "cache": {
                "metadata": gcs_pool.get_cache_info(),
                "video": video_cache_stats
            },
            "timestamp": time.time()
        }
    except Exception as e:
        logger.error(f"❌ Health check failed: {e}")
        return {
            "status": "error",
            "error": str(e)
        }