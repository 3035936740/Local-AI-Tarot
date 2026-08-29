from openai import AsyncOpenAI

from utils import CustomAsyncClient


def normalize_openai_base_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw.startswith(("http://", "https://")):
        raw = f"http://{raw}"
    raw = raw.rstrip("/")
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"


def resolve_provider(provider: str | None, url: str) -> str:
    name = (provider or "").strip().lower()
    if name in {"openai", "ollama"}:
        return name
    if name:
        raise ValueError(f"unknown provider: {name}")
    lowered = (url or "").lower()
    if "openai.com" in lowered or "/v1" in lowered:
        return "openai"
    return "ollama"


class OllamaChatClient:
    def __init__(self, url: str, api_key: str | None = None):
        self.api_key = api_key
        self._inner = CustomAsyncClient(host=url, api_key=api_key)

    @property
    def base_url(self) -> str:
        return str(self._inner._client.base_url).rstrip("/")

    async def chat(self, *, model: str, messages: list[dict]) -> dict:
        return await self._inner.chat(model=model, messages=messages)


class OpenAIChatClient:
    def __init__(self, url: str, api_key: str | None = None, client=None):
        self.api_key = api_key
        self.base_url = normalize_openai_base_url(url)
        self._inner = client or AsyncOpenAI(
            base_url=self.base_url,
            api_key=api_key or "not-set",
        )

    async def chat(self, *, model: str, messages: list[dict]) -> dict:
        response = await self._inner.chat.completions.create(model=model, messages=messages)
        content = ""
        if response.choices:
            content = response.choices[0].message.content or ""
        return {"message": {"content": content}}


def create_chat_client(provider: str | None, url: str, api_key: str | None):
    resolved = resolve_provider(provider, url)
    if resolved == "openai":
        return OpenAIChatClient(url, api_key)
    return OllamaChatClient(url, api_key)
