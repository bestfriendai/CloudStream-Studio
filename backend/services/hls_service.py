import ffmpeg
import os
import logging
from typing import List, Dict
from pathlib import Path
from config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class HLSService:
    """HLS 串流轉換服務"""
    
    @staticmethod
    def convert_to_hls(
        input_path: str,
        output_dir: str,
        variants: List[Dict[str, any]] = None
    ) -> str:
        """
        將影片轉換為 HLS 格式
        
        Args:
            input_path: 輸入影片路徑
            output_dir: 輸出目錄
            variants: 畫質變體配置
            
        Returns:
            master.m3u8 的路徑
        """
        try:
            # 創建輸出目錄
            os.makedirs(output_dir, exist_ok=True)
            
            # 使用預設變體或自訂變體
            if variants is None:
                variants = settings.HLS_VARIANTS
            
            # 為每個變體生成 HLS
            for variant in variants:
                variant_name = variant['name']
                height = variant['height']
                bitrate = variant['bitrate']
                
                playlist_path = os.path.join(output_dir, f"{variant_name}.m3u8")
                segment_pattern = os.path.join(output_dir, f"{variant_name}_%03d.ts")
                
                logger.info(f"Converting to HLS: {variant_name}")
                
                (
                    ffmpeg
                    .input(input_path)
                    .output(
                        playlist_path,
                        format='hls',
                        start_number=0,
                        hls_time=settings.HLS_SEGMENT_DURATION,
                        hls_list_size=0,
                        hls_segment_filename=segment_pattern,
                        vf=f"scale=-2:{height}",
                        video_bitrate=bitrate,
                        maxrate=bitrate,
                        bufsize=f"{int(bitrate[:-1]) * 2}k",
                        vcodec='libx264',
                        acodec='aac',
                        audio_bitrate='128k',
                        preset='medium',
                        g=48,  # GOP size
                        keyint_min=48,
                        sc_threshold=0
                    )
                    .overwrite_output()
                    .run(capture_stdout=True, capture_stderr=True)
                )
            
            # 生成 master playlist
            master_path = HLSService._create_master_playlist(output_dir, variants)
            
            logger.info(f"HLS conversion completed: {master_path}")
            return master_path
            
        except ffmpeg.Error as e:
            logger.error(f"HLS conversion error: {e.stderr.decode()}")
            raise Exception(f"Failed to convert to HLS: {e.stderr.decode()}")
    
    @staticmethod
    def _create_master_playlist(output_dir: str, variants: List[Dict]) -> str:
        """
        創建 master playlist
        """
        master_path = os.path.join(output_dir, "master.m3u8")
        
        with open(master_path, 'w') as f:
            f.write("#EXTM3U\n")
            f.write("#EXT-X-VERSION:3\n\n")
            
            for variant in variants:
                name = variant['name']
                bitrate_num = int(variant['bitrate'].replace('k', '')) * 1000
                height = variant['height']
                
                f.write(f"#EXT-X-STREAM-INF:BANDWIDTH={bitrate_num},RESOLUTION=x{height}\n")
                f.write(f"{name}.m3u8\n\n")
        
        return master_path
    
    @staticmethod
    def generate_preview_thumbnails(
        video_path: str,
        output_dir: str,
        interval: int = 10,
        width: int = 160
    ) -> List[str]:
        """
        生成預覽縮圖序列（用於 timeline scrubbing）
        
        Args:
            video_path: 影片路徑
            output_dir: 輸出目錄
            interval: 間隔秒數
            width: 縮圖寬度
            
        Returns:
            縮圖檔案路徑列表
        """
        try:
            os.makedirs(output_dir, exist_ok=True)
            
            # 獲取影片時長
            probe = ffmpeg.probe(video_path)
            duration = float(probe['format']['duration'])
            
            thumbnails = []
            output_pattern = os.path.join(output_dir, "thumb_%04d.jpg")
            
            # 使用 FFmpeg 批次生成縮圖
            (
                ffmpeg
                .input(video_path)
                .filter('fps', f'1/{interval}')
                .filter('scale', width, -1)
                .output(output_pattern, start_number=0)
                .overwrite_output()
                .run(capture_stdout=True, capture_stderr=True)
            )
            
            # 收集生成的縮圖
            for i in range(int(duration / interval) + 1):
                thumb_path = os.path.join(output_dir, f"thumb_{i:04d}.jpg")
                if os.path.exists(thumb_path):
                    thumbnails.append(thumb_path)
            
            logger.info(f"Generated {len(thumbnails)} preview thumbnails")
            return thumbnails
            
        except Exception as e:
            logger.error(f"Failed to generate thumbnails: {e}")
            raise
