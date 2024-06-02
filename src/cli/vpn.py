"""
Start/fully-stop ZScaler VPN client.

Context: ZScaler VPN client wants to stay hanging around and start when the
system starts. No way.

systemd files:

  - user level:
    ZSTray.service        /etc/xdg/systemd/user/ZSTray.service

  - system level (root):
    zsaservice.service:   /etc/systemd/system/zsaservice.service
"""

import argparse
import logging
import sys

from src.domain import (
    ZScalerVpnStatus,
    is_zscaler_running,
    start_zscaler,
    stop_zscaler,
)
from src.model import ErrorStr
from src import log

logger = logging.getLogger(__name__)


def parse_cli_argument() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vpn")
    parser.add_argument("--verbose", action="store_true", help="show debug logs")

    subparser = parser.add_subparsers(dest="subcommand")
    subparser.add_parser("up", help="start ZSCaler client")
    subparser.add_parser("down", help="stop ZSCaler client")

    args = parser.parse_args()

    return args


def main() -> ErrorStr | None:

    logger.debug(f"{sys.argv=}")

    current_status = is_zscaler_running()

    match args.subcommand:
        case "up":
            if current_status == ZScalerVpnStatus.all_processes_running:
                logger.info("ZSCaler is already up")
            else:
                start_zscaler()
        case "down":
            if current_status == ZScalerVpnStatus.no_processes_running:
                logger.info("ZSCaler is already down")
            else:
                stop_zscaler()
        case None:
            if current_status == ZScalerVpnStatus.all_processes_running:
                logger.info("ZSCaler is running")
            elif current_status == ZScalerVpnStatus.some_processes_running:
                logger.info("ZSCaler is half-running")
            elif current_status == ZScalerVpnStatus.no_processes_running:
                logger.info("ZSCaler is not running")
            else:
                raise NotImplementedError(
                    f"unsupported {ZScalerVpnStatus.__name__} value: {current_status}"
                )
        case _:
            raise NotImplementedError(f"unexpected subcommand found: {args.subcommand}")


if __name__ == "__main__":
    args = parse_cli_argument()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format=log.VERBOSE_FORMAT if args.verbose else log.QUIET_FORMAT,
    )

    if error := main():
        logger.error(error)
        exit(0)
