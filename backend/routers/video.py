from fastapi import APIRouter, BackgroundTasks, HTTPException
from models import ClipRequest, MergeRequest, TaskResponse, HLSConversionRequest
from services.gcs_service import GCSService
from services.ffmpeg_service import FFmpegService
from services.hls_service import HLSService
from utils.task_manager import task_manager
from config import get_settings
import tempfile
import os
import shutil
import logging

router = APIRouter(prefix="/api/video", tags=["Video Processing"])
logger = logging.getLogger(__name__)
settings = get_settings()

gcs_service = GCSService()
ffmpeg_service = FFmpegService()
hls_service = HLSService()

# ==================== 剪輯單一影片 ====================
@router.post("/clip", response_model=TaskResponse)
async def clip_video(request: ClipRequest, background_tasks: BackgroundTasks):
    """
    剪輯單一影片片段
    """
    # 創建任務
    task_id = task_manager.create_task("Clip task created")
    
    # 在背景執行
    background_tasks.add_task(
        process_clip_task,
        task_id,
        request
    )
    
    return TaskResponse(
        task_id=task_id,
        message="Clip task started",
        status_url=f"/api/tasks/{task_id}"
    )

async def process_clip_task(task_id: str, request: ClipRequest):
    """執行剪輯任務"""
    temp_dir = tempfile.mkdtemp(prefix="clip_")
    
    try:
        # 更新狀態：開始處理
        task_manager.update_task(
            task_id,
            status="processing",
            progress=0.1,
            message="Downloading source video..."
        )
        
        # 1. 下載原始影片
        local_input = os.path.join(temp_dir, "input.mp4")
        gcs_service.download_file(request.source_video, local_input)
        
        task_manager.update_task(task_id, progress=0.3, message="Clipping video...")
        
        # 2. 剪輯影片
        local_output = os.path.join(temp_dir, "output.mp4")
        ffmpeg_service.clip_video(
            local_input,
            local_output,
            request.start_time,
            request.end_time,
            re_encode=False
        )
        
        task_manager.update_task(task_id, progress=0.7, message="Uploading to GCS...")
        
        # 3. 上傳到 GCS
        output_path = f"clips/{request.output_name}"
        gcs_service.upload_file(local_output, output_path)
        
        # 4. 生成縮圖
        thumbnail_local = os.path.join(temp_dir, "thumbnail.jpg")
        ffmpeg_service.generate_thumbnail(local_output, thumbnail_local)
        
        thumbnail_path = f"thumbnails/{request.output_name}.jpg"
        gcs_service.upload_file(thumbnail_local, thumbnail_path)
        
        # 完成
        output_url = gcs_service.get_public_url(output_path)
        
        task_manager.update_task(
            task_id,
            status="completed",
            progress=1.0,
            message="Clip completed successfully",
            output_url=output_url,
            output_path=output_path
        )
        
        logger.info(f"Clip task {task_id} completed: {output_url}")
        
    except Exception as e:
        logger.error(f"Clip task {task_id} failed: {e}")
        task_manager.update_task(
            task_id,
            status="failed",
            error=str(e),
            message=f"Clip failed: {str(e)}"
        )
    
    finally:
        # 清理臨時檔案
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== 合併多個片段 ====================
@router.post("/merge", response_model=TaskResponse)
async def merge_videos(request: MergeRequest, background_tasks: BackgroundTasks):
    """
    合併多個影片片段
    """
    if len(request.clips) < 1:
        raise HTTPException(status_code=400, detail="At least one clip is required")
    
    task_id = task_manager.create_task("Merge task created")
    
    background_tasks.add_task(
        process_merge_task,
        task_id,
        request
    )
    
    return TaskResponse(
        task_id=task_id,
        message="Merge task started",
        status_url=f"/api/tasks/{task_id}"
    )

