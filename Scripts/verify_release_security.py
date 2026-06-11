#!/usr/bin/env python3
"""
Verify release security posture for Marcedit public-beta builds.

This script has two modes:
  - source config mode: always checks project release settings and entitlements.
  - app bundle mode: with --app, additionally inspects a built .app signature.
"""

from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROJECT_FILE = PROJECT_ROOT / "MarceditApp.xcodeproj" / "project.pbxproj"
ENTITLEMENTS_FILE = PROJECT_ROOT / "Sources" / "Marcedit" / "Marcedit.entitlements"

REQUIRED_ENTITLEMENTS = {
    "com.apple.security.app-sandbox": True,
    "com.apple.security.files.user-selected.read-write": True,
}

FORBIDDEN_ENTITLEMENTS = {
    "com.apple.security.network.client",
    "com.apple.security.network.server",
    "com.apple.security.files.downloads.read-write",
    "com.apple.security.files.home-relative-path.read-write",
    "com.apple.security.files.absolute-path.read-write",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_entitlements() -> dict:
    if not ENTITLEMENTS_FILE.exists():
        fail(f"Missing entitlements file: {ENTITLEMENTS_FILE.relative_to(PROJECT_ROOT)}")
    with ENTITLEMENTS_FILE.open("rb") as handle:
        data = plistlib.load(handle)
    if not isinstance(data, dict):
        fail("Entitlements plist is not a dictionary")
    return data


def verify_entitlements(data: dict) -> None:
    for key, expected in REQUIRED_ENTITLEMENTS.items():
        if data.get(key) is not expected:
            fail(f"Entitlement {key} must be {expected!r}")
    for key in FORBIDDEN_ENTITLEMENTS:
        if data.get(key):
            fail(f"Forbidden entitlement is enabled: {key}")


def verify_project_settings() -> None:
    text = PROJECT_FILE.read_text()
    target_block = _extract_named_block(text, "TARGET001 /* Marcedit */")
    if "buildConfigurationList = CONFIGLIST001;" not in target_block:
        fail("Marcedit target does not use CONFIGLIST001")
    config_list = _extract_named_block(
        text,
        'CONFIGLIST001 /* Build configuration list for PBXNativeTarget "Marcedit" */',
    )
    if "APPREL001 /* Release */" not in config_list:
        fail("Marcedit target configuration list does not include APPREL001")

    release_section = _extract_named_block(text, "APPREL001 /* Release */")
    required = [
        "CODE_SIGN_ENTITLEMENTS = Sources/Marcedit/Marcedit.entitlements;",
        "ENABLE_HARDENED_RUNTIME = YES;",
    ]
    for needle in required:
        if needle not in release_section:
            fail(f"Release project setting missing: {needle}")


def _extract_named_block(text: str, marker: str) -> str:
    try:
        start = text.index(marker)
    except ValueError:
        fail(f"Could not find project block marker: {marker}")

    brace_start = text.find("{", start)
    if brace_start == -1:
        fail(f"Could not find opening brace for project block marker: {marker}")

    depth = 0
    for index in range(brace_start, len(text)):
        char = text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1]
    fail(f"Could not find closing brace for project block marker: {marker}")


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, check=False)


def verify_app_bundle(app_path: Path, require_developer_id: bool) -> None:
    if not app_path.exists():
        fail(f"App bundle does not exist: {app_path}")

    signature = run(["codesign", "-dvvv", "--entitlements", ":-", str(app_path)])
    if signature.returncode != 0:
        fail(f"codesign inspection failed: {signature.stderr.strip()}")

    combined = signature.stdout + signature.stderr
    if not has_hardened_runtime(combined):
        fail("Built app is missing hardened runtime")
    verify_macho_architecture(app_path / "Contents" / "MacOS" / "Marcedit", "arm64")

    try:
        entitlements = plistlib.loads(signature.stdout.encode("utf-8"))
    except Exception as exc:
        fail(f"Could not parse signed entitlements: {exc}")
    verify_entitlements(entitlements)

    if require_developer_id and "Authority=Developer ID Application:" not in combined:
        fail("Built app is not signed with a Developer ID Application certificate")

    verify = run(["codesign", "--verify", "--strict", "--verbose=2", str(app_path)])
    if verify.returncode != 0:
        fail(f"codesign verification failed: {verify.stderr.strip()}")

    verify_nested_code(app_path, require_developer_id)


def has_hardened_runtime(codesign_output: str) -> bool:
    for line in codesign_output.splitlines():
        if line.startswith("CodeDirectory ") and "flags=" in line:
            flags = line.split("flags=", 1)[1]
            return "runtime" in flags.lower()
    return False


def iter_nested_code(app_path: Path) -> list[Path]:
    nested: list[Path] = []
    macos_dir = app_path / "Contents" / "MacOS"

    for path in app_path.rglob("*"):
        if path.is_dir() and path.suffix == ".framework":
            nested.append(path)
            continue
        if not path.is_file():
            continue
        if path == macos_dir / "Marcedit":
            continue
        if path.suffix not in {".dylib", ".so"}:
            continue
        file_result = run(["file", "-b", str(path)])
        if file_result.returncode != 0:
            fail(f"Could not inspect nested code file type: {path}")
        if "Mach-O" in file_result.stdout:
            nested.append(path)
    return nested


def verify_nested_code(app_path: Path, require_developer_id: bool) -> None:
    for path in iter_nested_code(app_path):
        verify = run(["codesign", "--verify", "--strict", "--verbose=2", str(path)])
        if verify.returncode != 0:
            rel_path = path.relative_to(app_path)
            fail(f"Nested code signature invalid for {rel_path}: {verify.stderr.strip()}")

        if require_developer_id:
            signature = run(["codesign", "-dvvv", str(path)])
            if signature.returncode != 0:
                rel_path = path.relative_to(app_path)
                fail(f"Nested code signature inspection failed for {rel_path}: {signature.stderr.strip()}")
            if "Authority=Developer ID Application:" not in signature.stderr:
                rel_path = path.relative_to(app_path)
                fail(f"Nested code is not Developer ID signed: {rel_path}")


def verify_macho_architecture(path: Path, required_arch: str) -> None:
    result = run(["lipo", "-archs", str(path)])
    if result.returncode != 0:
        fail(f"Could not inspect Mach-O architectures for {path}: {result.stderr.strip()}")
    archs = set(result.stdout.split())
    if required_arch not in archs:
        fail(f"Mach-O file missing required {required_arch} architecture: {path} has {sorted(archs)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", type=Path, help="Optional built Marcedit.app to inspect")
    parser.add_argument(
        "--require-developer-id",
        action="store_true",
        help="Require Developer ID Application authority when --app is provided",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.require_developer_id and args.app is None:
        fail("--require-developer-id requires --app so the signed artifact can be inspected")
    entitlements = load_entitlements()
    verify_entitlements(entitlements)
    verify_project_settings()
    if args.app is not None:
        verify_app_bundle(args.app, args.require_developer_id)
    print("Release security verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
