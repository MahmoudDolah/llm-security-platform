"""
LLM Client Module

Abstracts different LLM backends (Ollama, OpenAI, Anthropic).
"""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import httpx
from dataclasses import dataclass


@dataclass
class LLMResponse:
    """Standardized LLM response"""

    content: str
    model: str
    tokens_used: Optional[int] = None
    finish_reason: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMClient(ABC):
    """Abstract base class for LLM clients"""

    @abstractmethod
    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate a response from the LLM"""
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """Check if LLM backend is healthy"""
        pass


class OllamaClient(LLMClient):
    """
    Client for local Ollama LLM server.

    Ollama provides a local LLM server compatible with OpenAI API.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama2",
        timeout: int = 30,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = httpx.AsyncClient(timeout=timeout)

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate response using Ollama"""
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": kwargs.get("model", self.model),
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
            },
        }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            return LLMResponse(
                content=data.get("response", ""),
                model=data.get("model", self.model),
                tokens_used=data.get("eval_count"),
                finish_reason="stop",
                metadata={"ollama_data": data},
            )
        except httpx.HTTPError as e:
            error_detail = (
                f"URL: {url}, Status: {getattr(e.response, 'status_code', 'N/A')}"
            )
            if hasattr(e, "response"):
                error_detail += f", Response: {e.response.text[:200]}"
            raise Exception(f"Ollama request failed: {str(e)} - {error_detail}")

    async def health_check(self) -> bool:
        """Check if Ollama is running"""
        try:
            response = await self.client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False


class OpenAIClient(LLMClient):
    """
    Client for OpenAI API.

    Supports GPT-3.5, GPT-4, and other OpenAI models.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-3.5-turbo",
        timeout: int = 30,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.base_url = "https://api.openai.com/v1"
        self.client = httpx.AsyncClient(
            timeout=timeout, headers={"Authorization": f"Bearer {api_key}"}
        )

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate response using OpenAI"""
        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": kwargs.get("model", self.model),
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
        }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            choice = data["choices"][0]
            usage = data.get("usage", {})

            return LLMResponse(
                content=choice["message"]["content"],
                model=data["model"],
                tokens_used=usage.get("total_tokens"),
                finish_reason=choice.get("finish_reason"),
                metadata={"openai_data": data},
            )
        except httpx.HTTPError as e:
            raise Exception(f"OpenAI request failed: {str(e)}")

    async def health_check(self) -> bool:
        """Check if OpenAI API is accessible"""
        try:
            response = await self.client.get(f"{self.base_url}/models")
            return response.status_code == 200
        except Exception:
            return False


class AnthropicClient(LLMClient):
    """
    Client for Anthropic Claude API.

    Supports Claude 3 and other Anthropic models.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-sonnet-20240229",
        timeout: int = 30,
        max_tokens: int = 1000,
        temperature: float = 0.7,
    ):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.base_url = "https://api.anthropic.com/v1"
        self.client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
        )

    async def generate(self, prompt: str, **kwargs) -> LLMResponse:
        """Generate response using Anthropic Claude"""
        url = f"{self.base_url}/messages"

        payload = {
            "model": kwargs.get("model", self.model),
            "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            "temperature": kwargs.get("temperature", self.temperature),
            "messages": [{"role": "user", "content": prompt}],
        }

        try:
            response = await self.client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()

            content = data["content"][0]["text"]
            usage = data.get("usage", {})

            return LLMResponse(
                content=content,
                model=data["model"],
                tokens_used=usage.get("input_tokens", 0)
                + usage.get("output_tokens", 0),
                finish_reason=data.get("stop_reason"),
                metadata={"anthropic_data": data},
            )
        except httpx.HTTPError as e:
            raise Exception(f"Anthropic request failed: {str(e)}")

    async def health_check(self) -> bool:
        """Check if Anthropic API is accessible"""
        # Anthropic doesn't have a dedicated health endpoint
        # We'll just check if we can make a minimal request
        try:
            # Make a minimal request
            url = f"{self.base_url}/messages"
            payload = {
                "model": self.model,
                "max_tokens": 10,
                "messages": [{"role": "user", "content": "test"}],
            }
            response = await self.client.post(url, json=payload)
            return response.status_code == 200
        except Exception:
            return False


class LLMClientFactory:
    """Factory for creating LLM clients"""

    @staticmethod
    def create_client(backend: str, **kwargs) -> LLMClient:
        """
        Create an LLM client based on backend type.

        Args:
            backend: Type of backend (ollama, openai, anthropic)
            **kwargs: Backend-specific configuration

        Returns:
            LLM client instance
        """
        backend = backend.lower()

        if backend == "ollama":
            return OllamaClient(
                base_url=kwargs.get("ollama_base_url", "http://localhost:11434"),
                model=kwargs.get("model", "llama2"),
                timeout=kwargs.get("timeout", 30),
                max_tokens=kwargs.get("max_tokens", 1000),
                temperature=kwargs.get("temperature", 0.7),
            )

        elif backend == "openai":
            if "api_key" not in kwargs:
                raise ValueError("OpenAI backend requires api_key")
            return OpenAIClient(
                api_key=kwargs["api_key"],
                model=kwargs.get("model", "gpt-3.5-turbo"),
                timeout=kwargs.get("timeout", 30),
                max_tokens=kwargs.get("max_tokens", 1000),
                temperature=kwargs.get("temperature", 0.7),
            )

        elif backend == "anthropic":
            if "api_key" not in kwargs:
                raise ValueError("Anthropic backend requires api_key")
            return AnthropicClient(
                api_key=kwargs["api_key"],
                model=kwargs.get("model", "claude-3-sonnet-20240229"),
                timeout=kwargs.get("timeout", 30),
                max_tokens=kwargs.get("max_tokens", 1000),
                temperature=kwargs.get("temperature", 0.7),
            )

        else:
            raise ValueError(f"Unsupported backend: {backend}")


# Example usage
if __name__ == "__main__":
    import asyncio

    async def test_ollama():
        client = LLMClientFactory.create_client("ollama")

        # Health check
        healthy = await client.health_check()
        print(f"Ollama healthy: {healthy}")

        if healthy:
            # Generate response
            response = await client.generate("What is the capital of France?")
            print(f"Response: {response.content}")

    asyncio.run(test_ollama())
