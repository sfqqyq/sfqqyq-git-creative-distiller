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
    github_clone_proxy: str = ""
    auth_username: str = "admin"
    auth_password: str = ""
    auth_session_secret: str = ""
    auth_session_seconds: int = 604800
    auth_cookie_name: str = "git_creative_session"
    auth_cookie_secure: bool = False
    minimax_api_key: str = ""
    minimax_api_base_url: str = "https://api.minimax.io/v1"
    minimax_image_model: str = "image-01"
    minimax_image_aspect_ratio: str = "16:9"
    image_output_dir: str = "./storage/images"
    image_url_prefix: str = "/generated-images"
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

    @property
    def image_output_path(self) -> Path:
        return Path(self.image_output_dir).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
