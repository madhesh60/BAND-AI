"""Configuration management for the coding assistant."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


@dataclass
class BandConfig:
    """BAND platform configuration."""
    api_key: str = ""
    rest_url: str = "https://app.band.ai/"
    ws_url: str = "wss://app.band.ai/api/v1/socket/websocket"


@dataclass
class LLMConfig:
    """LLM provider configuration."""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    api_key: str = ""
    temperature: float = 0.7
    max_tokens: int = 4096


@dataclass
class GitConfig:
    """Git repository configuration."""
    repo_url: Optional[str] = None
    default_branch: str = "main"
    github_token: Optional[str] = None
    auto_merge_threshold: str = "low"


@dataclass
class AgentConfig:
    """Individual agent configuration."""
    agent_id: str
    api_key: str
    role: str
    description: str
    llm: LLMConfig = field(default_factory=LLMConfig)


@dataclass
class AppConfig:
    """Main application configuration."""
    band: BandConfig = field(default_factory=BandConfig)
    agents: dict = field(default_factory=dict)
    git: GitConfig = field(default_factory=GitConfig)
    log_level: str = "INFO"


class ConfigManager:
    """Manages application configuration."""

    _instance: Optional["ConfigManager"] = None

    def __new__(cls) -> "ConfigManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._config: Optional[AppConfig] = None
        self._agent_config: dict = {}

    def load(self, config_path: Optional[Path] = None) -> AppConfig:
        """Load configuration from file and environment variables."""
        if self._config is not None:
            return self._config

        # Load agent configuration
        if config_path is None:
            config_path = Path.cwd() / "agent_config.yaml"

        if config_path.exists():
            with open(config_path) as f:
                self._agent_config = yaml.safe_load(f) or {}

        # Build configuration
        self._config = AppConfig(
            band=BandConfig(
                api_key=os.getenv("BAND_API_KEY", ""),
                rest_url=os.getenv("THENVOI_REST_URL", "https://app.band.ai/"),
                ws_url=os.getenv("THENVOI_WS_URL", "wss://app.band.ai/api/v1/socket/websocket"),
            ),
            git=GitConfig(
                repo_url=os.getenv("GITHUB_REPO_URL"),
                default_branch=os.getenv("DEFAULT_BRANCH", "main"),
                github_token=os.getenv("GITHUB_TOKEN"),
                auto_merge_threshold=os.getenv("AUTO_MERGE_THRESHOLD", "low"),
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )

        return self._config

    @property
    def config(self) -> AppConfig:
        """Get current configuration."""
        if self._config is None:
            return self.load()
        return self._config

    def get_agent_config(self, agent_name: str) -> Optional[AgentConfig]:
        """Get configuration for a specific agent."""
        if not self._agent_config:
            config_path = Path.cwd() / "agent_config.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    self._agent_config = yaml.safe_load(f) or {}

        agents_config = self._agent_config.get("agents", {})
        agent_data = agents_config.get(agent_name)

        if agent_data is None:
            return None

        # Replace environment variables
        agent_id = agent_data.get("agent_id", "").replace("${BAND_API_KEY}", os.getenv("BAND_API_KEY", ""))
        api_key = os.getenv("BAND_API_KEY", "")

        provider = os.getenv("LLM_PROVIDER", "")
        overall_key = os.getenv("OVERALL_API_KEY", "")
        has_overall = overall_key and "your" not in overall_key.lower() and "sk-" in overall_key

        if not provider:
            if has_overall:
                provider = "openrouter"
            else:
                ant_key = os.getenv("ANTHROPIC_API_KEY", "")
                has_anthropic = ant_key and "your" not in ant_key.lower() and "sk-ant" in ant_key
                openai_key = os.getenv("OPENAI_API_KEY", "")
                has_openai = openai_key and "your" not in openai_key.lower() and "sk-" in openai_key
                
                if has_openai:
                    provider = "openai"
                else:
                    provider = "anthropic"

        # Check for agent-specific model (e.g. CODER_MODEL, PLANNER_MODEL)
        agent_model_var = f"{agent_name.upper()}_MODEL"
        llm_model = os.getenv(agent_model_var)

        if provider == "openrouter":
            llm_api_key = overall_key
            if not llm_model:
                llm_model = os.getenv("LLM_MODEL", "anthropic/claude-3.5-sonnet")
        elif provider == "openai":
            llm_api_key = os.getenv("OPENAI_API_KEY", "")
            if not llm_model:
                llm_model = os.getenv("LLM_MODEL", "gpt-4o")
        else:
            llm_api_key = os.getenv("ANTHROPIC_API_KEY", "")
            if not llm_model:
                llm_model = os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

        # Trim spaces if any in the API keys
        if llm_api_key:
            llm_api_key = llm_api_key.strip()

        return AgentConfig(
            agent_id=agent_id,
            api_key=api_key,
            role=agent_data.get("role", ""),
            description=agent_data.get("description", ""),
            llm=LLMConfig(
                provider=provider,
                api_key=llm_api_key,
                model=llm_model,
            ),
        )


# Global config instance
config = ConfigManager()