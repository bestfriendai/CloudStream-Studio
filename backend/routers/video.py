from fastapi import APIRouter, BackgroundTasks, HTTPException
from models import MergeRequest, TaskResponse, HLSConversionRequest
from services.gcs_service import GCSService
from services.ffmpeg_service import FFmpegService
from services.hls_service import HLSService
from utils.task_manager import task_manager
from config import get_settings
import tempfile
import os
import shutil
import logging
import subprocess

router = APIRouter(prefix="/api/videos", tags=["Video Processing"])
logger = logging.getLogger(__name__)
settings = get_settings()

gcs_service = GCSService()
ffmpeg_service = FFmpegService()
hls_service = HLSService()


# ==================== 合併多個片段 ====================
@router.post("/merge", response_model=TaskResponse)
async def merge_videos(request: MergeRequest, background_tasks: BackgroundTasks):
    """
    合併多個影片片段（毫秒級精度）
    
    - 自動處理不同格式和編碼的影片
    - 支持毫秒級時間精度
    """
    if len(request.clips) < 1:
        raise HTTPException(status_code=400, detail="At least one clip is required")
    
    task_id = task_manager.create_task(
        f"Merge task created ({len(request.clips)} clips)"
    )
    
    background_tasks.add_task(
        process_merge_task,
        task_id,
        request
    )
    
    return TaskResponse(
        task_id=task_id,
        message=f"Merge task started with {len(request.clips)} clips",
        status_url=f"/api/tasks/{task_id}"
    )


