# backend/utils/task_manager.py

from datetime import datetime
from typing import Optional, Dict, Any
import uuid
import logging

logger = logging.getLogger(__name__)


class TaskManager:
    """任務管理器"""
    
    def __init__(self):
        self.tasks: Dict[str, Dict[str, Any]] = {}
    
    def create_task(self, message: str = "Task created") -> str:
        """創建新任務"""
        task_id = str(uuid.uuid4())
        
        self.tasks[task_id] = {
            "task_id": task_id,
            "status": "pending",
            "progress": 0.0,
            "message": message,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "output_url": None,
            "output_path": None,
            "error": None,
            "metadata": {}  # ✅ 添加 metadata 字段
        }
        
        logger.info(f"Created task: {task_id}")
        return task_id
    
    def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        output_url: Optional[str] = None,
        output_path: Optional[str] = None,
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None  # ✅ 添加 metadata 參數
    ):
        """更新任務狀態"""
        if task_id not in self.tasks:
            logger.warning(f"Task {task_id} not found")
            return
        
        task = self.tasks[task_id]
        
        if status is not None:
            task["status"] = status
        
        if progress is not None:
            task["progress"] = progress
        
        if message is not None:
            task["message"] = message
        
        if output_url is not None:
            task["output_url"] = output_url
        
        if output_path is not None:
            task["output_path"] = output_path
        
        if error is not None:
            task["error"] = error
        
        # ✅ 更新 metadata
        if metadata is not None:
            if "metadata" not in task:
                task["metadata"] = {}
            task["metadata"].update(metadata)
        
        task["updated_at"] = datetime.now().isoformat()
        
        logger.info(f"Updated task {task_id}: {status} ({progress})")
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """獲取任務信息"""
        return self.tasks.get(task_id)
    
    def list_tasks(
        self,
        status: Optional[str] = None,
        limit: int = 100
    ) -> list:
        """列出任務"""
        tasks = list(self.tasks.values())
        
        # 過濾狀態
        if status:
            tasks = [t for t in tasks if t["status"] == status]
        
        # 按創建時間排序（最新的在前）
        tasks.sort(key=lambda x: x["created_at"], reverse=True)
        
        # 限制數量
        return tasks[:limit]
    
    def delete_task(self, task_id: str) -> bool:
        """刪除任務"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            logger.info(f"Deleted task: {task_id}")
            return True
        return False


# 全局單例
task_manager = TaskManager()
