# ZSCaler utilities

## Install

Install the guardian daemon and `vpn` CLI:

```shell
bin/install
```

- guardian daemon: systemd service that checks if the Internet Security is ON regularly.
- `vpn` CLI: starts/stop ZSCaler services (including UI and background systemd services).

## Usage

Start VPN:
```shell
vpn up
```

Stop VPN:
```shell
vpn down
```

## Configuration

The configuration lives in `~/.config/zscaler-manager/config.json`:

```json
{
  "wait_between_checks_in_seconds": 5,
  "notification_bin": "~/path/to/my/notification/script"
}
```

## Guardian daemon notifications

When the guardian daemon detects that ZSCaler's _Internet Security_ is on, it will notify by executing the path specified in config. The executable will receive a single string argument with a notification message.
