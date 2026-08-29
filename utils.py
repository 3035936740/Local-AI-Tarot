import ollama
import httpx


class CustomAsyncClient(ollama.AsyncClient):
    def __init__(self, host: str = None, api_key: str = None, **kwargs):
        super().__init__(host, **kwargs)
        self.api_key = api_key
        hooks = self._client.event_hooks.setdefault("request", [])
        hooks.append(self._inject_api_key)

    async def _inject_api_key(self, request: httpx.Request):
        if self.api_key:
            request.headers["Authorization"] = f"Bearer {self.api_key}"
