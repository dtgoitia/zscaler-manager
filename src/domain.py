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
import datetime
import enum
import json
import logging
import sqlite3
import subprocess
import os
import textwrap
import time
from pathlib import Path
from typing import Literal, TypeAlias


logger = logging.getLogger(__name__)


def parse_cli_argument() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="vpn")
    parser.add_argument("--verbose", action="store_true", help="show debug logs")

    subparser = parser.add_subparsers(dest="subcommand")
    subparser.add_parser("up", help="start ZSCaler client")
    subparser.add_parser("down", help="stop ZSCaler client")

    args = parser.parse_args()

    return args


def _get_command_without_arguments_from_ps_aux_line(line: str) -> str:
    user, pid, cpu_pct, mem_pct, vsz, rss, tty, stat, start, _time, cmd = line.split(
        maxsplit=10
    )
    cmd_chunks = cmd.split(maxsplit=1)
    if len(cmd_chunks) == 0:
        raise NotImplementedError(
            f"oopss.. something wrong happened when trying to get the cmd from this line: {line!r}"
        )
    return cmd_chunks[0]


def _is_process_running(target_binary_name: str) -> bool:
    logger.debug(
        f"looking for {target_binary_name!r} binary name in the output of `ps aux`"
    )
    process = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    for line in process.stdout.splitlines()[1:]:
        binary_name = _get_command_without_arguments_from_ps_aux_line(line=line)
        if binary_name == target_binary_name:
            logger.debug(f"{target_binary_name!r} binary name found")
            return True
    else:
        logger.debug(f"{target_binary_name!r} binary name not found")
        return False


def _are_processes_running(patterns: list[str]) -> bool:
    """
    This function checks if all patterns are found in `ps aux`. If they are not
    found, it waits a bit and retries.
    """
    not_running = set(patterns)

    attempts = 0
    max_attempts = 5
    wait_between_attempts = 1  # seconds

    while not_running and attempts < max_attempts:
        for binary_name in list(not_running):
            if _is_process_running(target_binary_name=binary_name):
                not_running.remove(binary_name)
                logger.debug(f"{binary_name} is running")
            else:
                logger.debug(f"{binary_name} is not running")

        if not_running:
            logger.info(
                f"{len(not_running)} processes are still is not running, waiting {wait_between_attempts}s before retrying..."
            )
            time.sleep(wait_between_attempts)
            attempts += 1
        else:
            return True

    return False


def _are_processes_not_running(patterns: list[str]) -> bool:
    """
    This function checks if all patterns are not found in `ps aux`. If they are
    found, it waits a bit and retries.
    """
    running = set(patterns)

    attempts = 0
    max_attempts = 5
    wait_between_attempts = 1  # seconds

    while running and attempts < max_attempts:
        for binary_name in list(running):
            if not _is_process_running(target_binary_name=binary_name):
                running.remove(binary_name)
                logger.debug(f"{binary_name} is not running")
            else:
                logger.debug(f"{binary_name} is running")

        if running:
            logger.info(
                f"{len(running)} processes are still is running, waiting {wait_between_attempts}s before retrying..."
            )
            time.sleep(wait_between_attempts)
            attempts += 1
        else:
            return True

    return False


def _is_systemd_unit_enabled(unit_name: str) -> bool:
    logger.debug(f"checking if the unit {unit_name!r} is enabled")
    cmd = ["systemctl", "status", unit_name]
    process = subprocess.run(cmd, capture_output=True, text=True)
    second_line = process.stdout.splitlines()[1].strip()
    expected_prefix = "Loaded: "
    if not second_line.startswith(expected_prefix):
        raise ValueError(
            f"expected the second line to start with {expected_prefix!r} when"
            f' executing `{" ".join(cmd)}`, but got this output instead:\n\n'
            f"{process.stdout}"
        )

    is_enabled = "; enabled; preset: disabled)" in second_line
    logger.debug(f"the unit {unit_name!r} is enabled")
    return is_enabled


