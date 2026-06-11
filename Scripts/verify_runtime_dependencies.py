#!/usr/bin/env python3
"""
Verify that the vendored Python runtime matches runtime-requirements-lock.txt.

This intentionally checks Sources/Marcedit/python_site directly rather than the
developer environment so CI catches drift in the actual bundled app runtime.
"""

from __future__ import annotations

import argparse
import base64
import csv
import hashlib
from email.parser import Parser
import plistlib
from pathlib import Path
import stat
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SITE = PROJECT_ROOT / "Sources" / "Marcedit" / "python_site"
DEFAULT_LOCK = PROJECT_ROOT / "runtime-requirements-lock.txt"
DEFAULT_FRAMEWORK = PROJECT_ROOT / "Sources" / "Marcedit" / "Frameworks" / "Python.framework"
REQUIRED_CPYTHON_VERSION = "3.11.15"
ALLOWED_UNTRACKED_DIRS = {"editor_pkg"}


def canonical_name(name: str) -> str:
    return name.replace("_", "-").lower()


def read_lock(path: Path) -> dict[str, str]:
    expected: dict[str, str] = {}
    for line_number, raw_line in enumerate(path.read_text().splitlines(), start=1):
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        if "==" not in line:
            raise ValueError(f"{path}:{line_number}: expected pinned requirement with ==")
        name, version = line.split("==", 1)
        expected[canonical_name(name.strip())] = version.strip()
    return expected


def read_vendored(site: Path) -> tuple[dict[str, str], list[Path]]:
    actual: dict[str, str] = {}
    dist_infos: list[Path] = []
    for dist_info in sorted(site.glob("*.dist-info")):
        dist_infos.append(dist_info)
        metadata = dist_info / "METADATA"
        if not metadata.exists():
            raise ValueError(f"Missing METADATA in {dist_info}")
        parsed = Parser().parsestr(metadata.read_text(errors="replace"))
        name = parsed.get("Name")
        version = parsed.get("Version")
        if not name or not version:
            raise ValueError(f"Missing Name/Version in {metadata}")
        actual[canonical_name(name)] = version
    return actual, dist_infos


def format_packages(packages: dict[str, str]) -> str:
    return ", ".join(f"{name}=={version}" for name, version in sorted(packages.items()))


def verify(site: Path, lock: Path, framework: Path, required_arch: str) -> list[str]:
    expected = read_lock(lock)
    actual, dist_infos = read_vendored(site)
    errors: list[str] = []

    missing = {name: version for name, version in expected.items() if name not in actual}
    extra = {name: version for name, version in actual.items() if name not in expected}
    mismatched = {
        name: (expected[name], actual[name])
        for name in expected.keys() & actual.keys()
        if expected[name] != actual[name]
    }

    if missing:
        errors.append(f"Missing vendored packages: {format_packages(missing)}")
    if extra:
        errors.append(f"Unexpected vendored packages: {format_packages(extra)}")
    if mismatched:
        rendered = ", ".join(
            f"{name}: lock {locked} != vendored {vendored}"
            for name, (locked, vendored) in sorted(mismatched.items())
        )
        errors.append(f"Version drift: {rendered}")
    errors.extend(verify_records(site, dist_infos))
    errors.extend(verify_native_architecture(site, required_arch))
    errors.extend(verify_python_framework(framework, required_arch))
    return errors


def verify_python_framework(framework: Path, required_arch: str) -> list[str]:
    errors: list[str] = []
    version_root = framework / "Versions" / "3.11"
    info_plist = version_root / "Resources" / "Info.plist"
    python_binary = version_root / "Python"
    if not info_plist.exists():
        return [f"Missing Python framework Info.plist: {info_plist}"]
    if not python_binary.exists():
        return [f"Missing Python framework binary: {python_binary}"]

    with info_plist.open("rb") as handle:
        info = plistlib.load(handle)
    version = info.get("CFBundleVersion")
    if version != REQUIRED_CPYTHON_VERSION:
        errors.append(f"Bundled CPython version is {version}, expected {REQUIRED_CPYTHON_VERSION}")

    for path in enumerate_macho_files(version_root):
        errors.extend(verify_macho_file_architecture(path, framework, required_arch))
        errors.extend(verify_no_homebrew_load_commands(path, framework))
    errors.extend(verify_no_homebrew_executable_scripts(version_root, framework))
    errors.extend(verify_no_homebrew_startup_hooks(version_root, framework))
    return errors


def enumerate_macho_files(root: Path) -> list[Path]:
    macho_files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        result = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True, check=False)
        if result.returncode == 0 and "Mach-O" in result.stdout:
            macho_files.append(path)
    return macho_files


