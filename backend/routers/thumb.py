# backend/routers/thumb.py

"""
縮圖路由
提供影片縮圖生成和管理功能
"""

import logging
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import Response
from utils.thumbnails import get_thumbnail_generator

logger = logging.getLogger(__name__)

router = APIRouter(tags=["thumbnails"])


@router.get("/api/thumbnails/video/{video_path:path}")
async def get_video_thumbnail(
    video_path: str,
    width: int = Query(320, ge=1, le=1920, description="縮圖寬度"),
    height: int = Query(180, ge=1, le=1080, description="縮圖高度"),
    time_offset: float = Query(1.0, ge=0, description="時間偏移（秒）"),
    quality: int = Query(85, ge=1, le=100, description="JPEG 質量"),
    force_regenerate: bool = Query(False, description="強制重新生成")
):
    """
    獲取影片縮圖
    
    - **video_path**: 影片文件路徑
    - **width**: 縮圖寬度 (1-1920)
    - **height**: 縮圖高度 (1-1080)
    - **time_offset**: 從影片的哪個時間點截取（秒）
    - **quality**: JPEG 質量 (1-100)
    - **force_regenerate**: 是否強制重新生成（忽略快取）
    
    返回 JPEG 格式的縮圖圖片
    """
    try:
        logger.info(f"📥 收到縮圖請求:")
        logger.info(f"   路徑: {video_path}")
        logger.info(f"   參數: width={width}, height={height}, time_offset={time_offset}, quality={quality}")
        logger.info(f"   強制重新生成: {force_regenerate}")
        
        # 獲取 Thumbnail Generator
        generator = get_thumbnail_generator()
        
        # 生成或獲取縮圖
        thumbnail_data, is_new = await generator.get_or_create_thumbnail(
            video_path=video_path,
            width=width,
            height=height,
            time_offset=time_offset,
            quality=quality,
            force_regenerate=force_regenerate
        )
        
        logger.info(f"✅ 縮圖{'生成' if is_new else '快取'}成功: {len(thumbnail_data)} bytes")
        
        # 返回圖片
        return Response(
            content=thumbnail_data,
            media_type="image/jpeg",
            headers={
                # 快取策略：新生成的快取1小時，快取的快取24小時
                "Cache-Control": "public, max-age=3600" if is_new else "public, max-age=86400",
                "Content-Disposition": f'inline; filename="thumbnail_{width}x{height}.jpg"',
                "X-Thumbnail-Source": "generated" if is_new else "cached"
            }
        )
        
    except FileNotFoundError as e:
        logger.error(f"❌ 影片文件不存在: {video_path}")
        raise HTTPException(
            status_code=404,
            detail=f"影片文件不存在: {str(e)}"
        )
    except Exception as e:
        logger.error(f"❌ 獲取影片縮圖失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"縮圖生成失敗: {str(e)}"
        )


@router.delete("/api/thumbnails/video/{video_path:path}")
async def delete_video_thumbnail(
    video_path: str,
    width: int = Query(None, ge=1, le=1920),
    height: int = Query(None, ge=1, le=1080),
    time_offset: float = Query(None, ge=0)
):
    """
    刪除影片縮圖
    
    - 如果指定 width, height, time_offset，則只刪除特定縮圖
    - 如果不指定參數，則刪除該影片的所有縮圖
    """
    try:
        logger.info(f"🗑️  收到刪除縮圖請求:")
        logger.info(f"   路徑: {video_path}")
        
        generator = get_thumbnail_generator()
        
        if width and height and time_offset is not None:
            # 刪除特定縮圖
            logger.info(f"   刪除特定縮圖: {width}x{height} @ {time_offset}s")
            await generator.delete_thumbnail(
                video_path=video_path,
                width=width,
                height=height,
                time_offset=time_offset
            )
            return {
                "success": True,
                "message": f"已刪除縮圖: {width}x{height} @ {time_offset}s"
            }
        else:
            # 刪除所有縮圖
            logger.info(f"   刪除所有縮圖")
            await generator.delete_thumbnails(video_path)
            return {
                "success": True,
                "message": "已刪除所有縮圖"
            }
        
    except Exception as e:
        logger.error(f"❌ 刪除縮圖失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"刪除縮圖失敗: {str(e)}"
        )


@router.get("/api/thumbnails/info/{video_path:path}")
async def get_thumbnail_info(video_path: str):
    """
    獲取影片縮圖信息
    
    返回該影片所有縮圖的信息
    """
    try:
        logger.info(f"📊 獲取縮圖信息: {video_path}")
        
        generator = get_thumbnail_generator()
        info = generator.get_thumbnail_info(video_path)
        
        return info
        
    except Exception as e:
        logger.error(f"❌ 獲取縮圖信息失敗: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"獲取縮圖信息失敗: {str(e)}"
        )


@router.get("/api/thumbnails/health")
async def thumbnail_health_check():
    """
    縮圖服務健康檢查
    """
    try:
        generator = get_thumbnail_generator()
        
        return {
            "status": "healthy",
            "ffmpeg_available": generator.ffmpeg_path is not None,
            "ffmpeg_path": generator.ffmpeg_path,
            "thumbnail_prefix": generator.thumbnail_prefix
        }
        
    except Exception as e:
        logger.error(f"❌ 健康檢查失敗: {e}")
        raise HTTPException(
            status_code=503,
            detail=f"縮圖服務不可用: {str(e)}"
        )