async def process_merge_task(task_id: str, request: MergeRequest):
    """執行合併任務（毫秒級精度）"""
    temp_dir = tempfile.mkdtemp(prefix="merge_")
    clip_files = []
    clip_durations = []
    
    try:
        task_manager.update_task(
            task_id,
            status="processing",
            progress=0.1,
            message="Processing clips with millisecond precision..."
        )
        
        total_clips = len(request.clips)
        logger.info(f"🔗 [Task {task_id}] 開始合併 {total_clips} 個片段（毫秒級精度）")
        
        # ✅ 計算預期總時長
        expected_total_duration = 0.0
        for clip in request.clips:
            clip_duration = round(clip.end_time - clip.start_time, 3)
            expected_total_duration += clip_duration
            logger.info(f"   片段: {clip.source_video}")
            logger.info(f"      範圍: {clip.start_time:.3f}s - {clip.end_time:.3f}s")
            logger.info(f"      時長: {clip_duration:.3f}s ({int(clip_duration * 1000)}ms)")
        
        expected_total_duration = round(expected_total_duration, 3)
        logger.info(f"   預期總時長: {expected_total_duration:.3f}s ({int(expected_total_duration * 1000)}ms)")
        
        # ==================== 1. 處理每個片段 ====================
        for i, clip in enumerate(request.clips):
            logger.info(f"   處理片段 {i+1}/{total_clips}: {clip.source_video}")
            
            # 下載原始影片
            local_input = os.path.join(temp_dir, f"input_{i}.mp4")
            gcs_service.download_file(clip.source_video, local_input)
            
            # 獲取影片信息
            video_info = ffmpeg_service.get_video_info(local_input)
            logger.info(f"      原始時長: {video_info['duration']:.3f}s, 分辨率: {video_info['width']}x{video_info['height']}")
            
            # ✅ 剪輯片段（毫秒級精度）
            clip_output = os.path.join(temp_dir, f"clip_{i:03d}.mp4")
            logger.info(f"      剪輯: {clip.start_time:.3f}s - {clip.end_time:.3f}s")
            
            ffmpeg_service.clip_video(
                local_input,
                clip_output,
                clip.start_time,
                clip.end_time,
                re_encode=True,  # ✅ 合併時需要重新編碼以確保兼容性
                precise=True     # ✅ 毫秒級精度
            )
            
            # 驗證剪輯結果
            clip_info = ffmpeg_service.get_video_info(clip_output)
            actual_clip_duration = round(clip_info['duration'], 3)
            expected_clip_duration = round(clip.end_time - clip.start_time, 3)
            
            logger.info(f"      剪輯後時長: {actual_clip_duration:.3f}s")
            logger.info(f"      預期時長: {expected_clip_duration:.3f}s")
            
            clip_error = abs(actual_clip_duration - expected_clip_duration)
            clip_error_ms = int(clip_error * 1000)
            logger.info(f"      誤差: {clip_error:.3f}s ({clip_error_ms}ms)")
            
            clip_files.append(clip_output)
            clip_durations.append(actual_clip_duration)
            
            # 更新進度
            progress = 0.1 + (0.6 * (i + 1) / total_clips)
            task_manager.update_task(
                task_id,
                progress=progress,
                message=f"Processed clip {i+1}/{total_clips} ({actual_clip_duration:.3f}s)"
            )
            
            # 清理輸入文件
            os.remove(local_input)
        
        # ==================== 2. 合併影片 ====================
        task_manager.update_task(task_id, progress=0.7, message="Merging clips...")
        
        logger.info(f"🔗 [Task {task_id}] 合併所有片段...")
        merged_output = os.path.join(temp_dir, "merged.mp4")
        
        # ✅ 使用重新編碼模式以確保精度
        ffmpeg_service.merge_videos(
            clip_files, 
            merged_output, 
            re_encode=True  # 重新編碼以確保兼容性和精度
        )
        
        # ✅ 驗證合併結果（毫秒級精度）
        merged_info = ffmpeg_service.get_video_info(merged_output)
        actual_total_duration = round(merged_info['duration'], 3)
        
        logger.info(f"   ✅ 合併完成")
        logger.info(f"   實際總時長: {actual_total_duration:.3f}s ({int(actual_total_duration * 1000)}ms)")
        logger.info(f"   預期總時長: {expected_total_duration:.3f}s ({int(expected_total_duration * 1000)}ms)")
        
        # ✅ 計算總誤差
        total_error = abs(actual_total_duration - expected_total_duration)
        total_error_ms = int(total_error * 1000)
        total_error_percent = (total_error / expected_total_duration) * 100 if expected_total_duration > 0 else 0
        
        logger.info(f"   誤差: {total_error:.3f}s ({total_error_ms}ms, {total_error_percent:.2f}%)")
        
        # ✅ 精度評估
        if total_error < 0.050:
            logger.info(f"   ✅ 合併精度：優秀 (< 50ms)")
            merge_precision = "excellent"
        elif total_error < 0.100:
            logger.info(f"   ✓ 合併精度：良好 (< 100ms)")
            merge_precision = "good"
        elif total_error < 0.200:
            logger.info(f"   ○ 合併精度：可接受 (< 200ms)")
            merge_precision = "acceptable"
        else:
            logger.warning(f"   ⚠️  合併精度：一般 (> 200ms)")
            merge_precision = "fair"
        
        # ==================== 3. 上傳到 GCS ====================
        task_manager.update_task(task_id, progress=0.9, message="Uploading result...")
        
        output_path = f"merged/{request.output_name}"
        logger.info(f"📤 [Task {task_id}] 上傳到 GCS: {output_path}")
        gcs_service.upload_file(merged_output, output_path)
        
        # ==================== 4. 生成縮圖 ====================
        thumbnail_local = os.path.join(temp_dir, "thumbnail.jpg")
        thumbnail_time = round(actual_total_duration / 2, 3)
        ffmpeg_service.generate_thumbnail(
            merged_output, 
            thumbnail_local,
            timestamp=thumbnail_time
        )
        
        thumbnail_path = f"thumbnails/{request.output_name}.jpg"
        gcs_service.upload_file(thumbnail_local, thumbnail_path)
        
        # ==================== 5. 完成 ====================
        output_url = gcs_service.get_public_url(output_path)
        thumbnail_url = gcs_service.get_public_url(thumbnail_path)
        
        # ✅ 返回毫秒級精度的 metadata
        task_manager.update_task(
            task_id,
            status="completed",
            progress=1.0,
            message="Merge completed successfully with millisecond precision",
            output_url=output_url,
            output_path=output_path,
            metadata={
                "total_clips": total_clips,
                "merged_duration": actual_total_duration,
                "expected_duration": expected_total_duration,
                "duration_error_ms": total_error_ms,
                "duration_error_percent": round(total_error_percent, 2),
                "precision_level": merge_precision,
                "clip_durations": clip_durations,
                "file_size": os.path.getsize(merged_output),
                "thumbnail_url": thumbnail_url,
                "video_info": {
                    "width": merged_info['width'],
                    "height": merged_info['height'],
                    "codec": merged_info['codec'],
                    "fps": merged_info['fps']
                }
            }
        )
        
        logger.info(f"✅ [Task {task_id}] 合併任務完成（毫秒級精度）")
        logger.info(f"   輸出 URL: {output_url}")
        logger.info(f"   精度等級: {merge_precision}")
        
    except Exception as e:
        logger.error(f"❌ [Task {task_id}] 合併任務失敗: {e}", exc_info=True)
        task_manager.update_task(
            task_id,
            status="failed",
            error=str(e),
            message=f"Merge failed: {str(e)}"
        )
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