def _is_systemd_unit_disabled(unit_name: str) -> bool:
    logger.debug(f"checking if the unit {unit_name!r} is disabled")
    cmd = ["systemctl", "status", unit_name]
    process = subprocess.run(cmd, capture_output=True, text=True)
    second_line = process.stdout.splitlines()[1].strip()
    expected_prefix = "Loaded: "
    if not second_line.startswith(expected_prefix):
        raise ValueError(
            f"expected the second line to start with {expected_prefix!r} when"
            f' executing `{" ".join(cmd)}`, but got this output instead:\n\n'
            f"{process.stdout}"
        )

    is_disabled = "; disabled; preset: disabled)" in second_line
    logger.debug(f"the unit {unit_name!r} is disabled")
    return is_disabled


def _did_gui_start_correctly() -> bool:
    return _are_processes_running(patterns=["/opt/zscaler/bin/ZSTray"])


def _did_gui_stop_correctly() -> bool:
    return _are_processes_not_running(patterns=["/opt/zscaler/bin/ZSTray"])


def _was_daemon_enabled_correctly(service: str) -> bool:
    return _is_systemd_unit_enabled(unit_name=service)


def _did_daemon_start_correctly() -> bool:
    return _are_processes_running(
        patterns=[
            "/opt/zscaler/bin/zsaservice",
            "/opt/zscaler/bin/zstunnel",
        ]
    )


def _did_daemon_stop_correctly() -> bool:
    return _are_processes_not_running(
        patterns=[
            "/opt/zscaler/bin/zsaservice",
            "/opt/zscaler/bin/zstunnel",
        ]
    )


def _was_daemon_disabled_correctly(service: str) -> bool:
    return _is_systemd_unit_disabled(unit_name=service)


def _run_as_sudo(cmd: list[str]) -> None:
    logger.debug(f"executing as root cmd='{' '.join(cmd)}'")
    subprocess.run(
        args=["sudo", *cmd],
    )
    logger.debug("waiting")


def _run_as_user(cmd: list[str]) -> None:
    logger.debug(f"executing as user cmd='{' '.join(cmd)}'")
    subprocess.run(cmd)


def _enable_systemd_service_as_root(*, service: str) -> None:
    _run_as_sudo(cmd=["systemctl", "enable", service])


def _start_systemd_service_as_root(*, service: str) -> None:
    _run_as_sudo(cmd=["systemctl", "start", service])


def _stop_systemd_service_as_root(*, service: str) -> None:
    _run_as_sudo(cmd=["systemctl", "stop", service])


def _disable_systemd_service_as_root(*, service: str) -> None:
    _run_as_sudo(cmd=["systemctl", "disable", service])


def _start_systemd_service_as_user(service: str) -> None:
    _run_as_user(cmd=["systemctl", "--user", "start", service])


def _stop_systemd_service_as_user(service: str) -> None:
    _run_as_user(cmd=["systemctl", "--user", "stop", service])


def start_zscaler() -> None:
    gui_service = "ZSTray.service"
    daemon_service = "zsaservice.service"

    logger.info(f"enabling {daemon_service!r} systemd service as root")
    _enable_systemd_service_as_root(service=daemon_service)
    if not _was_daemon_enabled_correctly(service=daemon_service):
        exit(f"failed to enable {daemon_service}")

    logger.info(f"starting {daemon_service!r} systemd service as root")
    _start_systemd_service_as_root(service=daemon_service)
    if not _did_daemon_start_correctly():
        exit(f"failed to start {daemon_service}")

    logger.info(f"enabling {gui_service!r} systemd service as user")
    _start_systemd_service_as_user(service=gui_service)
    if not _did_gui_start_correctly():
        exit(f"failed to start {gui_service}")

    logger.info("zscaler correctly started")


def stop_zscaler() -> None:
    gui_service = "ZSTray.service"
    daemon_service = "zsaservice.service"

    _stop_systemd_service_as_user(service=gui_service)
    if not _did_gui_stop_correctly():
        exit(f"failed to stop {gui_service}")

    _stop_systemd_service_as_root(service=daemon_service)
    if not _did_daemon_stop_correctly():
        exit(f"failed to stop {daemon_service}")

    _disable_systemd_service_as_root(service=daemon_service)
    if not _was_daemon_disabled_correctly(service=daemon_service):
        exit(f"failed to disable {daemon_service}")

    logger.info("zscaler correctly stopped")


class ZScalerVpnStatus(enum.Enum):
    all_processes_running = "all_processes_running"
    some_processes_running = "some_processes_running"
    no_processes_running = "no_processes_running"


