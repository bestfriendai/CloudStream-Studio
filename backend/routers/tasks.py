from fastapi import APIRouter, HTTPException
from models import TaskStatus
from utils.task_manager import task_manager
from typing import List, Optional

router = APIRouter(prefix="/api/tasks", tags=["Task Management"])

@router.get("/{task_id}", response_model=TaskStatus)
async def get_task_status(task_id: str):
    """
    查詢任務狀態
    """
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return task

@router.get("/", response_model=List[TaskStatus])
async def list_tasks(
    status: Optional[str] = None,
    limit: int = 50
):
    """
    列出所有任務
    
    Args:
        status: 過濾狀態 (pending, processing, completed, failed)
        limit: 返回數量限制
    """
    tasks = task_manager.list_tasks(status=status)
    return tasks[:limit]

@router.delete("/{task_id}")
async def cancel_task(task_id: str):
    """
    取消/刪除任務
    """
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # 如果任務正在處理中，標記為取消
    if task.status in ["pending", "processing"]:
        task_manager.update_task(task_id, status="cancelled")
    
    # 刪除任務記錄
    task_manager.delete_task(task_id)
    
    return {"message": f"Task {task_id} cancelled"}

@router.post("/{task_id}/retry")
async def retry_task(task_id: str):
    """
    重試失敗的任務
    """
    task = task_manager.get_task(task_id)
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status != "failed":
        raise HTTPException(
            status_code=400, 
            detail="Only failed tasks can be retried"
        )
    
    # 重置任務狀態
    task_manager.update_task(
        task_id,
        status="pending",
        progress=0.0,
        error=None,
        message="Task queued for retry"
    )
    
    return {"message": f"Task {task_id} queued for retry"}
