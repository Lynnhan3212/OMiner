import hashlib
import math
import re
from typing import Any

from openai import OpenAI


def normalize_vector(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class EmbeddingClient:
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class MockEmbeddingClient(EmbeddingClient):
    def __init__(self, dimensions: int = 64):
        self.dimensions = dimensions

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in texts]

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = [_normalize_token(token) for token in re.findall(r"[a-z0-9]+", text.lower())]
        tokens = [token for token in tokens if token]
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            vector[index] += 1.0
        return normalize_vector(vector)


class OpenAIEmbeddingClient(EmbeddingClient):
    def __init__(self, api_key: str, model: str, base_url: str | None = None, batch_size: int = 64):
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = OpenAI(**kwargs)
        self.model = model
        self.batch_size = batch_size

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        embeddings: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            response = self.client.embeddings.create(model=self.model, input=batch)
            embeddings.extend(normalize_vector(item.embedding) for item in response.data)
        return embeddings


def get_embedding_client(config: dict[str, Any]) -> EmbeddingClient:
    if config.get("mode") == "real":
        return OpenAIEmbeddingClient(
            api_key=config["llm_api_key"],
            model=config.get("embedding_model", "text-embedding-3-small"),
            base_url=config.get("llm_base_url"),
            batch_size=int(config.get("embedding_batch_size", 64)),
        )
    return MockEmbeddingClient()


def _normalize_token(token: str) -> str:
    synonyms = {
        "debugging": "debug",
        "debugged": "debug",
        "retrieved": "retrieval",
        "retrieve": "retrieval",
        "retrieves": "retrieval",
        "returns": "return",
        "returned": "return",
        "chunks": "chunk",
        "logs": "log",
        "developers": "developer",
        "calendars": "calendar",
    }
    return synonyms.get(token, token)
