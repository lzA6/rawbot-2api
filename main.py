import json
from contextlib import asynccontextmanager
from typing import Optional, Union

from fastapi import FastAPI, Request, HTTPException, Depends, Header
from fastapi.responses import JSONResponse, StreamingResponse
from loguru import logger

from app.core.config import settings
from app.providers.rawbot_provider import RawbotProvider

# 日志配置保持不变
logger.add(
    "logs/app.log", 
    rotation="10 MB", 
    retention="7 days", 
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} - {message}",
    encoding="utf-8"
)
logger.add(
    lambda msg: print(msg, end=''),
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}:{function}:{line}</cyan> - <level>{message}</level>",
    colorize=True
)

provider = RawbotProvider()

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"应用启动中... {settings.APP_NAME} v{settings.APP_VERSION}")
    logger.info("服务已进入 'Dual-Mode Smart Response' 模式。")
    logger.info(f"服务将在 http://localhost:{settings.NGINX_PORT} 上可用")
    yield
    logger.info("应用关闭。")

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=settings.DESCRIPTION,
    lifespan=lifespan
)

async def verify_api_key(authorization: Optional[str] = Header(None)):
    if settings.API_MASTER_KEY and settings.API_MASTER_KEY != "1":
        if not authorization or "bearer" not in authorization.lower():
            raise HTTPException(status_code=401, detail="需要 Bearer Token 认证。")
        token = authorization.split(" ")[-1]
        if token != settings.API_MASTER_KEY:
            raise HTTPException(status_code=403, detail="无效的 API Key。")

# --- [核心修正] ---
# 添加 response_model=None 来解决 FastAPI 启动错误
@app.post(
    "/v1/chat/completions",
    dependencies=[Depends(verify_api_key)],
    response_model=None 
)
async def chat_completions(request: Request) -> Union[JSONResponse, StreamingResponse]:
    try:
        request_data = await request.json()
        
        response = await provider.chat_completion(request_data)
        
        if isinstance(response, JSONResponse):
             # 确保 response.body 是字节串
             body_bytes = response.body
             logger.info(f"--- [发送非流式响应] ---\n{json.dumps(json.loads(body_bytes.decode('utf-8')), indent=2, ensure_ascii=False)}")

        return response
    except Exception as e:
        logger.error(f"处理聊天请求时发生顶层错误: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")

@app.get("/v1/models", dependencies=[Depends(verify_api_key)], response_class=JSONResponse)
async def list_models():
    # provider.get_models() 已经返回 JSONResponse，直接返回即可
    return await provider.get_models()

@app.get("/", summary="根路径", include_in_schema=False)
def root():
    return {"message": f"欢迎来到 {settings.APP_NAME} v{settings.APP_VERSION}. 服务运行正常。"}
