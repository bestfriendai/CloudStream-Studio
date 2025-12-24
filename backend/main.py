# backend/main.py

import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager

from config import get_settings
from services.gcs_service import get_gcs_service
from utils.thumbnails import get_thumbnail_generator
from routers import video, tasks, files, stream, thumb

# 設置日誌
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


# ==================== 生命週期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """應用生命週期管理"""
    # 啟動
    try:
        logger.info("🚀 應用啟動中...")
        
        # 初始化 GCS Service
        logger.info("   初始化 GCS Service...")
        storage = get_gcs_service()
        logger.info("   ✅ GCS Service 已初始化")
        
        # 初始化 Thumbnail Generator（單例模式）
        logger.info("   初始化 Thumbnail Generator...")
        thumbnail_generator = get_thumbnail_generator() 
        logger.info("   ✅ Thumbnail Generator 已設置")
        
        logger.info("✅ 應用啟動完成")
        
    except Exception as e:
        logger.error(f"❌ 應用啟動失敗: {e}", exc_info=True)
        raise
    
    yield
    
    # 關閉
    logger.info("👋 應用關閉中...")


# ==================== FastAPI 應用 ====================

app = FastAPI(
    title="CloudStream Studio API",
    description="影片流媒體管理系統",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
)

# CORS 中間件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Range",
        "Accept-Ranges", 
        "Content-Length",
        "Content-Type",
        "X-Cache",
        "X-Response-Time"
    ],
    max_age=3600
)


# ==================== 全局異常處理 ====================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """全局異常處理"""
    logger.error(f"❌ {request.method} {request.url.path} - {exc.__class__.__name__}: {exc}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc)}
    )


# ==================== 路由 ====================

app.include_router(video.router)
app.include_router(tasks.router)
app.include_router(files.router)
app.include_router(stream.router)
app.include_router(thumb.router)


# ==================== 健康檢查 ====================

@app.get("/")
async def root():
    """根路徑"""
    return {
        "message": "CloudStream Studio API",
        "version": "1.0.0",
        "status": "running"
    }


@app.get("/api/health")
async def health_check():
    """健康檢查"""
    try:
        storage = get_gcs_service()
        
        return {
            "status": "healthy",
            "services": {
                "gcs": "connected",
                "thumbnails": "ready"
            },
            "bucket": storage.bucket_name
        }
    except Exception as e:
        logger.error(f"❌ 健康檢查失敗: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e)
            }
        )


# ==================== 請求日誌中間件 ====================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """記錄所有請求"""
    response = await call_next(request)
    
    status_emoji = "✅" if response.status_code < 400 else "❌"
    logger.info(f"{status_emoji} {request.method} {request.url.path} - {response.status_code}")
    
    return response


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
