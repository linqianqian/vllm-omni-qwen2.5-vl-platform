"""
启动脚本 - 单端口运行 FastAPI + Gradio
"""
import uvicorn


def main():
    uvicorn.run(
        "src.main:app",
        host="0.0.0.0",
        port=8080,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()
