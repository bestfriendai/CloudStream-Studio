from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime

# ==================== 剪輯相關模型 ====================
class ClipRequest(BaseModel):
    source_video: str = Field(..., description="GCS 中的影片路徑")
    start_time: float = Field(..., ge=0, description="開始時間（秒）")
    end_time: float = Field(..., gt=0, description="結束時間（秒）")
    output_name: str = Field(..., description="輸出檔名")
    
    class Config:
        json_schema_extra = {
            "example": {
                "source_video": "videos/sample.mp4",
                "start_time": 10.5,
                "end_time": 30.2,
                "output_name": "clip_001.mp4"
            }
        }

class MergeRequest(BaseModel):
    clips: List[ClipRequest] = Field(..., min_length=1, description="要合併的片段列表")
    output_name: str = Field(..., description="輸出檔名")
    
    class Config:
        json_schema_extra = {
            "example": {
                "clips": [
                    {
                        "source_video": "videos/video1.mp4",
                        "start_time": 0,
                        "end_time": 10,
                        "output_name": "clip1.mp4"
                    },
                    {
                        "source_video": "videos/video2.mp4",
                        "start_time": 5,
                        "end_time": 15,
                        "output_name": "clip2.mp4"
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
    
    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "status": "processing",
                "progress": 0.65,
                "message": "Processing video...",
                "created_at": "2024-01-01T12:00:00",
                "updated_at": "2024-01-01T12:05:30"
            }
        }

class TaskResponse(BaseModel):
    task_id: str
    message: str
    status_url: str
