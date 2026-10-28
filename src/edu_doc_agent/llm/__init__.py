"""Единый шлюз к LLM: клиент, кэш, ретраи, подмена в тестах."""

from edu_doc_agent.llm.base import LLMClient
from edu_doc_agent.llm.fake import FakeLLMClient, LLMCall

__all__ = ["FakeLLMClient", "LLMCall", "LLMClient"]
