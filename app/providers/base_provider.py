from abc import ABC, abstractmethod
from typing import Dict, Any
from fastapi.responses import JSONResponse

class BaseProvider(ABC):
    @abstractmethod
    async def chat_completion(self, request_data: Dict[str, Any]) -> JSONResponse:
        pass

    @abstractmethod
    async def get_models(self) -> JSONResponse:
        pass