@router.post("/optimize/{video_path:path}")
async def optimize_video(video_path: str, background_tasks: BackgroundTasks):
    """
    最佳化影片（Fast Start）
    
    將 moov atom 移到檔案開頭，加速串流載入
    
    Args:
        video_path: GCS 中的影片路徑
    
    Returns:
        TaskResponse: 任務資訊
    
    Example:
        ```bash
        curl -X POST http://localhost:8000/api/videos/optimize/uuid/video.mp4/timestamp/sample.mp4
        ```
    """
    try:
        if not gcs_service.file_exists(video_path):
            raise HTTPException(status_code=404, detail="影片不存在")
        
        logger.info(f"🔧 最佳化影片: {video_path}")
        
        # 創建任務
        task_id = task_manager.create_task(f"最佳化: {os.path.basename(video_path)}")
        
        # 在背景執行
        background_tasks.add_task(
            process_optimize_task,
            task_id,
            video_path
        )
        
        return TaskResponse(
            task_id=task_id,
            message="最佳化任務已啟動",
            status_url=f"/api/tasks/{task_id}"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ 創建最佳化任務失敗: {e}")
        raise HTTPException(status_code=500, detail=f"創建任務失敗: {str(e)}")


async def process_optimize_task(task_id: str, video_path: str):
    """執行最佳化任務"""
    temp_dir = None
    try:
        task_manager.update_task(
            task_id,
            status="processing",
            progress=0.1,
            message="下載影片..."
        )
        
        logger.info(f"🔧 [Task {task_id}] 開始最佳化: {video_path}")
        
        temp_dir = tempfile.mkdtemp(prefix="optimize_")
        local_input = os.path.join(temp_dir, "input.mp4")
        local_output = os.path.join(temp_dir, "output.mp4")
        
        # 下載影片
        gcs_service.download_file(video_path, local_input)
        
        task_manager.update_task(
            task_id,
            progress=0.3,
            message="執行 Fast Start 最佳化..."
        )
        
        # 使用 ffmpeg 進行 Fast Start 最佳化
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', local_input,
            '-c', 'copy',  # 不重新編碼
            '-movflags', '+faststart',  # Fast Start
            '-y',
            local_output
        ]
        
        logger.info(f"   執行: {' '.join(ffmpeg_cmd)}")
        
        process = subprocess.run(
            ffmpeg_cmd,
            capture_output=True,
            text=True,
            timeout=300
        )
        
        if process.returncode != 0:
            raise Exception(f"FFmpeg 失敗: {process.stderr}")
        
        task_manager.update_task(
            task_id,
            progress=0.7,
            message="上傳最佳化版本..."
        )
        
        # ✅ 上傳回 GCS（覆蓋原檔案）
        gcs_service.upload_file(local_output, video_path)
        
        # ✅ 清除 GCS metadata 快取
        from services.gcs_cache import get_connection_pool
        gcs_pool = get_connection_pool()
        gcs_pool.invalidate_metadata_cache(settings.GCS_BUCKET_NAME, video_path)
        logger.info(f"   ✅ 已清除 metadata 快取: {video_path}")
        
        # ✅ 清除影片快取
        from services.video_cache import get_video_cache
        video_cache = get_video_cache()
        video_cache.invalidate(video_path)
        logger.info(f"   ✅ 已清除影片快取: {video_path}")
        
        # 獲取檔案資訊
        optimized_info = ffmpeg_service.get_video_info(local_output)
        
        task_manager.update_task(
            task_id,
            status="completed",
            progress=1.0,
            message="最佳化完成",
            output_path=video_path,
            metadata={
                "optimized": True,
                "file_size": os.path.getsize(local_output),
                "duration": optimized_info['duration'],
                "video_info": {
                    "width": optimized_info['width'],
                    "height": optimized_info['height'],
                    "codec": optimized_info['codec'],
                    "fps": optimized_info['fps']
                }
            }
        )
        
        logger.info(f"✅ [Task {task_id}] 最佳化完成")
        
    except Exception as e:
        logger.error(f"❌ [Task {task_id}] 最佳化失敗: {e}", exc_info=True)
        task_manager.update_task(
            task_id,
            status="failed",
            error=str(e),
            message=f"最佳化失敗: {str(e)}"
        )
    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)