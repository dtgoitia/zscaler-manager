import subprocess

from src.config import Config


def notify(config: Config, msg: str) -> None:
    subprocess.run([config.notification_bin, msg])
