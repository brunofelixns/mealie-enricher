from collections.abc import AsyncIterator
from typing import Any

import httpx
from agents import Model, ModelSettings
from agents.agent_output import AgentOutputSchemaBase
from agents.handoffs import Handoff
from agents.items import ModelResponse, TResponseInputItem, TResponseStreamEvent
from agents.models.interface import ModelTracing
from agents.tool import Tool
from agents.usage import Usage
from openai.types.responses import ResponseOutputMessage, ResponseOutputText
from openai.types.responses.response_prompt_param import ResponsePromptParam

from ..config import LlmSettings


class LegacyChatModel(Model):
    """Bridge the SDK model interface to the original configurable HTTP contract."""

    def __init__(self, settings: LlmSettings, http: httpx.AsyncClient) -> None:
        self.settings = settings
        self.http = http

    async def get_response(
        self,
        system_instructions: str | None,
        input: str | list[TResponseInputItem],
        model_settings: ModelSettings,
        tools: list[Tool],
        output_schema: AgentOutputSchemaBase | None,
        handoffs: list[Handoff],
        tracing: ModelTracing,
        *,
        previous_response_id: str | None,
        conversation_id: str | None,
        prompt: ResponsePromptParam | None,
    ) -> ModelResponse:
        if system_instructions or tools or output_schema or handoffs:
            raise ValueError("Unsupported agent features in compatibility mode")
        if isinstance(input, str):
            text = input
        else:
            if len(input) != 1:
                raise ValueError("Expected one user message")
            message: Any = input[0]
            if message.get("role") != "user" or not isinstance(message.get("content"), str):
                raise ValueError("Expected original user prompt")
            text = message["content"]
        response = await self.http.post(
            self.settings.base_url + self.settings.endpoint_url,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.settings.api_key,
            },
            json={
                "model": self.settings.model,
                "messages": [{"role": "user", "content": text}],
                "temperature": model_settings.temperature,
                "max_tokens": model_settings.max_tokens,
            },
            timeout=None,
            follow_redirects=True,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        if not isinstance(content, str):
            raise ValueError("LLM returned empty response")
        return ModelResponse(
            output=[
                ResponseOutputMessage(
                    id="legacy-message",
                    type="message",
                    role="assistant",
                    status="completed",
                    content=[ResponseOutputText(type="output_text", text=content, annotations=[])],
                )
            ],
            usage=Usage(requests=1),
            response_id=None,
        )

    def stream_response(self, *args: Any, **kwargs: Any) -> AsyncIterator[TResponseStreamEvent]:
        raise NotImplementedError("The original service does not stream model responses")
