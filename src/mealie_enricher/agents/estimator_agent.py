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
        except Exception as error:
            logger.warning("LLM estimation failed: %s", error)
            return None
