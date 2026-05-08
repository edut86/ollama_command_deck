"""Command-line entrypoint for local Ollama tools."""

from __future__ import annotations

import argparse
import json
import sys

from .monitoring import (
    glances_all,
    glances_plugin,
    mqtt_ssh_snapshot,
    netdata_chart,
    netdata_info,
    prometheus_query,
    prometheus_query_range,
)
from .ollama_api import list_models
from .safety import UnsafeCommandError
from .shell_tools import run_local_command
from .ssh_tools import parse_ssh_config, run_ssh_command, ssh_config_status
from .time_tools import current_time
from .web_search import search_web


def main() -> int:
    parser = argparse.ArgumentParser(prog="ollama-tools")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("models")

    now = sub.add_parser("time")
    now.add_argument("--tz", help="IANA timezone, e.g. America/New_York")

    local = sub.add_parser("run-local")
    local.add_argument("shell_command")
    local.add_argument("--cwd")
    local.add_argument("--timeout", type=int, default=60)

    sub.add_parser("ssh-hosts")

    remote = sub.add_parser("run-ssh")
    remote.add_argument("host")
    remote.add_argument("shell_command")
    remote.add_argument("--timeout", type=int, default=60)

    web = sub.add_parser("search")
    web.add_argument("query")
    web.add_argument("--count", type=int, default=5)

    mqtt = sub.add_parser("mqtt-snapshot")
    mqtt.add_argument("host")
    mqtt.add_argument("--seconds", type=int, default=30)

    nd_info = sub.add_parser("netdata-info")
    nd_info.add_argument("host")

    nd_chart = sub.add_parser("netdata-chart")
    nd_chart.add_argument("host")
    nd_chart.add_argument("--chart", default="system.net")
    nd_chart.add_argument("--seconds", type=int, default=30)
    nd_chart.add_argument("--points", type=int, default=30)

    prom = sub.add_parser("prom-query")
    prom.add_argument("query")

    prom_range = sub.add_parser("prom-range")
    prom_range.add_argument("query")
    prom_range.add_argument("--seconds", type=int, default=300)
    prom_range.add_argument("--step", default="15s")

    glance = sub.add_parser("glances")
    glance.add_argument("host")
    glance.add_argument("--plugin")

    args = parser.parse_args()

    try:
        if args.command == "models":
            print(json.dumps([model.__dict__ for model in list_models()], indent=2))
        elif args.command == "time":
            print(json.dumps(current_time(args.tz).__dict__, indent=2))
        elif args.command == "run-local":
            result = run_local_command(args.shell_command, cwd=args.cwd, timeout=args.timeout)
            print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            return result.returncode
        elif args.command == "ssh-hosts":
            hosts = parse_ssh_config()
            print(json.dumps({"hosts": [host.__dict__ for host in hosts], "config": ssh_config_status().__dict__}, indent=2))
        elif args.command == "run-ssh":
            result = run_ssh_command(args.host, args.shell_command, timeout=args.timeout)
            print(result.stdout, end="")
            if result.stderr:
                print(result.stderr, end="", file=sys.stderr)
            return result.returncode
        elif args.command == "search":
            print(json.dumps([item.__dict__ for item in search_web(args.query, args.count)], indent=2))
        elif args.command == "mqtt-snapshot":
            print(json.dumps(mqtt_ssh_snapshot(args.host, seconds=args.seconds), indent=2))
        elif args.command == "netdata-info":
            print(json.dumps(netdata_info(args.host), indent=2))
        elif args.command == "netdata-chart":
            print(json.dumps(netdata_chart(args.host, chart=args.chart, seconds=args.seconds, points=args.points), indent=2))
        elif args.command == "prom-query":
            print(json.dumps(prometheus_query(args.query), indent=2))
        elif args.command == "prom-range":
            print(json.dumps(prometheus_query_range(args.query, seconds=args.seconds, step=args.step), indent=2))
        elif args.command == "glances":
            data = glances_plugin(args.host, args.plugin) if args.plugin else glances_all(args.host)
            print(json.dumps(data, indent=2))
    except (UnsafeCommandError, ValueError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
