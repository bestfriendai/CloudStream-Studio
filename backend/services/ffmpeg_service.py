import ffmpeg
import os
import logging
from typing import Optional, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)

class FFmpegService:
    """FFmpeg 影片處理服務"""
    
    @staticmethod
    def get_video_info(video_path: str) -> dict:
        """
        獲取影片資訊
        """
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
    def clip_video(
        input_path: str,
        output_path: str,
        start_time: float,
        end_time: float,
        re_encode: bool = False
    ) -> None:
        """
        剪輯影片
        
        Args:
            input_path: 輸入影片路徑
            output_path: 輸出影片路徑
            start_time: 開始時間（秒）
            end_time: 結束時間（秒）
            re_encode: 是否重新編碼（False 使用 copy 更快）
        """
        try:
            duration = end_time - start_time
            
            if re_encode:
                # 重新編碼（較慢但更精確）
                (
                    ffmpeg
                    .input(input_path, ss=start_time, t=duration)
                    .output(
                        output_path,
                        vcodec='libx264',
                        acodec='aac',
                        preset='medium',
                        crf=23
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            else:
                # 快速複製（不重新編碼）
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
            
            logger.info(f"Clipped video: {output_path}")
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error: {e.stderr.decode()}")
            raise Exception(f"Failed to clip video: {e.stderr.decode()}")
    
    @staticmethod
    def merge_videos(
        input_files: list[str],
        output_path: str,
        re_encode: bool = False
    ) -> None:
        """
        合併多個影片
        
        Args:
            input_files: 輸入影片列表
            output_path: 輸出影片路徑
            re_encode: 是否重新編碼
        """
        try:
            # 創建 concat 檔案
            concat_file = output_path + '.concat.txt'
            with open(concat_file, 'w') as f:
                for file in input_files:
                    # 使用絕對路徑
                    abs_path = os.path.abspath(file)
                    f.write(f"file '{abs_path}'\n")
            
            if re_encode:
                # 重新編碼合併
                (
                    ffmpeg
                    .input(concat_file, format='concat', safe=0)
                    .output(
                        output_path,
                        vcodec='libx264',
                        acodec='aac',
                        preset='medium',
                        crf=23
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            else:
                # 快速合併
                (
                    ffmpeg
                    .input(concat_file, format='concat', safe=0)
                    .output(output_path, c='copy')
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            
            # 清理 concat 檔案
            os.remove(concat_file)
            logger.info(f"Merged video: {output_path}")
            
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg merge error: {e.stderr.decode()}")
            raise Exception(f"Failed to merge videos: {e.stderr.decode()}")
    
    @staticmethod
    def generate_thumbnail(
        video_path: str,
        output_path: str,
        timestamp: float = 1.0,
        width: int = 320
    ) -> None:
        """
        生成縮圖
        
        Args:
            video_path: 影片路徑
            output_path: 輸出圖片路徑
            timestamp: 截圖時間點（秒）
            width: 縮圖寬度
        """
        try:
            (
                ffmpeg
                .input(video_path, ss=timestamp)
                .filter('scale', width, -1)
                .output(output_path, vframes=1)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            logger.info(f"Generated thumbnail: {output_path}")
            
        except ffmpeg.Error as e:
            logger.error(f"Failed to generate thumbnail: {e.stderr.decode()}")
            raise
    
    @staticmethod
    def extract_audio(
        video_path: str,
        output_path: str,
        codec: str = 'aac',
        bitrate: str = '192k'
    ) -> None:
        """
        提取音訊
        """
        try:
            (
                ffmpeg
                .input(video_path)
                .output(
                    output_path,
                    acodec=codec,
                    audio_bitrate=bitrate,
                    vn=None  # 不包含視訊
                )
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            logger.info(f"Extracted audio: {output_path}")
            
        except ffmpeg.Error as e:
            logger.error(f"Failed to extract audio: {e.stderr.decode()}")
            raise
