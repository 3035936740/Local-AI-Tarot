import ollama, httpx

class CustomAsyncClient(ollama.AsyncClient):
    def __init__(self, host: str = None, api_key: str = None, **kwargs):
        super().__init__(host, **kwargs)
        self.api_key = api_key
            
            # 注册请求前的事件钩子
        self._client.event_hooks["request"] = [self._inject_api_key]

    async def _inject_api_key(self, request: httpx.Request):
        """在发送请求前自动注入 API Key"""
        if self.api_key:
            request.headers["Authorization"] = f"Bearer {self.api_key}"