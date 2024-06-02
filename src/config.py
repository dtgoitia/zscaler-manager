from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path

from src.constants import CONFIG_PATH
from src.model import Seconds
import logging

logger = logging.getLogger(__name__)


class ConfigFileNotFound(Exception): ...


def read_config() -> Config:
    return Config.from_path(path=CONFIG_PATH)


@dataclass(frozen=True)
class Config:
    wait_between_checks: Seconds
    notification_bin: Path

    def from_path(path: Path) -> Config:
        if not CONFIG_PATH.exists():
            raise ConfigFileNotFound(f"configuration file does not exist: {path}")

        config = json.loads(path.read_text())

        notification_bin_path = Path(config["notification_bin"]).expanduser()
        if not notification_bin_path.exists():
            logger.warn(
                "invalid 'notification_bin', file does not"
                f" exist: {notification_bin_path}"
            )

        return Config(
            wait_between_checks=config["wait_between_checks_in_seconds"],
            notification_bin=notification_bin_path,
        )
