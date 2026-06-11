#!/usr/bin/env python3
"""Run a command with a timeout while streaming output and saving a full log."""

from __future__ import annotations

import argparse
import os
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, required=True)
    parser.add_argument("--log", required=True)
    parser.add_argument("cmd", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.cmd and args.cmd[0] == "--":
        args.cmd = args.cmd[1:]
    if not args.cmd:
        parser.error("missing command")
    return args


def terminate_process_group(proc: subprocess.Popen[str]) -> None:
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    deadline = time.monotonic() + 5
    while proc.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    if proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def main() -> int:
    args = parse_args()
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.monotonic()
    proc = subprocess.Popen(
        args.cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )

    timed_out = False
    with log_path.open("w", encoding="utf-8") as log:
        assert proc.stdout is not None
        selector = selectors.DefaultSelector()
        selector.register(proc.stdout, selectors.EVENT_READ)
        while True:
            for key, _ in selector.select(timeout=0.2):
                line = key.fileobj.readline()
                if line:
                    sys.stdout.write(line)
                    sys.stdout.flush()
                    log.write(line)
                    log.flush()

            if proc.poll() is not None:
                break

            if time.monotonic() - start > args.timeout:
                timed_out = True
                message = f"\n[watchdog] Command timed out after {args.timeout:.0f}s\n"
                sys.stdout.write(message)
                sys.stdout.flush()
                log.write(message)
                log.flush()
                terminate_process_group(proc)
                break

        for line in proc.stdout:
            sys.stdout.write(line)
            log.write(line)
        selector.close()

    if timed_out:
        return 124
    return proc.returncode if proc.returncode is not None else 1


if __name__ == "__main__":
    raise SystemExit(main())