def is_zscaler_running() -> ZScalerVpnStatus:
    binaries = [
        "/opt/zscaler/bin/ZSTray",
        "/opt/zscaler/bin/zsaservice",
        "/opt/zscaler/bin/zstunnel",
    ]
    are_running = set(map(_is_process_running, binaries))
    import os

    os.environ["PYTHONBREAKPOINT"] = "pdb.set_trace"
    if are_running == {True}:
        return ZScalerVpnStatus.all_processes_running
    elif are_running == {False}:
        return ZScalerVpnStatus.no_processes_running
    elif are_running == {True, False}:
        return ZScalerVpnStatus.some_processes_running
    else:
        raise NotImplementedError(f"unsupported scenario: {are_running=}")


class UnsupportedScenario(Exception): ...


Action: TypeAlias = Literal["nothing-to-reconcile", "shutdown", "startup"]


def decide_action(current: ZScalerVpnStatus, desired: ZScalerVpnStatus) -> Action:

    if current.value == desired.value:
        return "nothing-to-reconcile"

    if desired == ZScalerVpnStatus.all_processes_running and current in (
        ZScalerVpnStatus.no_processes_running,
        ZScalerVpnStatus.some_processes_running,
    ):
        return "startup"
    elif desired == ZScalerVpnStatus.no_processes_running and current in (
        ZScalerVpnStatus.all_processes_running,
        ZScalerVpnStatus.some_processes_running,
    ):
        return "shutdown"
    else:
        raise UnsupportedScenario(
            f"unable to determine the action to take:\ncurrent: {current.value}\ndesired: {desired.value}"
        )


class InternetSecurityStatus(enum.Enum):
    on = "on"
    off = "off"
    unknown = "unknown"


def is_internet_security_on() -> InternetSecurityStatus:
    DB_PATH = Path("~/.Zscaler/DB/ZscalerApp.db").expanduser()
    if not DB_PATH.exists():
        logger.warning(f"ZScaler DB not found at '{DB_PATH}'")
        return InternetSecurityStatus.unknown

    def _parse(event: dict[str, str]) -> dict[str, str]:
        time = event["Time"]
        t = datetime.datetime.strptime(time, "%a, %b %d %Y %H:%M:%S %p")
        event["t"] = t.isoformat()
        return event

    def _dict_factory(cursor: sqlite3.Cursor, row: tuple) -> dict:
        return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}

    with sqlite3.connect(DB_PATH) as conn:
        _prefix = "Internet Security"
        conn.row_factory = _dict_factory

        cur = conn.cursor()
        cur.execute(
            textwrap.dedent(
                f"""
                SELECT
                    Time,
                    NotificationName
                FROM ZAppNotifications
                WHERE NotificationName LIKE '{_prefix} %'
                """
            )
        )
        events = cur.fetchall()
        if not events:
            logger.warning(
                f"no notifications found in ZScaler DB ({DB_PATH}) that"
                f" start with {_prefix!r}"
            )
            return InternetSecurityStatus.unknown

        parsed = sorted(map(_parse, events), key=lambda x: x["t"])
        last_event = parsed[-1]

        logger.info(f"last event found in DB: {json.dumps(last_event)!r}")

        name = last_event["NotificationName"]
        match name:
            case "Internet Security Up":
                return InternetSecurityStatus.on
            case "Internet Security Disabled":
                return InternetSecurityStatus.on
            case "Internet Security Enabled":
                return InternetSecurityStatus.on
            case "Internet Security On":
                return InternetSecurityStatus.on
            case "Internet Security Off":
                return InternetSecurityStatus.off
            case _:
                raise UnsupportedScenario(f"unsupported notification name: {name!r}")


Process: TypeAlias = str


def _get_active_processes() -> list[Process]:
    proc = subprocess.run(["ps", "aux"], text=True, capture_output=True)
    stdout = proc.stdout.splitlines()

    processes: list[Process] = set()
    for process in stdout[1:]:
        command = process.split(maxsplit=10)[-1]
        if command.startswith(("[", "-")):
            continue
        try:
            binary, _ = command.split(maxsplit=1)
        except ValueError:
            binary = command
        processes.add(binary)

    return processes


def in_a_call() -> bool:
    for binary in _get_active_processes():
        if binary.endswith("zoom"):
            return True
    return False
