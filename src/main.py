"""
FastAPI 主应用
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
import time
import logging
import os

from .config import get_settings
from .api.router import api_router
from .services.llm_client import close_llm_client

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 页面自定义 CSS
CUSTOM_CSS = """
.sidebar { width: 200px !important; min-width: 200px !important; margin-left: -20px !important; }
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    from .database import init_db
    from .monitoring.rate_limiter import monitor
    
    init_db()  # 初始化数据库表
    monitor.start_monitoring()  # 启动系统监控
    
    logger.info("🚀 启动 vLLM-Omni 多模态推理平台...")
    yield
    # 关闭时
    logger.info("🛑 关闭应用...")
    monitor.stop_monitoring()
    await close_llm_client()


def create_app() -> FastAPI:
    """创建 FastAPI 应用"""
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="vLLM-Omni 多模态推理平台 API",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc"
    )

    # 添加 CORS 中间件
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 注册路由
    app.include_router(api_router, prefix="/api")

    # 请求日志中间件
    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s"
        )
        return response

    # 全局异常处理器
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"全局异常: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": {"message": str(exc), "type": "internal_error"}}
        )

    # 健康检查
    @app.get("/health", tags=["health"])
    async def health_check():
        return {"status": "healthy", "service": settings.app_name}

    # 挂载前端静态文件
    frontend_path = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
    if os.path.exists(frontend_path):
        app.mount("/", StaticFiles(directory=frontend_path, html=True), name="frontend")

    return app


# 创建应用实例
app = create_app()