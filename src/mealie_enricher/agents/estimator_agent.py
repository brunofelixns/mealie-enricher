import json
import logging

import httpx
from agents import Agent, ModelSettings, RunConfig, Runner
from agents.retry import ModelRetrySettings

from ..config import LlmSettings
from .legacy_chat_model import LegacyChatModel

logger = logging.getLogger(__name__)


class AgentLlmRunner:
    def __init__(self, settings: LlmSettings, http: httpx.AsyncClient) -> None:
        self.settings = settings
        self.agent = Agent(
            name="Nutrition estimator",
            instructions=None,
            model=LegacyChatModel(settings, http),
        )

    async def complete(self, prompt: str, *, max_tokens: int) -> str | None:
        if not self.settings.enabled or not self.settings.api_key:
            return None
        try:
            result = await Runner.run(
                self.agent,
                prompt,
                max_turns=1,
                run_config=RunConfig(
                    tracing_disabled=True,
                    model_settings=ModelSettings(
                        temperature=self.settings.temperature,
                        max_tokens=max_tokens,
                        retry=ModelRetrySettings(max_retries=0),
                    ),
                ),
            )
            return result.final_output if isinstance(result.final_output, str) else None
        except httpx.HTTPStatusError as error:
            response = error.response
            details = str(error)
            try:
                body = response.json()
                provider_error = body.get("error") if isinstance(body, dict) else None
                if isinstance(provider_error, dict):
                    details = json.dumps(
                        {key: provider_error.get(key) for key in ("code", "param", "message")},
                        ensure_ascii=False,
                    )
            except ValueError:
                pass
            details = details.replace(self.settings.api_key, "[redacted]")[:1000]
            logger.warning(
                "LLM estimation failed (model=%s, status=%s, request_id=%s): %s",
                self.settings.model,
                response.status_code,
                response.headers.get("x-request-id", "unknown"),
                details,
            )
            return None
        except Exception as error:
            logger.warning("LLM estimation failed: %s", error)
            return None
