import logging
import time

from src.config import Config, ConfigFileNotFound, read_config
from src.notification import notify
from src.domain import (
    InternetSecurityStatus,
    ZScalerVpnStatus,
    is_zscaler_running,
    is_internet_security_on,
    in_a_call,
)
from src.model import ErrorStr

from src import log

logger = logging.getLogger(__name__)


def _check(config: Config) -> None:
    vpn_status = is_zscaler_running()
    if vpn_status == ZScalerVpnStatus.no_processes_running:
        logger.info("ZScaler is OFF")
        return

    security_status = is_internet_security_on()
    match security_status:
        case InternetSecurityStatus.unknown:
            ...  # nothing found in the DB, or the DB file itself was not found
        case InternetSecurityStatus.off:
            ...  # nothing found in the DB, or the DB file itself was not found
        case InternetSecurityStatus.on:
            if in_a_call():
                notify(msg="turn lights off", config=config)
            else:
                notify(msg="Z Scaler internet security is on", config=config)
        case _:
            raise NotImplementedError(
                f"unsupported {InternetSecurityStatus.__name__}: {security_status.name!r}"
            )


def main() -> ErrorStr | None:
    try:
        config = read_config()
    except ConfigFileNotFound as error:
        return str(error)

    wait = config.wait_between_checks

    while True:
        _check(config=config)
        logger.info(f"waiting {wait}s before the next check")
        time.sleep(wait)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.DEBUG,
        format=log.VERBOSE_FORMAT,
    )

    if error := main():
        logger.error(error)
        exit(0)
