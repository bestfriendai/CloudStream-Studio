from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from services.gcs_service import GCSService
from config import get_settings
import logging
from typing import List

router = APIRouter(prefix="/api", tags=["File Management"])
logger = logging.getLogger(__name__)
settings = get_settings()

gcs_service = GCSService()

# ==================== 列出所有檔案 ====================
@router.get("/files")
async def list_files(prefix: str = ""):
    """
    列出 GCS Bucket 中的所有檔案
    
    Args:
        prefix: 路徑前綴過濾
    """
    try:
        files = gcs_service.list_files(prefix=prefix)
        
        # 格式化回傳資料
        formatted_files = []
        for file in files:
            formatted_files.append({
                "name": file["name"],
                "size": file["size"],
                "content_type": file["content_type"],
                "updated": file["updated"].isoformat() if file["updated"] else None,
                "public_url": file["public_url"]
            })
        
        return {
            "success": True,
            "count": len(formatted_files),
            "files": formatted_files
        }
        
    except Exception as e:
        logger.error(f"Failed to list files: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 上傳檔案 ====================
@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    上傳檔案到 GCS Bucket
    
    支援的格式：
    - 影片：mp4, mov, avi, mkv, webm
    - 圖片：jpg, jpeg, png, gif
    """
    try:
        # 驗證檔案類型
        allowed_video_types = ["video/mp4", "video/quicktime", "video/x-msvideo", "video/x-matroska", "video/webm"]
        allowed_image_types = ["image/jpeg", "image/png", "image/gif"]
        
        if file.content_type not in allowed_video_types + allowed_image_types:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {file.content_type}"
            )
        
        # 檢查檔案大小
        content = await file.read()
        file_size = len(content)
        
        if file_size > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {settings.MAX_FILE_SIZE / 1024 / 1024 / 1024:.1f}GB"
            )
        
        # 決定上傳路徑
        if file.content_type.startswith("video/"):
            gcs_path = f"videos/{file.filename}"
        else:
            gcs_path = f"images/{file.filename}"
        
        # 檢查檔案是否已存在
        if gcs_service.file_exists(gcs_path):
            raise HTTPException(
                status_code=409,
                detail=f"File already exists: {file.filename}"
            )
        
        # 上傳到 GCS
        import tempfile
        import os
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_file.write(content)
            tmp_path = tmp_file.name
        
        try:
            public_url = gcs_service.upload_file(tmp_path, gcs_path)
            
            # 如果是影片，獲取元數據
            metadata = None
            if file.content_type.startswith("video/"):
                from app.services.ffmpeg_service import FFmpegService
                try:
                    ffmpeg_service = FFmpegService()
                    metadata = ffmpeg_service.get_video_info(tmp_path)
                except Exception as e:
                    logger.warning(f"Failed to get video metadata: {e}")
            
            return {
                "success": True,
                "message": "File uploaded successfully",
                "file": {
                    "name": file.filename,
                    "path": gcs_path,
                    "size": file_size,
                    "content_type": file.content_type,
                    "public_url": public_url,
                    "metadata": metadata
                }
            }
            
        finally:
            os.unlink(tmp_path)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 刪除檔案 ====================
@router.delete("/delete/{filename:path}")
async def delete_file(filename: str):
    """
    從 GCS Bucket 刪除檔案
    
    Args:
        filename: 檔案路徑（可包含子目錄）
    """
    try:
        # 檢查檔案是否存在
        if not gcs_service.file_exists(filename):
            raise HTTPException(status_code=404, detail="File not found")
        
        # 刪除檔案
        gcs_service.delete_file(filename)
        
        # 同時刪除相關的縮圖（如果存在）
        thumbnail_path = f"thumbnails/{filename}.jpg"
        if gcs_service.file_exists(thumbnail_path):
            gcs_service.delete_file(thumbnail_path)
        
        # 刪除 HLS 檔案（如果存在）
        video_name = filename.split('/')[-1].rsplit('.', 1)[0]
        hls_dir = f"hls/{video_name}"
        try:
            hls_files = gcs_service.list_files(prefix=hls_dir)
            for hls_file in hls_files:
                gcs_service.delete_file(hls_file["name"])
        except:
            pass
        
        return {
            "success": True,
            "message": f"File deleted: {filename}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 獲取檔案資訊 ====================
@router.get("/files/{filename:path}")
async def get_file_info(filename: str):
    """
    獲取檔案詳細資訊
    """
    try:
        if not gcs_service.file_exists(filename):
            raise HTTPException(status_code=404, detail="File not found")
        
        metadata = gcs_service.get_file_metadata(filename)
        
        # 如果是影片，嘗試獲取影片資訊
        if metadata["content_type"] and metadata["content_type"].startswith("video/"):
            # 檢查是否有 HLS 版本
            video_name = filename.split('/')[-1].rsplit('.', 1)[0]
            hls_master = f"hls/{video_name}/master.m3u8"
            
            if gcs_service.file_exists(hls_master):
                metadata["hls_url"] = gcs_service.get_public_url(hls_master)
            
            # 檢查是否有縮圖
            thumbnail_path = f"thumbnails/{filename}.jpg"
            if gcs_service.file_exists(thumbnail_path):
                metadata["thumbnail_url"] = gcs_service.get_public_url(thumbnail_path)
        
        return {
            "success": True,
            "file": metadata
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== 批次刪除 ====================
@router.post("/delete-batch")
async def delete_batch(filenames: List[str]):
    """
    批次刪除檔案
    """
    results = {
        "success": [],
        "failed": []
    }
    
    for filename in filenames:
        try:
            if gcs_service.file_exists(filename):
                gcs_service.delete_file(filename)
                results["success"].append(filename)
            else:
                results["failed"].append({
                    "filename": filename,
                    "error": "File not found"
                })
        except Exception as e:
            results["failed"].append({
                "filename": filename,
                "error": str(e)
            })
    
    return {
        "success": len(results["failed"]) == 0,
        "deleted": len(results["success"]),
        "failed": len(results["failed"]),
        "results": results
    }
