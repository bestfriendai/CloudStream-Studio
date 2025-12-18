from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, Response
from services.gcs_service import GCSService
from config import get_settings
import logging
from typing import Optional
import re

router = APIRouter(prefix="/api", tags=["Video Streaming"])
logger = logging.getLogger(__name__)
settings = get_settings()

gcs_service = GCSService()

# ==================== Range 請求解析 ====================
def parse_range_header(range_header: str, file_size: int) -> tuple:
    """
    解析 HTTP Range 請求頭
    
    Returns:
        (start, end, content_length)
    """
    range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
    
    if not range_match:
        return 0, file_size - 1, file_size
    
    start = int(range_match.group(1))
    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
    
    # 確保範圍有效
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    
    content_length = end - start + 1
    
    return start, end, content_length

# ==================== 影片串流 ====================
@router.get("/stream/{filename:path}")
async def stream_video(filename: str, request: Request):
    """
    串流影片（支援 Range 請求）
    
    支援：
    - HTTP Range requests (部分內容請求)
    - 快進/快退
    - 暫停/繼續播放
    """
    try:
        # 檢查檔案是否存在
        if not gcs_service.file_exists(filename):
            raise HTTPException(status_code=404, detail="Video not found")
        
        # 獲取檔案元數據
        metadata = gcs_service.get_file_metadata(filename)
        file_size = metadata["size"]
        content_type = metadata["content_type"] or "video/mp4"
        
        # 檢查是否為 Range 請求
        range_header = request.headers.get("range")
        
        if range_header:
            # 處理 Range 請求
            start, end, content_length = parse_range_header(range_header, file_size)
            
            logger.info(f"Range request: {filename} bytes={start}-{end}/{file_size}")
            
            # 從 GCS 讀取指定範圍
            bucket = gcs_service.bucket
            blob = bucket.blob(filename)
            
            # 下載指定範圍的資料
            chunk = blob.download_as_bytes(start=start, end=end + 1)
            
            # 返回 206 Partial Content
            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": content_type,
                "Cache-Control": "public, max-age=3600"
            }
            
            return Response(
                content=chunk,
                status_code=206,
                headers=headers
            )
        
        else:
            # 完整檔案請求
            logger.info(f"Full file request: {filename}")
            
            bucket = gcs_service.bucket
            blob = bucket.blob(filename)
            
            # 使用串流方式返回
            def iterfile():
                chunk_size = 1024 * 1024  # 1MB chunks
                start = 0
                
                while start < file_size:
                    end = min(start + chunk_size, file_size)
                    chunk = blob.download_as_bytes(start=start, end=end)
                    yield chunk
                    start = end
            
            headers = {
                "Content-Length": str(file_size),
                "Content-Type": content_type,
                "Accept-Ranges": "bytes",
                "Cache-Control": "public, max-age=3600"
            }
            
            return StreamingResponse(
                iterfile(),
                headers=headers,
                media_type=content_type
            )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Streaming error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== HLS 串流 ====================
@router.get("/stream-hls/{video_name}/{filename}")
async def stream_hls(video_name: str, filename: str):
    """
    串流 HLS 檔案（.m3u8 playlist 或 .ts segments）
    
    Args:
        video_name: 影片名稱（目錄）
        filename: 檔案名稱（master.m3u8, 720p.m3u8, 720p_001.ts 等）
    """
    try:
        hls_path = f"hls/{video_name}/{filename}"
        
        if not gcs_service.file_exists(hls_path):
            raise HTTPException(status_code=404, detail="HLS file not found")
        
        # 獲取檔案
        bucket = gcs_service.bucket
        blob = bucket.blob(hls_path)
        content = blob.download_as_bytes()
        
        # 設定 Content-Type
        if filename.endswith('.m3u8'):
            content_type = "application/vnd.apple.mpegurl"
        elif filename.endswith('.ts'):
            content_type = "video/mp2t"
        else:
            content_type = "application/octet-stream"
        
        headers = {
            "Content-Type": content_type,
            "Cache-Control": "public, max-age=3600",
            "Access-Control-Allow-Origin": "*"
        }
        
        return Response(
            content=content,
            headers=headers
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"HLS streaming error: {e}")
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
            # 如果縮圖不存在，返回預設圖片或 404
            raise HTTPException(status_code=404, detail="Thumbnail not found")
        
        bucket = gcs_service.bucket
        blob = bucket.blob(thumbnail_path)
        content = blob.download_as_bytes()
        
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Thumbnail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 預覽縮圖序列 ====================
@router.get("/preview-thumbnails/{video_name}/{index}")
async def get_preview_thumbnail(video_name: str, index: int):
    """
    獲取預覽縮圖（用於 timeline scrubbing）
    
    Args:
        video_name: 影片名稱
        index: 縮圖索引
    """
    try:
        thumb_path = f"hls/{video_name}/thumbnails/thumb_{index:04d}.jpg"
        
        if not gcs_service.file_exists(thumb_path):
            raise HTTPException(status_code=404, detail="Preview thumbnail not found")
        
        bucket = gcs_service.bucket
        blob = bucket.blob(thumb_path)
        content = blob.download_as_bytes()
        
        return Response(
            content=content,
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=86400"}
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Preview thumbnail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
