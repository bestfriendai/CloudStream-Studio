import ffmpeg
import os
import logging
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class FFmpegService:
    """FFmpeg 影片處理服務（支持毫秒級精度）"""
    
    @staticmethod
    def get_video_info(video_path: str) -> dict:
        """獲取影片資訊"""
        try:
            probe = ffmpeg.probe(video_path)
            video_info = next(s for s in probe['streams'] if s['codec_type'] == 'video')
            
            return {
                "duration": float(probe['format']['duration']),
                "width": int(video_info['width']),
                "height": int(video_info['height']),
                "codec": video_info['codec_name'],
                "fps": eval(video_info['r_frame_rate']),
                "bitrate": int(probe['format'].get('bit_rate', 0))
            }
        except Exception as e:
            logger.error(f"Failed to get video info: {e}")
            raise
    
    @staticmethod
    def format_time_precise(seconds: float) -> str:
        """
        將秒數轉換為 FFmpeg 時間格式（毫秒精度）
        
        Args:
            seconds: 秒數（支持小數）
            
        Returns:
            格式化的時間字符串 "HH:MM:SS.mmm"
        """
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        # 格式化為 HH:MM:SS.mmm（3位小數）
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    @staticmethod
    def clip_video(
        input_path: str,
        output_path: str,
        start_time: float,
        end_time: float,
        re_encode: bool = True,
        precise: bool = True
    ) -> None:
        """
        剪輯影片（毫秒級精度）
        
        Args:
            input_path: 輸入影片路徑
            output_path: 輸出影片路徑
            start_time: 開始時間（秒，3位小數=毫秒）
            end_time: 結束時間（秒，3位小數=毫秒）
            re_encode: 是否重新編碼
            precise: 是否使用精確模式
        """
        try:
            # ✅ 確保精度保留到 3 位小數
            start_time = round(float(start_time), 3)
            end_time = round(float(end_time), 3)
            duration = round(end_time - start_time, 3)
            
            logger.info(f"🎬 FFmpeg 毫秒級剪輯:")
            logger.info(f"   模式: {'精確模式（重新編碼）' if re_encode else '快速模式（stream copy）'}")
            logger.info(f"   開始時間: {start_time:.3f}s ({FFmpegService.format_time_precise(start_time)})")
            logger.info(f"   結束時間: {end_time:.3f}s ({FFmpegService.format_time_precise(end_time)})")
            logger.info(f"   持續時間: {duration:.3f}s")
            
            if re_encode:
                # ✅ 精確模式：重新編碼（毫秒級精度）
                if precise:
                    logger.info(f"   使用雙重 seek 精確模式")
                    
                    # 粗略 seek（快速跳到附近）
                    rough_seek = max(0, start_time - 2)
                    fine_seek = round(start_time - rough_seek, 3)
                    
                    logger.info(f"   粗略 seek: {rough_seek:.3f}s")
                    logger.info(f"   精確 seek: {fine_seek:.3f}s")
                    
                    (
                        ffmpeg
                        .input(input_path, ss=rough_seek)
                        .output(
                            output_path,
                            ss=fine_seek,
                            t=duration,
                            vcodec='libx264',
                            acodec='aac',
                            preset='medium',
                            crf=23,
                            movflags='faststart',
                            vsync='cfr',
                            video_track_timescale='90000',
                            avoid_negative_ts='make_zero',
                            fflags='+genpts'
                        )
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True)
                    )
                else:
                    # 簡單精確模式
                    (
                        ffmpeg
                        .input(input_path, ss=start_time)
                        .output(
                            output_path,
                            t=duration,
                            vcodec='libx264',
                            acodec='aac',
                            preset='medium',
                            crf=23,
                            movflags='faststart',
                            vsync='cfr'
                        )
                        .overwrite_output()
                        .run(capture_stdout=True, capture_stderr=True)
                    )
            else:
                # ⚠️ 快速模式
                logger.warning(f"   ⚠️  快速模式無法達到毫秒級精度")
                
                (
                    ffmpeg
                    .input(input_path, ss=start_time, t=duration)
                    .output(
                        output_path,
                        codec='copy',
                        avoid_negative_ts='make_zero'
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            
            logger.info(f"✅ FFmpeg 剪輯完成: {output_path}")
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"❌ FFmpeg 錯誤: {error_msg}")
            raise Exception(f"Failed to clip video: {error_msg}")
    
    @staticmethod
    def merge_videos(
        input_files: list[str],
        output_path: str,
        re_encode: bool = False
    ) -> None:
        """合併多個影片"""
        try:
            concat_file = output_path + '.concat.txt'
            with open(concat_file, 'w') as f:
                for file in input_files:
                    abs_path = os.path.abspath(file)
                    f.write(f"file '{abs_path}'\n")
            
            logger.info(f"🔗 FFmpeg 合併 {len(input_files)} 個文件")
            
            if re_encode:
                (
                    ffmpeg
                    .input(concat_file, format='concat', safe=0)
                    .output(
                        output_path,
                        vcodec='libx264',
                        acodec='aac',
                        preset='medium',
                        crf=23,
                        movflags='faststart',
                        vsync='cfr'
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            else:
                (
                    ffmpeg
                    .input(concat_file, format='concat', safe=0)
                    .output(output_path, c='copy')
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            
            os.remove(concat_file)
            logger.info(f"✅ FFmpeg 合併完成: {output_path}")
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"❌ FFmpeg 合併錯誤: {error_msg}")
            raise Exception(f"Failed to merge videos: {error_msg}")
    
    @staticmethod
    def generate_thumbnail(
        video_path: str,
        output_path: str,
        timestamp: float = 1.0,
        width: int = 320
    ) -> None:
        """生成縮圖（支持毫秒級時間戳）"""
        try:
            timestamp = round(float(timestamp), 3)
            logger.info(f"🖼️  生成縮圖於 {timestamp:.3f}s")
            
            (
                ffmpeg
                .input(video_path, ss=timestamp)
                .filter('scale', width, -1)
                .output(output_path, vframes=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            logger.info(f"✅ 生成縮圖: {output_path}")
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"❌ 生成縮圖失敗: {error_msg}")
            raise
    
    @staticmethod
    def extract_audio(
        video_path: str,
        output_path: str,
        codec: str = 'aac',
        bitrate: str = '192k'
    ) -> None:
        """提取音訊"""
        try:
            (
                ffmpeg
                .input(video_path)
                .output(
                    output_path,
                    acodec=codec,
                    audio_bitrate=bitrate,
                    vn=None
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            logger.info(f"✅ 提取音頻: {output_path}")
            
        except ffmpeg.Error as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            logger.error(f"❌ 提取音頻失敗: {error_msg}")
            raise