async def process_merge_task(task_id: str, request: MergeRequest):
    """執行合併任務"""
    temp_dir = tempfile.mkdtemp(prefix="merge_")
    clip_files = []
    
    try:
        task_manager.update_task(
            task_id,
            status="processing",
            progress=0.1,
            message="Processing clips..."
        )
        
        total_clips = len(request.clips)
        
        # 1. 處理每個片段
        for i, clip in enumerate(request.clips):
            # 下載原始影片
            local_input = os.path.join(temp_dir, f"input_{i}.mp4")
            gcs_service.download_file(clip.source_video, local_input)
            
            # 剪輯片段
            clip_output = os.path.join(temp_dir, f"clip_{i}.mp4")
            ffmpeg_service.clip_video(
                local_input,
                clip_output,
                clip.start_time,
                clip.end_time,
                re_encode=True  # 合併時需要重新編碼以確保兼容性
            )
            
            clip_files.append(clip_output)
            
            # 更新進度
            progress = 0.1 + (0.6 * (i + 1) / total_clips)
            task_manager.update_task(
                task_id,
                progress=progress,
                message=f"Processed clip {i+1}/{total_clips}"
            )
        
        # 2. 合併影片
        task_manager.update_task(task_id, progress=0.7, message="Merging clips...")
        
        merged_output = os.path.join(temp_dir, "merged.mp4")
        ffmpeg_service.merge_videos(clip_files, merged_output, re_encode=False)
        
        # 3. 上傳到 GCS
        task_manager.update_task(task_id, progress=0.9, message="Uploading result...")
        
        output_path = f"merged/{request.output_name}"
        gcs_service.upload_file(merged_output, output_path)
        
        # 4. 生成縮圖
        thumbnail_local = os.path.join(temp_dir, "thumbnail.jpg")
        ffmpeg_service.generate_thumbnail(merged_output, thumbnail_local)
        
        thumbnail_path = f"thumbnails/{request.output_name}.jpg"
        gcs_service.upload_file(thumbnail_local, thumbnail_path)
        
        # 完成
        output_url = gcs_service.get_public_url(output_path)
        
        task_manager.update_task(
            task_id,
            status="completed",
            progress=1.0,
            message="Merge completed successfully",
            output_url=output_url,
            output_path=output_path
        )
        
        logger.info(f"Merge task {task_id} completed: {output_url}")
        
    except Exception as e:
        logger.error(f"Merge task {task_id} failed: {e}")
        task_manager.update_task(
            task_id,
            status="failed",
            error=str(e),
            message=f"Merge failed: {str(e)}"
        )
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ==================== HLS 轉換 ====================
@router.post("/convert-hls", response_model=TaskResponse)
async def convert_to_hls(request: HLSConversionRequest, background_tasks: BackgroundTasks):
    """
    將影片轉換為 HLS 格式
    """
    task_id = task_manager.create_task("HLS conversion task created")
    
    background_tasks.add_task(
        process_hls_task,
        task_id,
        request
    )
    
    return TaskResponse(
        task_id=task_id,
        message="HLS conversion started",
        status_url=f"/api/tasks/{task_id}"
    )

async def process_hls_task(task_id: str, request: HLSConversionRequest):
    """執行 HLS 轉換任務"""
    temp_dir = tempfile.mkdtemp(prefix="hls_")
    
    try:
        task_manager.update_task(
            task_id,
            status="processing",
            progress=0.1,
            message="Downloading video..."
        )
        
        # 1. 下載原始影片
        local_input = os.path.join(temp_dir, "input.mp4")
        gcs_service.download_file(request.video_path, local_input)
        
        task_manager.update_task(task_id, progress=0.2, message="Converting to HLS...")
        
        # 2. 轉換為 HLS
        hls_output_dir = os.path.join(temp_dir, "hls")
        
        # 根據請求選擇變體
        variants = settings.HLS_VARIANTS
        if request.variants:
            variants = [v for v in variants if v['name'] in request.variants]
        
        master_playlist = hls_service.convert_to_hls(
            local_input,
            hls_output_dir,
            variants
        )
        
        task_manager.update_task(task_id, progress=0.7, message="Uploading HLS files...")
        
        # 3. 上傳所有 HLS 檔案到 GCS
        video_name = os.path.splitext(os.path.basename(request.video_path))[0]
        gcs_hls_dir = f"hls/{video_name}"
        
        # 上傳所有檔案
        for root, dirs, files in os.walk(hls_output_dir):
            for file in files:
                local_file = os.path.join(root, file)
                relative_path = os.path.relpath(local_file, hls_output_dir)
                gcs_path = f"{gcs_hls_dir}/{relative_path}"
                
                gcs_service.upload_file(local_file, gcs_path)
        
        # 4. 生成預覽縮圖
        task_manager.update_task(task_id, progress=0.9, message="Generating thumbnails...")
        
        thumbnails_dir = os.path.join(temp_dir, "thumbnails")
        thumbnails = hls_service.generate_preview_thumbnails(
            local_input,
            thumbnails_dir,
            interval=10
        )
        
        # 上傳縮圖
        for i, thumb in enumerate(thumbnails):
            gcs_thumb_path = f"{gcs_hls_dir}/thumbnails/thumb_{i:04d}.jpg"
            gcs_service.upload_file(thumb, gcs_thumb_path)
        
        # 完成
        master_url = gcs_service.get_public_url(f"{gcs_hls_dir}/master.m3u8")
        
        task_manager.update_task(
            task_id,
            status="completed",
            progress=1.0,
            message="HLS conversion completed",
            output_url=master_url,
            output_path=gcs_hls_dir
        )
        
        logger.info(f"HLS task {task_id} completed: {master_url}")
        
    except Exception as e:
        logger.error(f"HLS task {task_id} failed: {e}")
        task_manager.update_task(
            task_id,
            status="failed",
            error=str(e),
            message=f"HLS conversion failed: {str(e)}"
        )
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
