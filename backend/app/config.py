from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置，所有可变配置都从环境变量读取。"""

    app_name: str = "sfqqyq-git-creative-distiller"
    app_env: str = "local"
    database_url: str = "sqlite:///./data/app.db"
    workspace_dir: str = "./storage/repos"
    skill_path: str = "../skills/git-creative-discovery/SKILL.md"
    claude_command: str = "claude"
    anthropic_api_key: str = ""
    anthropic_base_url: str = ""
    anthropic_auth_token: str = ""
    anthropic_model: str = ""
    anthropic_default_opus_model: str = ""
    anthropic_default_sonnet_model: str = ""
    anthropic_default_haiku_model: str = ""
    claude_code_subagent_model: str = ""
    claude_code_effort_level: str = ""
    enable_claude: bool = False

    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace_dir).resolve()

    @property
    def skill_file_path(self) -> Path:
        return Path(self.skill_path).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
