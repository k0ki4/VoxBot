import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()



@dataclass(frozen=True)
class BotConfig:
    token: str


@dataclass(frozen=True)
class AppConfig:
    env: str
    log_level: str


@dataclass(frozen=True)
class Config:
    bot: BotConfig
    app: AppConfig


def load_config() -> Config:
    return Config(
        bot=BotConfig(
            token=os.getenv("BOT_TOKEN")
        ),
        app=AppConfig(
            env=os.getenv("ENV", "dev"),
            log_level=os.getenv("LOG_LEVEL", "INFO")
        )
    )
