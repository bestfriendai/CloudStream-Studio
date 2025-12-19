from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Optional, Literal, Union
from datetime import datetime

# ==================== 剪輯相關模型 ====================
class ClipRequest(BaseModel):
    """剪輯請求（支持毫秒級精度 - 3位小數）"""
    source_video: str = Field(..., description="源影片路徑")
    start_time: float = Field(..., ge=0, description="開始時間（秒，支持3位小數=毫秒）")
    end_time: float = Field(..., gt=0, description="結束時間（秒，支持3位小數=毫秒）")
    output_name: str = Field(..., description="輸出文件名")
    
    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_precision(cls, v):
        """
        驗證並保留時間精度
        - 支持最多 3 位小數（毫秒級）
        - 例如：1.234 秒 = 1秒234毫秒
        """
        if isinstance(v, (int, float)):
            # 保留 3 位小數
            return round(float(v), 3)
        return float(v)
    
    @model_validator(mode='after')
    def validate_time_range(self):
        """驗證時間範圍"""
        if self.end_time <= self.start_time:
            raise ValueError(
                f'end_time ({self.end_time}) must be greater than start_time ({self.start_time})'
            )
        
        # ✅ 確保最小時長為 1 毫秒
        min_duration = 0.001
        if (self.end_time - self.start_time) < min_duration:
            raise ValueError(
                f'Clip duration must be at least {min_duration}s (1ms). '
                f'Current: {self.end_time - self.start_time:.3f}s'
            )
        
        return self
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_video": "videos/sample.mp4",
                "start_time": 1.234,      # 1秒234毫秒
                "end_time": 5.678,        # 5秒678毫秒
                "output_name": "clip_001.mp4"
            }
        }


class ClipInfo(BaseModel):
    """片段信息（用於合併）"""
    source_video: str = Field(..., description="源影片路徑")
    start_time: float = Field(..., ge=0, description="開始時間（秒，支持3位小數）")
    end_time: float = Field(..., gt=0, description="結束時間（秒，支持3位小數）")
    
    @field_validator('start_time', 'end_time')
    @classmethod
    def validate_time_precision(cls, v):
        """保留 3 位小數精度"""
        if isinstance(v, (int, float)):
            return round(float(v), 3)
        return float(v)
    
    @model_validator(mode='after')
    def validate_time_range(self):
        """驗證時間範圍"""
        if self.end_time <= self.start_time:
            raise ValueError(
                f'end_time ({self.end_time}) must be greater than start_time ({self.start_time})'
            )
        
        # 確保最小時長為 1 毫秒
        min_duration = 0.001
        if (self.end_time - self.start_time) < min_duration:
            raise ValueError(
                f'Clip duration must be at least {min_duration}s (1ms)'
            )
        
        return self


class MergeRequest(BaseModel):
    """合併請求"""
    clips: List[ClipInfo] = Field(..., min_length=1, description="要合併的片段列表")
    output_name: str = Field(..., description="輸出檔名")
    
    class Config:
        json_schema_extra = {
            "example": {
                "clips": [
                    {
                        "source_video": "videos/video1.mp4",
                        "start_time": 0.500,    # 500毫秒
                        "end_time": 10.250      # 10秒250毫秒
                    },
                    {
                        "source_video": "videos/video2.mp4",
                        "start_time": 5.123,
                        "end_time": 15.789
                    }
                ],
                "output_name": "merged_video.mp4"
            }
        }


# ==================== HLS 相關模型 ====================
class HLSConversionRequest(BaseModel):
    video_path: str = Field(..., description="要轉換的影片路徑")
    variants: Optional[List[str]] = Field(
        default=["720p", "480p", "360p"],
        description="要生成的畫質變體"
    )


# ==================== 任務狀態模型 ====================
class TaskStatus(BaseModel):
    task_id: str
    status: Literal["pending", "processing", "completed", "failed", "cancelled"]
    progress: float = Field(ge=0, le=1, description="進度 0-1")
    message: Optional[str] = None
    output_url: Optional[str] = None
    output_path: Optional[str] = None
    error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: Optional[dict] = Field(default=None, description="額外的元數據")  # ✅ 添加 metadata
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "processing",
                "progress": 0.65,
                "message": "Processing video...",
                "created_at": "2024-01-01T12:00:00",
                "updated_at": "2024-01-01T12:05:30",
                "metadata": {
                    "start_time": 1.234,
                    "end_time": 5.678,
                    "expected_duration": 4.444
                }
            }
        }


class TaskResponse(BaseModel):
    task_id: str
    message: str
    status_url: str