def verify_no_homebrew_load_commands(path: Path, root: Path) -> list[str]:
    errors: list[str] = []
    for args, label in ((["otool", "-L", str(path)], "linked libraries"), (["otool", "-l", str(path)], "load commands")):
        result = subprocess.run(args, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            errors.append(f"Could not inspect {label} for {path.relative_to(root)}: {result.stderr.strip()}")
            continue
        for line in result.stdout.splitlines():
            if "/opt/homebrew" in line:
                errors.append(f"Python framework file has Homebrew reference in {label}: {path.relative_to(root)} -> {line.strip()}")
    return errors


def verify_no_homebrew_executable_scripts(version_root: Path, framework: Path) -> list[str]:
    errors: list[str] = []
    bin_root = version_root / "bin"
    if not bin_root.exists():
        return errors
    for path in sorted(bin_root.rglob("*")):
        if not path.is_file() or not (path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)):
            continue
        result = subprocess.run(["file", "-b", str(path)], capture_output=True, text=True, check=False)
        if result.returncode != 0 or "Mach-O" in result.stdout:
            continue
        first_line = path.read_text(errors="replace").splitlines()[0:1]
        if first_line and "/opt/homebrew" in first_line[0]:
            errors.append(f"Executable script has Homebrew shebang: {path.relative_to(framework)} -> {first_line[0]}")
    return errors


def verify_no_homebrew_startup_hooks(version_root: Path, framework: Path) -> list[str]:
    errors: list[str] = []
    stdlib = version_root / "lib" / "python3.11"
    candidates = [stdlib / "sitecustomize.py", stdlib / "usercustomize.py"]
    candidates.extend(sorted(stdlib.glob("*.pth")))
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(errors="replace")
        if "/opt/homebrew" in text:
            errors.append(f"Python startup hook references Homebrew: {path.relative_to(framework)}")
    return errors


def verify_records(site: Path, dist_infos: list[Path]) -> list[str]:
    errors: list[str] = []
    tracked_paths: set[Path] = set()
    site_root = site.resolve()
    for dist_info in dist_infos:
        record = dist_info / "RECORD"
        if not record.exists():
            errors.append(f"Missing wheel RECORD: {record.relative_to(site)}")
            continue
        with record.open(newline="") as handle:
            for row in csv.reader(handle):
                if len(row) < 3:
                    errors.append(f"Malformed RECORD row in {record.relative_to(site)}: {row!r}")
                    continue
                relative_path, digest, _size = row[:3]
                file_path = site / relative_path
                try:
                    resolved = file_path.resolve()
                    resolved.relative_to(site_root)
                except ValueError:
                    continue
                tracked_paths.add(resolved)
                if not digest:
                    continue
                try:
                    algorithm, encoded = digest.split("=", 1)
                except ValueError:
                    errors.append(f"Malformed RECORD digest for {relative_path}: {digest}")
                    continue
                if algorithm != "sha256":
                    errors.append(f"Unsupported RECORD digest algorithm for {relative_path}: {algorithm}")
                    continue
                if not file_path.exists():
                    errors.append(f"RECORD file missing: {relative_path}")
                    continue
                actual = hashlib.sha256(file_path.read_bytes()).digest()
                expected = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
                if actual != expected:
                    errors.append(f"RECORD hash mismatch: {relative_path}")
    errors.extend(verify_no_untracked_files(site, tracked_paths))
    return errors


def verify_no_untracked_files(site: Path, tracked_paths: set[Path]) -> list[str]:
    errors: list[str] = []
    site_root = site.resolve()
    for path in sorted(site.rglob("*")):
        if not path.is_file():
            continue
        relative = path.resolve().relative_to(site_root)
        if relative.parts and relative.parts[0] in ALLOWED_UNTRACKED_DIRS:
            continue
        if path.resolve() not in tracked_paths:
            errors.append(f"Untracked vendored runtime file: {relative}")
    return errors


def verify_native_architecture(site: Path, required_arch: str) -> list[str]:
    errors: list[str] = []
    if not required_arch:
        return errors
    for path in sorted(site.rglob("*")):
        if not path.is_file() or path.suffix not in {".so", ".dylib"}:
            continue
        errors.extend(verify_macho_file_architecture(path, site, required_arch))
    return errors


def verify_macho_file_architecture(path: Path, root: Path, required_arch: str) -> list[str]:
    if not required_arch:
        return []
    result = subprocess.run(["lipo", "-archs", str(path)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        return [f"Could not inspect Mach-O architectures for {path.relative_to(root)}: {result.stderr.strip()}"]
    archs = set(result.stdout.split())
    if required_arch not in archs:
        return [
            f"Native runtime file missing required {required_arch} architecture: "
            f"{path.relative_to(root)} has {sorted(archs)}"
        ]
    return []


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", type=Path, default=DEFAULT_SITE)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK)
    parser.add_argument("--framework", type=Path, default=DEFAULT_FRAMEWORK)
    parser.add_argument(
        "--required-arch",
        default="arm64",
        help="Required architecture for vendored native .so/.dylib files; use empty string to disable",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    errors = verify(args.site, args.lock, args.framework, args.required_arch)
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("Vendored runtime dependencies match runtime-requirements-lock.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
