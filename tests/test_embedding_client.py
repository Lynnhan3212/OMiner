import math

from src.services.embedding_client import MockEmbeddingClient, get_embedding_client, normalize_vector


def test_normalize_vector_returns_unit_vector():
    vector = normalize_vector([3.0, 4.0])

    assert vector == [0.6, 0.8]
    assert round(math.sqrt(sum(value * value for value in vector)), 6) == 1.0


def test_normalize_vector_handles_zero_vector():
    assert normalize_vector([0.0, 0.0]) == [0.0, 0.0]


def test_mock_embedding_client_is_deterministic():
    client = MockEmbeddingClient(dimensions=8)

    first = client.embed_texts(["retrieval debugging", "calendar sync"])
    second = client.embed_texts(["retrieval debugging", "calendar sync"])

    assert first == second
    assert len(first) == 2
    assert len(first[0]) == 8


def test_get_embedding_client_returns_mock_for_mock_mode():
    client = get_embedding_client({"mode": "mock"})

    assert isinstance(client, MockEmbeddingClient)
