"""
Standard LLM configuration utility.

Primary : meta-llama/llama-3.3-70b-instruct:free  via OpenRouter
Fallback1: llama-3.3-70b-versatile                via Groq
Fallback2: llama-4-scout-17b-16e-instruct         via Groq

Triggers next fallback on:  exception  OR  empty content returned

Usage:
    from llm_utility import create_llm
    llm = create_llm()                        # conversational (temp 0.3)
    llm = create_llm(temperature=0.0)         # analytical
    structured = llm.with_structured_output(MySchema)
"""

from __future__ import annotations

import logging
import os
from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessageChunk, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from typing import Iterator
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from pydantic import PrivateAttr

logger = logging.getLogger(__name__)

OPENROUTER_PRIMARY_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
GROQ_PRIMARY_MODEL       = "llama-3.3-70b-versatile"
GROQ_SECONDARY_MODEL     = "meta-llama/llama-4-scout-17b-16e-instruct"


class FallbackChatModel(BaseChatModel):
    """
    A proper BaseChatModel that tries multiple providers in order.
    Advances to next model on exception OR empty content.
    Fully supports bind_tools() and with_structured_output().
    """

    _models: list = PrivateAttr()

    def __init__(self, *, models: list, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._models = models

    @property
    def _llm_type(self) -> str:
        return "fallback_chat_model"

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_exc: Optional[Exception] = None
        for i, mdl in enumerate(self._models):
            try:
                result = mdl.invoke(messages, stop=stop)
                # Normalise to ChatResult
                if isinstance(result, ChatResult):
                    if result.generations and result.generations[0].message.content:
                        return result
                    logger.warning("Model %d (%s) returned empty ChatResult — trying next", i, type(mdl).__name__)
                    continue
                # BaseMessage path
                content = result.content if hasattr(result, "content") else str(result)
                if content:
                    return ChatResult(generations=[ChatGeneration(message=result)])
                logger.warning("Model %d (%s) returned empty content — trying next", i, type(mdl).__name__)
            except Exception as exc:
                last_exc = exc
                logger.warning("Model %d (%s) failed: %s — trying next", i, type(mdl).__name__, exc)

        if last_exc:
            raise last_exc
        raise RuntimeError("All LLM models returned empty content")

    def _stream(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> Iterator[ChatGenerationChunk]:
        """Stream tokens from the first working model, falling back on error or empty output."""
        last_exc: Optional[Exception] = None
        for i, mdl in enumerate(self._models):
            try:
                yielded_anything = False
                for chunk in mdl.stream(messages, stop=stop):
                    yielded_anything = True
                    content = chunk.content if hasattr(chunk, "content") else ""
                    gen_chunk = ChatGenerationChunk(message=AIMessageChunk(content=content))
                    if run_manager:
                        run_manager.on_llm_new_token(content, chunk=gen_chunk)
                    yield gen_chunk
                if yielded_anything:
                    return
                logger.warning("Streaming model %d (%s) returned nothing — trying next", i, type(mdl).__name__)
            except StopIteration:
                return
            except Exception as exc:
                last_exc = exc
                logger.warning("Streaming model %d (%s) stream failed: %s — trying next", i, type(mdl).__name__, exc)

        if last_exc:
            raise last_exc
        raise RuntimeError("All LLM models returned empty stream")

    def bind_tools(self, tools: Any, **kwargs: Any) -> "FallbackChatModel":
        bound = [
            mdl.bind_tools(tools, **kwargs) if hasattr(mdl, "bind_tools") else mdl
            for mdl in self._models
        ]
        return FallbackChatModel(models=bound)

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        from langchain_core.runnables import RunnableLambda

        parsers = [
            mdl.with_structured_output(schema, **kwargs)
            for mdl in self._models
            if hasattr(mdl, "with_structured_output")
        ]

        def _invoke(input_: Any) -> Any:
            last_exc: Optional[Exception] = None
            for j, p in enumerate(parsers):
                try:
                    result = p.invoke(input_)
                    if result is not None:
                        return result
                    logger.warning("Structured-output model %d returned None — trying next", j)
                except Exception as exc:
                    last_exc = exc
                    logger.warning("Structured-output model %d failed: %s — trying next", j, exc)
            if last_exc:
                raise last_exc
            raise RuntimeError("All structured-output models failed")

        return RunnableLambda(_invoke)


def create_llm(
    temperature: float = 0.3,
    max_tokens: int = 1024,
    **kwargs: Any,
) -> BaseChatModel:
    """
    Build and return the FallbackChatModel chain.
    Falls back gracefully if GROQ_API_KEY is absent.
    """
    openrouter_key = os.environ.get("OPENROUTER_API_KEY")
    if not openrouter_key:
        raise ValueError("OPENROUTER_API_KEY environment variable is not set.")

    primary = ChatOpenAI(
        model=OPENROUTER_PRIMARY_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        openai_api_key=openrouter_key,
        openai_api_base="https://openrouter.ai/api/v1",
    )

    groq_key = os.environ.get("GROQ_API_KEY")
    if not groq_key:
        logger.warning("GROQ_API_KEY not set — running without Groq fallback")
        return primary

    groq_primary = ChatGroq(
        model=GROQ_PRIMARY_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        groq_api_key=groq_key,
    )
    groq_secondary = ChatGroq(
        model=GROQ_SECONDARY_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        groq_api_key=groq_key,
    )

    logger.info(
        "LLM chain: OpenRouter(%s) → Groq(%s) → Groq(%s)",
        OPENROUTER_PRIMARY_MODEL, GROQ_PRIMARY_MODEL, GROQ_SECONDARY_MODEL,
    )
    return FallbackChatModel(models=[primary, groq_primary, groq_secondary])
