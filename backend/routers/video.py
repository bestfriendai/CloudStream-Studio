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

router = APIRouter(prefix="/api/videos", tags=["Video Processing"])
logger = logging.getLogger(__name__)
settings = get_settings()

gcs_service = GCSService()
ffmpeg_service = FFmpegService()
hls_service = HLSService()

# ==================== 剪輯單一影片 ====================
@router.post("/clip", response_model=TaskResponse)
async def clip_video(request: ClipRequest, background_tasks: BackgroundTasks):
    """
    剪輯單一影片片段（毫秒級精度）
    
    - **精確模式**: 重新編碼，支持毫秒級精度
    - 時間格式: 支持 3 位小數（例如：1.234 秒 = 1秒234毫秒）
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
    """執行剪輯任務（毫秒級精度）"""
    temp_dir = tempfile.mkdtemp(prefix="clip_")
    
    try:
        # ==================== 1. 下載原始影片 ====================
        task_manager.update_task(
            task_id,
            status="processing",
            progress=0.1,
            message="Downloading source video..."
        )
        
        local_input = os.path.join(temp_dir, "input.mp4")
        logger.info(f"🎬 [Task {task_id}] 開始剪輯（毫秒級精度）...")
        logger.info(f"   開始時間: {request.start_time:.3f}s")
        logger.info(f"   結束時間: {request.end_time:.3f}s")
        logger.info(f"   預期時長: {(request.end_time - request.start_time):.3f}s")
        
        gcs_service.download_file(request.source_video, local_input)
        
        # 驗證下載
        if not os.path.exists(local_input):
            raise Exception("下載失敗：文件不存在")
        
        input_size = os.path.getsize(local_input)
        logger.info(f"   ✅ 下載完成，文件大小: {input_size / 1024 / 1024:.2f} MB")
        
        # ==================== 2. 獲取影片信息 ====================
        task_manager.update_task(task_id, progress=0.2, message="Analyzing video...")
        
        logger.info(f"📊 [Task {task_id}] 分析影片信息...")
        video_info = ffmpeg_service.get_video_info(local_input)
        
        original_duration = round(video_info['duration'], 3)  # ✅ 保留 3 位小數
        logger.info(f"   原始影片時長: {original_duration:.3f}s")
        logger.info(f"   分辨率: {video_info['width']}x{video_info['height']}")
        logger.info(f"   編碼: {video_info['codec']}")
        logger.info(f"   FPS: {video_info['fps']:.2f}")
        
        # ✅ 驗證時間範圍（保留毫秒精度）
        if request.start_time < 0:
            logger.warning(f"   ⚠️  開始時間 < 0，調整為 0")
            request.start_time = 0.0
        
        if request.end_time > original_duration:
            logger.warning(f"   ⚠️  結束時間 ({request.end_time:.3f}s) 超過影片時長 ({original_duration:.3f}s)，調整為影片時長")
            request.end_time = original_duration
        
        if request.start_time >= request.end_time:
            raise Exception(f"無效的時間範圍: {request.start_time:.3f}s - {request.end_time:.3f}s")
        
        # ✅ 計算預期時長（毫秒精度）
        expected_duration = round(request.end_time - request.start_time, 3)
        logger.info(f"   ✂️  剪輯範圍: {request.start_time:.3f}s - {request.end_time:.3f}s")
        logger.info(f"   ⏱️  預期時長: {expected_duration:.3f}s ({int(expected_duration * 1000)}ms)")
        
        # ==================== 3. 剪輯影片（毫秒級精度）====================
        task_manager.update_task(task_id, progress=0.3, message="Clipping video with millisecond precision...")
        
        local_output = os.path.join(temp_dir, "output.mp4")
        
        logger.info(f"🎬 [Task {task_id}] 開始剪輯（精確模式）...")
        
        # ✅ 使用精確模式（重新編碼）以達到毫秒級精度
        ffmpeg_service.clip_video(
            local_input,
            local_output,
            request.start_time,
            request.end_time,
            re_encode=True,    # ✅ 精確模式
            precise=True       # ✅ 雙重 seek
        )
        
        # 驗證輸出文件
        if not os.path.exists(local_output):
            raise Exception("剪輯失敗：輸出文件不存在")
        
        output_size = os.path.getsize(local_output)
        if output_size == 0:
            raise Exception("剪輯失敗：輸出文件為空")
        
        logger.info(f"   ✅ 剪輯完成，輸出文件大小: {output_size / 1024 / 1024:.2f} MB")
        
        # ==================== 4. 驗證輸出影片（毫秒級精度）====================
        task_manager.update_task(task_id, progress=0.5, message="Verifying output with millisecond accuracy...")
        
        logger.info(f"🔍 [Task {task_id}] 驗證輸出影片（毫秒級精度）...")
        output_info = ffmpeg_service.get_video_info(local_output)
        actual_duration = round(output_info['duration'], 3)  # ✅ 保留 3 位小數
        
        logger.info(f"   實際時長: {actual_duration:.3f}s ({int(actual_duration * 1000)}ms)")
        logger.info(f"   預期時長: {expected_duration:.3f}s ({int(expected_duration * 1000)}ms)")
        
        # ✅ 計算毫秒級誤差
        duration_diff = abs(actual_duration - expected_duration)
        duration_diff_ms = int(duration_diff * 1000)
        duration_error_percent = (duration_diff / expected_duration) * 100 if expected_duration > 0 else 0
        
        logger.info(f"   誤差: {duration_diff:.3f}s ({duration_diff_ms}ms, {duration_error_percent:.2f}%)")
        
        # ✅ 精度評估
        if duration_diff < 0.010:  # < 10ms
            logger.info(f"   ✅ 精度：優秀 (< 10ms)")
            precision_level = "excellent"
        elif duration_diff < 0.050:  # < 50ms
            logger.info(f"   ✓ 精度：良好 (< 50ms)")
            precision_level = "good"
        elif duration_diff < 0.100:  # < 100ms
            logger.info(f"   ○ 精度：可接受 (< 100ms)")
            precision_level = "acceptable"
        else:
            logger.warning(f"   ⚠️  精度：一般 (> 100ms)")
            precision_level = "fair"
        
        # ==================== 5. 上傳到 GCS ====================
        task_manager.update_task(task_id, progress=0.7, message="Uploading to GCS...")
        
        output_path = f"clips/{request.output_name}"
        logger.info(f"📤 [Task {task_id}] 上傳到 GCS: {output_path}")
        
        gcs_service.upload_file(local_output, output_path)
        logger.info(f"   ✅ 上傳完成")
        
        # ==================== 6. 生成縮圖 ====================
        task_manager.update_task(task_id, progress=0.9, message="Generating thumbnail...")
        
        logger.info(f"🖼️  [Task {task_id}] 生成縮圖...")
        thumbnail_local = os.path.join(temp_dir, "thumbnail.jpg")
        
        # 在影片中間位置截圖（毫秒精度）
        thumbnail_time = round(expected_duration / 2, 3)
        ffmpeg_service.generate_thumbnail(
            local_output,
            thumbnail_local,
            timestamp=thumbnail_time
        )
        
        thumbnail_path = f"thumbnails/{request.output_name}.jpg"
        gcs_service.upload_file(thumbnail_local, thumbnail_path)
        logger.info(f"   ✅ 縮圖已上傳")
        
        # ==================== 7. 完成 ====================
        output_url = gcs_service.get_public_url(output_path)
        thumbnail_url = gcs_service.get_public_url(thumbnail_path)
        
        # ✅ 返回毫秒級精度的 metadata
        task_manager.update_task(
            task_id,
            status="completed",
            progress=1.0,
            message="Clip completed successfully with millisecond precision",
            output_url=output_url,
            output_path=output_path,
            metadata={
                "original_duration": original_duration,
                "clip_duration": actual_duration,
                "expected_duration": expected_duration,
                "start_time": request.start_time,
                "end_time": request.end_time,
                "duration_error_ms": duration_diff_ms,
                "duration_error_percent": round(duration_error_percent, 2),
                "precision_level": precision_level,
                "file_size": output_size,
                "thumbnail_url": thumbnail_url,
                "video_info": {
                    "width": output_info['width'],
                    "height": output_info['height'],
                    "codec": output_info['codec'],
                    "fps": output_info['fps']
                }
            }
        )
        
        logger.info(f"✅ [Task {task_id}] 剪輯任務完成（毫秒級精度）")
        logger.info(f"   輸出 URL: {output_url}")
        logger.info(f"   縮圖 URL: {thumbnail_url}")
        logger.info(f"   精度等級: {precision_level}")
        
    except Exception as e:
        logger.error(f"❌ [Task {task_id}] 剪輯任務失敗: {e}", exc_info=True)
        task_manager.update_task(
            task_id,
            status="failed",
            error=str(e),
            message=f"Clip failed: {str(e)}"
        )
    
    finally:
        # 清理臨時檔案
        logger.info(f"🧹 [Task {task_id}] 清理臨時文件: {temp_dir}")
        shutil.rmtree(temp_dir, ignore_errors=True)


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


# ==================== HLS 轉換 ====================
@router.post("/hls", response_model=TaskResponse)
async def convert_to_hls(request: HLSConversionRequest, background_tasks: BackgroundTasks):
    """
    將影片轉換為 HLS 格式
    
    - 支持多畫質轉換
    - 自動生成 master playlist
    - 生成預覽縮圖
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
        
        logger.info(f"📺 [Task {task_id}] 開始 HLS 轉換: {request.video_path}")
        
        # 1. 下載原始影片
        local_input = os.path.join(temp_dir, "input.mp4")
        gcs_service.download_file(request.video_path, local_input)
        
        # 獲取影片信息
        video_info = ffmpeg_service.get_video_info(local_input)
        logger.info(f"   影片信息: {video_info['duration']:.2f}s, {video_info['width']}x{video_info['height']}")
        
        task_manager.update_task(task_id, progress=0.2, message="Converting to HLS...")
        
        # 2. 轉換為 HLS
        hls_output_dir = os.path.join(temp_dir, "hls")
        
        # 根據請求選擇變體
        variants = settings.HLS_VARIANTS
        if request.variants:
            variants = [v for v in variants if v['name'] in request.variants]
        
        logger.info(f"   轉換畫質: {[v['name'] for v in variants]}")
        
        master_playlist = hls_service.convert_to_hls(
            local_input,
            hls_output_dir,
            variants
        )
        
        task_manager.update_task(task_id, progress=0.7, message="Uploading HLS files...")
        
        # 3. 上傳所有 HLS 檔案到 GCS
        video_name = os.path.splitext(os.path.basename(request.video_path))[0]
        gcs_hls_dir = f"hls/{video_name}"
        
        logger.info(f"📤 [Task {task_id}] 上傳 HLS 文件到: {gcs_hls_dir}")
        
        # 上傳所有檔案
        file_count = 0
        for root, dirs, files in os.walk(hls_output_dir):
            for file in files:
                local_file = os.path.join(root, file)
                relative_path = os.path.relpath(local_file, hls_output_dir)
                gcs_path = f"{gcs_hls_dir}/{relative_path}"
                
                gcs_service.upload_file(local_file, gcs_path)
                file_count += 1
        
        logger.info(f"   ✅ 已上傳 {file_count} 個文件")
        
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
        
        logger.info(f"   ✅ 已生成 {len(thumbnails)} 個縮圖")
        
        # 完成
        master_url = gcs_service.get_public_url(f"{gcs_hls_dir}/master.m3u8")
        
        task_manager.update_task(
            task_id,
            status="completed",
            progress=1.0,
            message="HLS conversion completed",
            output_url=master_url,
            output_path=gcs_hls_dir,
            metadata={
                "variants": [v['name'] for v in variants],
                "file_count": file_count,
                "thumbnail_count": len(thumbnails),
                "video_info": video_info
            }
        )
        
        logger.info(f"✅ [Task {task_id}] HLS 轉換完成: {master_url}")
        
    except Exception as e:
        logger.error(f"❌ [Task {task_id}] HLS 轉換失敗: {e}", exc_info=True)
        task_manager.update_task(
            task_id,
            status="failed",
            error=str(e),
            message=f"HLS conversion failed: {str(e)}"
        )
    
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
