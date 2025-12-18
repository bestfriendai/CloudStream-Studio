from typing import Dict, Optional
from datetime import datetime
import uuid
import logging
from models import TaskStatus

logger = logging.getLogger(__name__)

class TaskManager:
    """
    簡單的記憶體任務管理器
    生產環境建議使用 Redis
    """
    
    def __init__(self):
        self._tasks: Dict[str, TaskStatus] = {}
    
    def create_task(self, message: str = "Task created") -> str:
        """創建新任務"""
        task_id = str(uuid.uuid4())
        
        task = TaskStatus(
            task_id=task_id,
            status="pending",
            progress=0.0,
            message=message,
            created_at=datetime.now(),
            updated_at=datetime.now()
        )
        
        self._tasks[task_id] = task
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
        error: Optional[str] = None
    ) -> None:
        """更新任務狀態"""
        if task_id not in self._tasks:
            raise ValueError(f"Task {task_id} not found")
        
        task = self._tasks[task_id]
        
        if status is not None:
            task.status = status
        if progress is not None:
            task.progress = progress
        if message is not None:
            task.message = message
        if output_url is not None:
            task.output_url = output_url
        if output_path is not None:
            task.output_path = output_path
        if error is not None:
            task.error = error
        
        task.updated_at = datetime.now()
        
        logger.info(f"Updated task {task_id}: {status} ({progress})")
    
    def get_task(self, task_id: str) -> Optional[TaskStatus]:
        """獲取任務狀態"""
        return self._tasks.get(task_id)
    
    def delete_task(self, task_id: str) -> None:
        """刪除任務"""
        if task_id in self._tasks:
            del self._tasks[task_id]
            logger.info(f"Deleted task: {task_id}")
    
    def list_tasks(self, status: Optional[str] = None) -> list[TaskStatus]:
        """列出所有任務"""
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        
        return sorted(tasks, key=lambda x: x.created_at, reverse=True)

# 全域任務管理器實例
task_manager = TaskManager()
