import httpx
import asyncio
import time
import uuid
from typing import Dict, Any, List, AsyncGenerator
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi import HTTPException
from loguru import logger

from app.core.config import settings
from app.providers.base_provider import BaseProvider
from app.utils.sse_utils import create_chat_completion_chunk, create_sse_data, DONE_CHUNK

class RawbotProvider(BaseProvider):
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=settings.API_REQUEST_TIMEOUT)
        self.providers = [
            {"name": "Cohere", "model": "command-r-08-2024", "token": settings.COHERE_TOKEN, "url": "https://api.cohere.ai/v1/chat", "method": self._call_cohere},
            {"name": "AI21 Labs", "model": "jamba-mini", "token": settings.AI21_TOKEN, "url": "https://api.ai21.com/studio/v1/chat/completions", "method": self._call_ai21},
            {"name": "Mistral", "model": "mistral-small-latest", "token": settings.MISTRAL_TOKEN, "url": "https://api.mistral.ai/v1/chat/completions", "method": self._call_mistral},
        ]

    async def chat_completion(self, request_data: Dict[str, Any]):
        user_prompt = next((m['content'] for m in reversed(request_data.get("messages", [])) if m.get('role') == 'user'), None)
        if not user_prompt:
            raise HTTPException(status_code=400, detail="在 'messages' 中未找到用户消息。")

        # 根据客户端请求决定响应模式
        if request_data.get("stream", False):
            logger.info("检测到流式请求 (stream: true)，启动伪流式生成器。")
            return StreamingResponse(self._stream_response_generator(user_prompt), media_type="text/event-stream")
        else:
            logger.info("处理非流式请求 (stream: false)。")
            content = await self._get_aggregated_content(user_prompt)
            response_data = self._build_non_stream_response(content)
            return JSONResponse(content=response_data)

    async def _get_aggregated_content(self, prompt: str) -> str:
        """在内部并发获取所有结果并格式化为纯文本。"""
        tasks = [provider["method"](prompt, provider) for provider in self.providers]
        results = await asyncio.gather(*tasks)
        return self._format_plain_text_response(results)

    async def _stream_response_generator(self, prompt: str) -> AsyncGenerator[str, None]:
        """伪流式生成器，逐字发送内容。"""
        request_id = f"chatcmpl-{uuid.uuid4()}"
        model_name = settings.VIRTUAL_MODEL
        
        try:
            full_content = await self._get_aggregated_content(prompt)
            
            # 逐字发送，模拟打字机效果
            for char in full_content:
                chunk = create_chat_completion_chunk(request_id, model_name, char)
                sse_event = create_sse_data(chunk)
                logger.info(f"--- [流式发送] ---\n{sse_event.strip()}")
                yield sse_event
                await asyncio.sleep(0.01) # 控制打字速度

            # 发送结束标志
            final_chunk = create_chat_completion_chunk(request_id, model_name, "", "stop")
            final_event = create_sse_data(final_chunk)
            logger.info(f"--- [流式结束] ---\n{final_event.strip()}")
            yield final_event
            yield DONE_CHUNK
            
        except Exception as e:
            logger.error(f"流式生成器发生错误: {e}", exc_info=True)
            error_chunk = create_chat_completion_chunk(request_id, model_name, f"\n服务器内部错误: {e}", "stop")
            yield create_sse_data(error_chunk)
            yield DONE_CHUNK

    def _build_non_stream_response(self, content: str) -> Dict[str, Any]:
        """构建完整的非流式JSON响应。"""
        return {
            "id": f"chatcmpl-{uuid.uuid4()}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": settings.VIRTUAL_MODEL,
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

    def _format_plain_text_response(self, results: List[Dict]) -> str:
        response_parts = []
        for result in results:
            provider_name = result.get("provider", "未知")
            model_name = result.get("model", "N/A")
            header = f"--- [{provider_name} ({model_name})] ---\n"
            
            if result.get("error"):
                content = f"请求失败: {result['content']}\n"
            else:
                content = result.get("content", "无响应内容。\n")
            
            response_parts.append(header + content)
        
        return "\n".join(response_parts)

    # _call_* 方法保持不变
    async def _call_cohere(self, prompt: str, provider_info: Dict) -> Dict:
        payload = {"model": provider_info["model"], "message": prompt, "temperature": 0.5, "max_tokens": 200}
        headers = {"Authorization": f"Bearer {provider_info['token']}", "Content-Type": "application/json"}
        try:
            response = await self.client.post(provider_info["url"], headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return {"provider": provider_info["name"], "model": provider_info["model"], "content": data.get("text", "")}
        except Exception as e:
            logger.error(f"请求 {provider_info['name']} 失败: {e}")
            return {"provider": provider_info["name"], "model": provider_info["model"], "content": str(e), "error": True}

    async def _call_ai21(self, prompt: str, provider_info: Dict) -> Dict:
        payload = {"model": provider_info["model"], "messages": [{"role": "user", "content": prompt}], "temperature": 0.5, "max_tokens": 200}
        headers = {"Authorization": f"Bearer {provider_info['token']}", "Content-Type": "application/json"}
        try:
            response = await self.client.post(provider_info["url"], headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return {"provider": provider_info["name"], "model": provider_info["model"], "content": data["choices"][0]["message"]["content"]}
        except Exception as e:
            logger.error(f"请求 {provider_info['name']} 失败: {e}")
            return {"provider": provider_info["name"], "model": provider_info["model"], "content": str(e), "error": True}

    async def _call_mistral(self, prompt: str, provider_info: Dict) -> Dict:
        payload = {"model": provider_info["model"], "messages": [{"role": "user", "content": prompt}], "temperature": 0.5, "max_tokens": 200}
        headers = {"Authorization": f"Bearer {provider_info['token']}", "Content-Type": "application/json"}
        try:
            response = await self.client.post(provider_info["url"], headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return {"provider": provider_info["name"], "model": provider_info["model"], "content": data["choices"][0]["message"]["content"]}
        except Exception as e:
            logger.error(f"请求 {provider_info['name']} 失败: {e}")
            return {"provider": provider_info["name"], "model": provider_info["model"], "content": str(e), "error": True}

    async def get_models(self) -> JSONResponse:
        model_data = {
            "object": "list",
            "data": [{"id": name, "object": "model", "created": int(time.time()), "owned_by": "lzA6"} for name in settings.KNOWN_MODELS]
        }
        return JSONResponse(content=model_data)
