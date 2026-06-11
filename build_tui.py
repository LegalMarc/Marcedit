#!/usr/bin/env python3
"""
Marcedit Build & Test TUI
A text-based interface for building and testing the Marcedit PDF Editor.
"""

import os
import subprocess
import sys
import shutil
import time
from pathlib import Path
from datetime import datetime

# ANSI color codes
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    MAGENTA = '\033[95m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'

# Configuration
PROJECT_ROOT = Path(__file__).parent.resolve()
BUILD_DIR = PROJECT_ROOT / "ignored-resources"
APP_NAME = "Marcedit"

def clear_screen():
    """Clear the terminal screen."""
    os.system('clear' if os.name != 'nt' else 'cls')

def print_header():
    """Print the TUI header."""
    clear_screen()
    print(f"{Colors.CYAN}{Colors.BOLD}")
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║                  MARCEDIT BUILD & TEST TUI                   ║")
    print("║             PDF Line Editor (Modern Transformation)          ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print(f"{Colors.ENDC}")
    print(f"{Colors.DIM}Project: {PROJECT_ROOT}{Colors.ENDC}")
    print(f"{Colors.DIM}Build Output: {BUILD_DIR}{Colors.ENDC}")
    print()

def print_menu():
    """Print the main menu."""
    print(f"{Colors.BOLD}Available Actions:{Colors.ENDC}")
    print()
    print(f"{Colors.BOLD}Build:{Colors.ENDC}")
    print(f"  {Colors.GREEN}1{Colors.ENDC}) Build Debug")
    print(f"  {Colors.GREEN}2{Colors.ENDC}) Build Release")
    print(f"  {Colors.GREEN}3{Colors.ENDC}) Build & Run (Debug)")
    print(f"  {Colors.GREEN}4{Colors.ENDC}) Run App")
    print(f"  {Colors.GREEN}5{Colors.ENDC}) Clean Build Directory")
    print(f"  {Colors.GREEN}6{Colors.ENDC}) Show Build Info")
    print()
    print(f"{Colors.BOLD}Swift Testing:{Colors.ENDC}")
    print(f"  {Colors.CYAN}7{Colors.ENDC}) Run SwiftPM Tests")
    print()
    print(f"{Colors.BOLD}Python Unit Tests:{Colors.ENDC}")
    print(f"  {Colors.BLUE}8{Colors.ENDC}) Run pytest (All Tests)")
    print(f"  {Colors.BLUE}9{Colors.ENDC}) Run pytest (Core Tests Only)")
    print(f"  {Colors.BLUE}10{Colors.ENDC}) Run pytest (Reflow Tests Only)")
    print(f"  {Colors.BLUE}11{Colors.ENDC}) Run pytest with Coverage")
    print(f"  {Colors.BLUE}12{Colors.ENDC}) Run Pipeline Verification")
    print()
    print(f"{Colors.BOLD}App Stability Tests:{Colors.ENDC}")
    print(f"  {Colors.MAGENTA}13{Colors.ENDC}) Run Automated Crash Test")
    print(f"  {Colors.MAGENTA}14{Colors.ENDC}) Run UI Interaction Test")
    print(f"  {Colors.MAGENTA}15{Colors.ENDC}) Run Full Stability Suite")
    print(f"  {Colors.RED}16{Colors.ENDC}) Reproduce Text Selection Crash (Python)")
    print(f"  {Colors.RED}17{Colors.ENDC}) Reproduce Text Selection Crash (XCTest)")
    print(f"  {Colors.RED}18{Colors.ENDC}) Run Both Crash Tests")
    print()
    print(f"{Colors.BOLD}Architecture Tests:{Colors.ENDC}")
    print(f"  {Colors.BLUE}19{Colors.ENDC}) Run Redaction Cleanup Tests")
    print()
    print(f"{Colors.BOLD}XCUITests (End-to-End):{Colors.ENDC}")
    print(f"  {Colors.CYAN}20{Colors.ENDC}) Generate UI Test Corpus (PyMuPDF PDFs)")
    print(f"  {Colors.CYAN}21{Colors.ENDC}) Run XCUITests (Full UI Test Suite)")
    print()
    print(f"  {Colors.YELLOW}q{Colors.ENDC}) Quit")
    print()

def ensure_build_dir():
    """Ensure the build directory exists."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create a .gitkeep to ensure the directory structure is maintained
    gitkeep = BUILD_DIR / ".gitkeep"
    if not gitkeep.exists():
        gitkeep.touch()

def run_command(cmd: list, description: str, capture_output: bool = False, cwd=PROJECT_ROOT) -> tuple[bool, str]:
    """Run a command and display its progress."""
    print(f"{Colors.BLUE}▶ {description}...{Colors.ENDC}")
    print(f"{Colors.DIM}  Command: {' '.join(cmd)}{Colors.ENDC}")
    print()
    
    try:
        if capture_output:
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
            success = result.returncode == 0
            output = result.stdout + result.stderr
        else:
            result = subprocess.run(cmd, cwd=cwd)
            success = result.returncode == 0
            output = ""
        
        if success:
            print(f"{Colors.GREEN}✓ {description} completed successfully!{Colors.ENDC}")
        else:
            print(f"{Colors.RED}✗ {description} failed!{Colors.ENDC}")
            if capture_output and output:
                print(f"{Colors.DIM}{output[-2000:]}{Colors.ENDC}")  # Last 2000 chars
        
        return success, output
    except Exception as e:
        print(f"{Colors.RED}✗ Error: {e}{Colors.ENDC}")
        return False, str(e)

def build(configuration: str = "Debug") -> bool:
    """Build the app with SwiftPM."""
    import json
    
    ensure_build_dir()
    start_time = time.time()
    
    # --- VERSION MANAGEMENT ---
    # Load and increment version from version.json
    # Format: major.minor.patch (patch auto-increments on each build)
    version_file = PROJECT_ROOT / "version.json"
    if version_file.exists():
        with open(version_file) as f:
            version_data = json.load(f)
    else:
        version_data = {"major": 0, "minor": 5, "patch": 0}
    
    # Increment patch number for each build
    version_data["patch"] = version_data.get("patch", 0) + 1
    
    # Save updated version
    with open(version_file, "w") as f:
        json.dump(version_data, f, indent=2)
    
    # Format: 0.5.15 (not "0.5 (15)")
    version_string = f"{version_data['major']}.{version_data['minor']}.{version_data['patch']}"
    build_number = str(version_data["patch"])  # App Store uses this as build number
    
    print(f"{Colors.CYAN}Version: {version_string}{Colors.ENDC}")
    print()
    # --- END VERSION MANAGEMENT ---
    
    print(f"{Colors.HEADER}Building {configuration} configuration with SwiftPM...{Colors.ENDC}")
    print()
    
    # Use swift build with default build path (.build) for faster incremental builds
    config_value = "debug" if configuration == "Debug" else "release"
    
    cmd = [
        "swift", "build",
        "--configuration", config_value,
    ]
    
    success, _ = run_command(cmd, f"Building {configuration}")
    
    if success:
        # Create App Bundle Structure in ignored-resources
        app_bundle = BUILD_DIR / "Marcedit.app"
        contents_dir = app_bundle / "Contents"
        macos_dir = contents_dir / "MacOS"
        resources_dir = contents_dir / "Resources"
        
        if app_bundle.exists():
            shutil.rmtree(app_bundle)
            
        # Clean up legacy raw executable if present
        legacy_binary = BUILD_DIR / APP_NAME
        if legacy_binary.exists():
            legacy_binary.unlink()
            
        macos_dir.mkdir(parents=True)
        resources_dir.mkdir(parents=True)
        
        # Copy binary from default .build location
        build_path = PROJECT_ROOT / ".build"
        binary_path = build_path / config_value / APP_NAME
        dest_binary = macos_dir / APP_NAME
        
        if binary_path.exists():
            shutil.copy2(binary_path, dest_binary)
            
            # Copy resource bundle
            bundle_src = build_path / config_value / f"{APP_NAME}_{APP_NAME}.bundle"
            if bundle_src.exists():
                shutil.copytree(bundle_src, resources_dir / f"{APP_NAME}_{APP_NAME}.bundle", symlinks=True)
            
            # Copy bundled fonts to app bundle
            fonts_src = PROJECT_ROOT / "assets" / "fonts"
            if fonts_src.exists():
                fonts_dest = resources_dir / f"{APP_NAME}_{APP_NAME}.bundle" / "fonts"
                if fonts_dest.exists():
                    shutil.rmtree(fonts_dest)
                shutil.copytree(fonts_src, fonts_dest, ignore=shutil.ignore_patterns('*.zip', '*.tar.gz', '*.DS_Store'))
                print(f"{Colors.CYAN}Bundled fonts copied to app{Colors.ENDC}")
            
            # Compile Assets.xcassets to Assets.car (manually to ensure AppIcon is included)
            print(f"{Colors.HEADER}Compiling assets...{Colors.ENDC}")
            assets_src = PROJECT_ROOT / "Sources" / "Marcedit" / "Assets.xcassets"
            if assets_src.exists():
                try:
                    subprocess.run([
                        "xcrun", "actool",
                        str(assets_src),
                        "--compile", str(resources_dir),
                        "--platform", "macosx",
                        "--minimum-deployment-target", "14.0",
                        # Removed --app-icon to prevent Assets.car from claiming the icon
                        # "--app-icon", "AppIcon",
                        "--output-partial-info-plist", str(BUILD_DIR / "partial.plist")
                    ], check=True, capture_output=True)
                    print(f"{Colors.CYAN}Assets compiled to Assets.car{Colors.ENDC}")
                except subprocess.CalledProcessError as e:
                    print(f"{Colors.RED}Failed to compile assets: {e.stderr}{Colors.ENDC}")
            
            # Generate AppIcon.icns for Finder fallback
            print(f"{Colors.HEADER}Generating AppIcon.icns...{Colors.ENDC}")
            iconset_src = PROJECT_ROOT / "Sources" / "Marcedit" / "Assets.xcassets" / "AppIcon.appiconset"
            
            # Create a temporary .iconset directory structure expected by iconutil
            temp_iconset = BUILD_DIR / "AppIcon.iconset"
            if temp_iconset.exists():
                shutil.rmtree(temp_iconset)
            
            if iconset_src.exists():
                shutil.copytree(iconset_src, temp_iconset)
                
                # Remove Contents.json which iconutil might reject
                contents_json = temp_iconset / "Contents.json"
                if contents_json.exists():
                    contents_json.unlink()

                # Run iconutil
                icns_dest = resources_dir / "AppIcon.icns"
                try:
                    subprocess.run([
                        "iconutil", "-c", "icns",
                        "-o", str(icns_dest),
                        str(temp_iconset)
                    ], check=True, capture_output=True)
                    print(f"{Colors.CYAN}AppIcon.icns generated{Colors.ENDC}")
                except subprocess.CalledProcessError as e:
                     print(f"{Colors.RED}Failed to generate AppIcon.icns: {e.stderr}{Colors.ENDC}")
                
                # Clean up
                shutil.rmtree(temp_iconset)
            
            # Create Info.plist with dynamic version and all required keys
            info_plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>Marcedit</string>
    <key>CFBundleIdentifier</key>
    <string>com.marclaw.Marcedit</string>
    <key>CFBundleName</key>
    <string>Marcedit</string>
    <key>CFBundleDisplayName</key>
    <string>Marcedit</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>{version_string}</string>
    <key>CFBundleVersion</key>
    <string>{build_number}</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticTermination</key>
    <true/>
    <key>NSSupportsSuddenTermination</key>
    <true/>
    <key>NSRequiresAquaSystemAppearance</key>
    <false/>
    <key>NSPrincipalClass</key>
    <string>NSApplication</string>
    <key>NSHumanReadableCopyright</key>
    <string>Copyright © 2026. All rights reserved.</string>
</dict>
</plist>"""
            (contents_dir / "Info.plist").write_text(info_plist)
            
            # Sign all native libraries first (inside-out signing)
            print(f"{Colors.HEADER}Signing native libraries...{Colors.ENDC}")
            for pattern in ["**/*.dylib", "**/*.so", "**/*.framework"]:
                for lib_path in app_bundle.rglob(pattern):
                    if lib_path.is_file() or (lib_path.is_dir() and lib_path.suffix == ".framework"):
                        subprocess.run(
                            ["codesign", "--force", "--sign", "-", str(lib_path)],
                            capture_output=True
                        )
            
            # Sign the app bundle itself (no --deep since we signed libs individually)
            subprocess.run(["codesign", "--force", "--sign", "-", str(app_bundle)], capture_output=True)
            
            # Touch the app bundle to force Finder to refresh the icon
            subprocess.run(["touch", str(app_bundle)])
            
            elapsed = time.time() - start_time
            print(f"\n{Colors.GREEN}App Bundle ready at: {app_bundle}{Colors.ENDC}")
            print(f"{Colors.GREEN}Version {version_string}{Colors.ENDC}")
            print(f"{Colors.DIM}Build completed in {elapsed:.1f}s{Colors.ENDC}")
        else:
            print(f"\n{Colors.YELLOW}⚠ Binary not found at expected path: {binary_path}{Colors.ENDC}")
    
    return success

def run_app() -> bool:
    """Run the built app."""
    app_bundle = BUILD_DIR / "Marcedit.app"
    
    if not app_bundle.exists():
        print(f"{Colors.YELLOW}⚠ App not found at {app_bundle}{Colors.ENDC}")
        print(f"{Colors.YELLOW}  Building first...{Colors.ENDC}")
        print()
        if not build("Release"):
            return False
    
    print(f"{Colors.HEADER}Launching {APP_NAME}...{Colors.ENDC}")
    print()
    
    # Open the app bundle
    cmd = ["open", str(app_bundle)]
    
    try:
        subprocess.run(cmd)
        print(f"{Colors.GREEN}✓ App launched!{Colors.ENDC}")
        return True
    except Exception as e:
        print(f"{Colors.RED}✗ Failed to launch: {e}{Colors.ENDC}")
        return False

def clean_build_dir(interactive: bool = True) -> bool:
    """Clean the build directory."""
    print(f"{Colors.HEADER}Cleaning build directory...{Colors.ENDC}")
    print()
    
    if BUILD_DIR.exists():
        if interactive:
            # List what will be deleted
            items = list(BUILD_DIR.iterdir())
            preserved_items = {".gitkeep", "sample-files-marcedit"}

            if items:
                to_delete = [item for item in items if item.name not in preserved_items]
                to_preserve = [item for item in items if item.name in preserved_items and item.name != ".gitkeep"]

                if to_delete:
                    print(f"{Colors.DIM}Will remove:{Colors.ENDC}")
                    for item in to_delete:
                        print(f"  - {item.name}")

                if to_preserve:
                    print(f"{Colors.GREEN}Will preserve:{Colors.ENDC}")
                    for item in to_preserve:
                        print(f"  ✓ {item.name} {Colors.DIM}(test files){Colors.ENDC}")

                print()

                confirm = input(f"{Colors.YELLOW}Confirm deletion? (y/N): {Colors.ENDC}").strip().lower()
                if confirm != 'y':
                    print(f"{Colors.BLUE}Cancelled.{Colors.ENDC}")
                    return False
        
        # Actual Deletion
        # Preserve sample-files-marcedit directory
        preserved_items = {".gitkeep", "sample-files-marcedit"}

        for item in BUILD_DIR.iterdir():
            if item.name not in preserved_items:
                try:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                except Exception as e:
                    # Retry once for "Directory not empty" or similar race conditions
                    print(f"{Colors.YELLOW}  ⚠ Retry deletion for {item.name}: {e}{Colors.ENDC}")
                    time.sleep(0.5)
                    try:
                        if item.is_dir():
                            shutil.rmtree(item, ignore_errors=True)
                        else:
                            item.unlink(missing_ok=True)
                    except Exception as e2:
                        print(f"{Colors.RED}  ✗ Failed to delete {item.name}: {e2}{Colors.ENDC}")
                        return False
        
        print(f"{Colors.GREEN}✓ Build directory cleaned!{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.BLUE}Build directory doesn't exist yet.{Colors.ENDC}")
        return True

def run_tests() -> bool:
    """Run unit tests with SwiftPM."""
    print(f"{Colors.HEADER}Running SwiftPM tests...{Colors.ENDC}")
    print()
    
    cmd = ["swift", "test"]
    
    success, _ = run_command(cmd, "Running tests")
    return success

def run_pipeline_verification() -> bool:
    """Run Python end-to-end pipeline verification."""
    print(f"{Colors.HEADER}Running End-to-End Pipeline Verification...{Colors.ENDC}")
    print()

    python_cmd = None
    source_type = "System"

    # 1. Check for Bundled Python (Debug) - Most Accurate validation
    debug_bundle_python = BUILD_DIR / "Debug" / f"{APP_NAME}.app" / "Contents" / "Resources" / "python" / "bin" / "python3"
    if debug_bundle_python.exists():
        python_cmd = str(debug_bundle_python)
        source_type = "Bundled (Debug App)"

    # 2. Check for Bundled Python (Release)
    if not python_cmd:
        release_bundle_python = BUILD_DIR / "Release" / f"{APP_NAME}.app" / "Contents" / "Resources" / "python" / "bin" / "python3"
        if release_bundle_python.exists():
             python_cmd = str(release_bundle_python)
             source_type = "Bundled (Release App)"

    # 3. Fallback to Local Venv
    if not python_cmd:
        venv_python = PROJECT_ROOT / ".venv" / "bin" / "python3"
        if venv_python.exists():
            python_cmd = str(venv_python)
            source_type = "Local .venv"
            print(f"{Colors.YELLOW}⚠ Warning: App not built. Using local .venv which may not match App behavior.{Colors.ENDC}")

    # 4. Fallback to System
    if not python_cmd:
        python_cmd = "python3"
        print(f"{Colors.RED}⚠ Warning: Using system python3. Strongly recommend building app first.{Colors.ENDC}")

    print(f"{Colors.DIM}Using Python: {source_type}{Colors.ENDC}")
    print(f"{Colors.DIM}Path: {python_cmd}{Colors.ENDC}")

    test_script = PROJECT_ROOT / "tests" / "pipeline_test.py"

    cmd = [python_cmd, str(test_script)]

    # We pass Cwd as project URL
    success, _ = run_command(cmd, "Pipeline verification", cwd=PROJECT_ROOT)
    return success

def find_python_command() -> tuple[str, str]:
    """Find the best Python command to use for testing. Returns (python_cmd, source_type)."""
    python_cmd = None
    source_type = "System"

    # 1. Check for Bundled Python (Debug)
    debug_bundle_python = BUILD_DIR / "Debug" / f"{APP_NAME}.app" / "Contents" / "Resources" / "python" / "bin" / "python3"
    if debug_bundle_python.exists():
        python_cmd = str(debug_bundle_python)
        source_type = "Bundled (Debug App)"

    # 2. Check for Bundled Python (Release)
    if not python_cmd:
        release_bundle_python = BUILD_DIR / "Release" / f"{APP_NAME}.app" / "Contents" / "Resources" / "python" / "bin" / "python3"
        if release_bundle_python.exists():
             python_cmd = str(release_bundle_python)
             source_type = "Bundled (Release App)"

    # 3. Fallback to Local Venv
    if not python_cmd:
        venv_python = PROJECT_ROOT / ".venv" / "bin" / "python3"
        if venv_python.exists():
            python_cmd = str(venv_python)
            source_type = "Local .venv"

    # 4. Fallback to System
    if not python_cmd:
        python_cmd = "python3"
        source_type = "System"

    return python_cmd, source_type

def run_pytest(test_target: str = "all", coverage: bool = False) -> bool:
    """Run pytest tests.

    Args:
        test_target: 'all', 'core', or 'reflow'
        coverage: Whether to generate coverage report
    """
    python_cmd, source_type = find_python_command()

    # Build pytest command
    if test_target == "all":
        pytest_cmd = ["-m", "pytest", "tests/", "-v"]
        desc = "Running all pytest tests"
    elif test_target == "core":
        pytest_cmd = ["-m", "pytest", "tests/test_editor_core.py", "-v"]
        desc = "Running core tests"
    elif test_target == "reflow":
        pytest_cmd = ["-m", "pytest", "tests/test_reflow_synthesizer.py", "-v"]
        desc = "Running reflow tests"
    else:
        print(f"{Colors.RED}Invalid test target: {test_target}{Colors.ENDC}")
        return False

    # Add coverage if requested
    if coverage:
        pytest_cmd.extend([
            "--cov=Sources/Marcedit/python_site/editor_pkg",
            "--cov-report=term-missing",
            "--cov-report=html"
        ])
        desc += " with coverage"

    print(f"{Colors.HEADER}{desc}...{Colors.ENDC}")
    print()
    print(f"{Colors.DIM}Using Python: {source_type}{Colors.ENDC}")
    print(f"{Colors.DIM}Path: {python_cmd}{Colors.ENDC}")
    print()

    # Check if pytest is available
    check_cmd = [python_cmd, "-c", "import pytest"]
    check_result = subprocess.run(check_cmd, capture_output=True)

    if check_result.returncode != 0:
        print(f"{Colors.YELLOW}⚠ pytest not found. Installing...{Colors.ENDC}")
        pip_cmd = [python_cmd, "-m", "pip", "install"]
        if source_type == "System":
            pip_cmd.append("--user")
        pip_cmd.extend(["pytest", "PyMuPDF"])
        install_result = subprocess.run(pip_cmd)

        if install_result.returncode != 0:
            print(f"{Colors.RED}✗ Failed to install pytest{Colors.ENDC}")
            return False

        # Install coverage tools if needed
        if coverage:
            cov_cmd = [python_cmd, "-m", "pip", "install"]
            if source_type == "System":
                cov_cmd.append("--user")
            cov_cmd.append("pytest-cov")
            subprocess.run(cov_cmd)

    if coverage:
        # Check for pytest-cov
        check_cov = [python_cmd, "-c", "import pytest_cov"]
        cov_result = subprocess.run(check_cov, capture_output=True)

        if cov_result.returncode != 0:
            print(f"{Colors.YELLOW}⚠ pytest-cov not found. Installing...{Colors.ENDC}")
            pip_cmd = [python_cmd, "-m", "pip", "install"]
            if source_type == "System":
                pip_cmd.append("--user")
            pip_cmd.append("pytest-cov")
            subprocess.run(pip_cmd)

    # Run pytest using python -m pytest for better module resolution
    cmd = [python_cmd, "-m"] + pytest_cmd

    success, _ = run_command(cmd, desc, cwd=PROJECT_ROOT)

    if coverage and success:
        print()
        print(f"{Colors.GREEN}Coverage report generated:{Colors.ENDC}")
        print(f"{Colors.DIM}  Terminal: See above{Colors.ENDC}")
        print(f"{Colors.DIM}  HTML: {PROJECT_ROOT / 'htmlcov' / 'index.html'}{Colors.ENDC}")

    return success

def run_automated_crash_test() -> bool:
    """Run automated crash test to detect app startup and stability issues."""
    print(f"{Colors.HEADER}Running Automated Crash Test...{Colors.ENDC}")
    print()

    test_script = PROJECT_ROOT / "test_app_crash.py"

    if not test_script.exists():
        print(f"{Colors.RED}✗ Test script not found: {test_script}{Colors.ENDC}")
        return False

    # Run the crash test
    python_cmd, _ = find_python_command()
    cmd = [python_cmd, str(test_script)]

    success, output = run_command(cmd, "Automated crash test", cwd=PROJECT_ROOT)

    if success:
        print()
        print(f"{Colors.GREEN}✓ Automated crash test passed{Colors.ENDC}")
        print(f"{Colors.DIM}  App launched and remained stable{Colors.ENDC}")
    else:
        print()
        print(f"{Colors.RED}✗ Crash test detected issues{Colors.ENDC}")
        print(f"{Colors.DIM}  Check output above for details{Colors.ENDC}")

    return success

def run_ui_interaction_test() -> bool:
    """Run UI interaction test to test menus, windows, and text input system."""
    print(f"{Colors.HEADER}Running UI Interaction Test...{Colors.ENDC}")
    print()

    test_script = PROJECT_ROOT / "test_ui_interactions.scpt"

    if not test_script.exists():
        print(f"{Colors.RED}✗ Test script not found: {test_script}{Colors.ENDC}")
        return False

    # Run the AppleScript test
    cmd = ["osascript", str(test_script)]

    success, output = run_command(cmd, "UI interaction test", cwd=PROJECT_ROOT)

    if success:
        print()
        print(f"{Colors.GREEN}✓ UI interaction test passed{Colors.ENDC}")
        print(f"{Colors.DIM}  Menus, windows, and text input working{Colors.ENDC}")
    else:
        print()
        print(f"{Colors.RED}✗ UI test detected issues{Colors.ENDC}")
        print(f"{Colors.DIM}  Check output above for details{Colors.ENDC}")

    return success

def run_full_stability_suite() -> bool:
    """Run comprehensive stability suite (crash + UI + unit tests)."""
    print(f"{Colors.HEADER}Running Full Stability Suite...{Colors.ENDC}")
    print()
    print(f"{Colors.DIM}This will run:{Colors.ENDC}")
    print(f"{Colors.DIM}  1. Automated crash test{Colors.ENDC}")
    print(f"{Colors.DIM}  2. UI interaction test{Colors.ENDC}")
    print(f"{Colors.DIM}  3. Python unit tests{Colors.ENDC}")
    print()

    results = {}

    # Test 1: Automated crash test
    print(f"{Colors.MAGENTA}─── Test 1/3: Automated Crash Test ───{Colors.ENDC}")
    results["crash_test"] = run_automated_crash_test()
    print()

    # Test 2: UI interaction test
    print(f"{Colors.MAGENTA}─── Test 2/3: UI Interaction Test ───{Colors.ENDC}")
    results["ui_test"] = run_ui_interaction_test()
    print()

    # Test 3: Python unit tests
    print(f"{Colors.MAGENTA}─── Test 3/3: Python Unit Tests ───{Colors.ENDC}")
    results["unit_tests"] = run_pytest(test_target="all", coverage=False)
    print()

    # Summary
    print(f"{Colors.HEADER}Stability Suite Summary{Colors.ENDC}")
    print()

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = f"{Colors.GREEN}✓ PASS{Colors.ENDC}" if result else f"{Colors.RED}✗ FAIL{Colors.ENDC}"
        test_label = {
            "crash_test": "Automated Crash Test",
            "ui_test": "UI Interaction Test",
            "unit_tests": "Python Unit Tests"
        }.get(test_name, test_name)

        print(f"  {status}: {test_label}")

    print()
    if passed == total:
        print(f"{Colors.GREEN}✓ All stability tests passed ({passed}/{total}){Colors.ENDC}")
        print(f"{Colors.DIM}  App is stable and ready for use!{Colors.ENDC}")
        return True
    else:
        print(f"{Colors.YELLOW}⚠ Some stability tests failed ({passed}/{total}){Colors.ENDC}")
        print(f"{Colors.DIM}  Review failures above before deploying{Colors.ENDC}")
        return False

def run_redaction_cleanup_tests() -> bool:
    """Run architecture tests for redaction cleanup - verifies double-text fix."""
    print(f"{Colors.HEADER}Running Redaction Cleanup Tests...{Colors.ENDC}")
    print()
    print(f"{Colors.DIM}Tests verify that text replacement properly removes original text{Colors.ENDC}")
    print(f"{Colors.DIM}(fixes 'double text' / ghost text artifacts){Colors.ENDC}")
    print()

    python_cmd, source_type = find_python_command()
    print(f"{Colors.DIM}Using Python: {source_type}{Colors.ENDC}")
    print()

    # Run specific test file
    cmd = [python_cmd, "-m", "pytest", "tests/test_redaction_cleanup.py", "-v"]
    
    success, _ = run_command(cmd, "Redaction cleanup tests", cwd=PROJECT_ROOT)
    
    if success:
        print()
        print(f"{Colors.GREEN}✓ All redaction cleanup tests passed{Colors.ENDC}")
        print(f"{Colors.DIM}  Double-text fix is working correctly{Colors.ENDC}")
    else:
        print()
        print(f"{Colors.RED}✗ Redaction cleanup tests failed{Colors.ENDC}")
        print(f"{Colors.DIM}  Check output above for details{Colors.ENDC}")
    
    return success

def reproduce_text_selection_crash() -> bool:
    """Reproduce the TextInputUIMacHelper crash that occurs when clicking on text."""
    print(f"{Colors.RED}Reproducing Text Selection Crash...{Colors.ENDC}")
    print()
    print(f"{Colors.YELLOW}This test will:{Colors.ENDC}")
    print(f"{Colors.YELLOW}  1. Launch Marcedit app{Colors.ENDC}")
    print(f"{Colors.YELLOW}  2. Create/open a test PDF{Colors.ENDC}")
    print(f"{Colors.YELLOW}  3. Simulate clicking on text{Colors.ENDC}")
    print(f"{Colors.YELLOW}  4. Check if app crashes{Colors.ENDC}")
    print()
    print(f"{Colors.RED}⚠ WARNING: This will likely crash the app{Colors.ENDC}")
    print()

    test_script = PROJECT_ROOT / "test_text_selection_crash.py"

    if not test_script.exists():
        print(f"{Colors.RED}✗ Test script not found: {test_script}{Colors.ENDC}")
        return False

    # Run the crash reproduction test
    python_cmd, _ = find_python_command()
    cmd = [python_cmd, str(test_script)]

    success, _ = run_command(cmd, "Text selection crash test", cwd=PROJECT_ROOT)

    if success:
        print()
        print(f"{Colors.GREEN}✓ App did NOT crash - TextInputUIMacHelper issue is FIXED!{Colors.ENDC}")
    else:
        print()
        print(f"{Colors.RED}✗ App crashed - TextInputUIMacHelper issue still present{Colors.ENDC}")
        print()
        print(f"{Colors.YELLOW}See TUI_TEXT_SELECTION_CRASH.md for solutions{Colors.ENDC}")

    return success

def reproduce_text_selection_crash_xctest() -> bool:
    """Reproduce the TextInputUIMacHelper crash using XCTest framework."""
    print(f"{Colors.RED}Reproducing Text Selection Crash (XCTest)...{Colors.ENDC}")
    print()
    print(f"{Colors.YELLOW}This test will:{Colors.ENDC}")
    print(f"{Colors.YELLOW}  1. Build the app in Debug configuration{Colors.ENDC}")
    print(f"{Colors.YELLOW}  2. Run XCTest testTextInputSystem(){Colors.ENDC}")
    print(f"{Colors.YELLOW}  3. Verify if crash occurs when clicking on PDF text{Colors.ENDC}")
    print()
    print(f"{Colors.CYAN}Note: This is the more reliable test method{Colors.ENDC}")
    print()

    # First, build the app
    print(f"{Colors.BLUE}Building app for testing...{Colors.ENDC}")
    if not build("Debug"):
        print(f"{Colors.RED}✗ Build failed - cannot run XCTest{Colors.ENDC}")
        return False

    # Run the XCTest
    print()
    print(f"{Colors.BLUE}Running XCTest for text input crash...{Colors.ENDC}")

    xctest_cmd = [
        "xcodebuild",
        "test",
        "-scheme", "Marcedit",
        "-destination", "platform=macOS",
        "-only-testing:MarceditTests/MarceditUITests/testTextInputSystem"
    ]

    success, output = run_command(xctest_cmd, "XCTest text input crash test", capture_output=True)

    # Display test output
    if output:
        print()
        print(f"{Colors.DIM}Test Output:{Colors.ENDC}")
        print(output)

    if success:
        print()
        print(f"{Colors.GREEN}✓ Test passed - TextInputUIMacHelper crash is FIXED!{Colors.ENDC}")
    else:
        print()
        print(f"{Colors.RED}✗ Test failed - App crashed or error occurred{Colors.ENDC}")
        print()
        print(f"{Colors.YELLOW}Check the output above for crash details{Colors.ENDC}")
        print(f"{Colors.YELLOW}Crash logs: ~/Library/Logs/DiagnosticReports/{Colors.ENDC}")

    return success

def run_both_crash_tests() -> bool:
    """Run both Python and XCTest crash tests for comprehensive verification."""
    print(f"{Colors.MAGENTA}Running Both Crash Tests{Colors.ENDC}")
    print()
    print(f"{Colors.YELLOW}This will run both testing methods to verify results{Colors.ENDC}")
    print()

    results = []

    # Test 1: Python test
    print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.CYAN}Test 1: Python Coordinate-Based Test{Colors.ENDC}")
    print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
    print()

    result1 = reproduce_text_selection_crash()
    results.append(("Python Test", result1))

    print()

    # Test 2: XCTest
    print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
    print(f"{Colors.CYAN}Test 2: XCTest UI Test{Colors.ENDC}")
    print(f"{Colors.CYAN}{'='*60}{Colors.ENDC}")
    print()

    result2 = reproduce_text_selection_crash_xctest()
    results.append(("XCTest", result2))

    # Summary
    print()
    print(f"{Colors.MAGENTA}{'='*60}{Colors.ENDC}")
    print(f"{Colors.MAGENTA}Summary of Both Tests{Colors.ENDC}")
    print(f"{Colors.MAGENTA}{'='*60}{Colors.ENDC}")
    print()

    all_passed = True
    for test_name, result in results:
        status = f"{Colors.GREEN}PASS{Colors.ENDC}" if result else f"{Colors.RED}FAIL{Colors.ENDC}"
        print(f"  {test_name}: {status}")
        if not result:
            all_passed = False

    print()

    if all_passed:
        print(f"{Colors.GREEN}✓ Both tests PASSED - TextInputUIMacHelper crash is FIXED!{Colors.ENDC}")
    else:
        print(f"{Colors.RED}✗ One or more tests FAILED - TextInputUIMacHelper crash still present{Colors.ENDC}")

    return all_passed

def generate_uitest_corpus() -> bool:
    """Generate the XCUITest PDF corpus using PyMuPDF."""
    print(f"{Colors.HEADER}Generating XCUITest Corpus PDFs...{Colors.ENDC}")
    print()
    print(f"{Colors.DIM}Creates 5 test PDFs in tests/ui_corpus/cases/ using PyMuPDF.{Colors.ENDC}")
    print(f"{Colors.DIM}Requires: pip install pymupdf{Colors.ENDC}")
    print()

    script = PROJECT_ROOT / "tests" / "ui_corpus" / "generate_corpus.py"
    if not script.exists():
        print(f"{Colors.RED}✗ Corpus generator not found: {script}{Colors.ENDC}")
        return False

    python_cmd, source_type = find_python_command()
    print(f"{Colors.DIM}Using Python: {source_type}{Colors.ENDC}")

    # Check for fitz (PyMuPDF)
    check = subprocess.run([python_cmd, "-c", "import fitz"], capture_output=True)
    if check.returncode != 0:
        print(f"{Colors.YELLOW}⚠ PyMuPDF not found. Installing...{Colors.ENDC}")
        subprocess.run([python_cmd, "-m", "pip", "install", "pymupdf"])

    cmd = [python_cmd, str(script)]
    success, _ = run_command(cmd, "Generating corpus PDFs", cwd=PROJECT_ROOT)

    if success:
        print()
        print(f"{Colors.GREEN}✓ Corpus generated in tests/ui_corpus/cases/{Colors.ENDC}")
        print(f"{Colors.DIM}  001_simple_word, 002_full_line, 003_split_runs,{Colors.ENDC}")
        print(f"{Colors.DIM}  004_multipage, 005_font_preservation{Colors.ENDC}")

    return success


def run_xcuitests() -> bool:
    """Run the full XCUITest suite via xcodebuild."""
    print(f"{Colors.HEADER}Running XCUITests (End-to-End UI Test Suite)...{Colors.ENDC}")
    print()
    print(f"{Colors.DIM}Tests:{Colors.ENDC}")
    print(f"{Colors.DIM}  • RealWorldEditTests  — 5 corpus cases (simple word, full line,{Colors.ENDC}")
    print(f"{Colors.DIM}                          split runs, multi-page, font preservation){Colors.ENDC}")
    print(f"{Colors.DIM}  • SelectionAccuracyTests — joinedLineSelection regression guard{Colors.ENDC}")
    print(f"{Colors.DIM}  • WorkflowTests       — preview, cancel, rapid toggle, consecutive edits{Colors.ENDC}")
    print()

    # Check that corpus exists first
    corpus_dir = PROJECT_ROOT / "tests" / "ui_corpus" / "cases"
    if not corpus_dir.exists() or not any(corpus_dir.iterdir()):
        print(f"{Colors.YELLOW}⚠ Corpus PDFs not found. Generating now...{Colors.ENDC}")
        print()
        if not generate_uitest_corpus():
            print(f"{Colors.RED}✗ Cannot run XCUITests without corpus PDFs.{Colors.ENDC}")
            return False
        print()

    results_path = PROJECT_ROOT / "ignored-resources" / "xctest-results.xcresult"
    # Remove stale result bundle
    if results_path.exists():
        import shutil as _shutil
        _shutil.rmtree(results_path)

    xctest_cmd = [
        "xcodebuild", "test",
        "-project", str(PROJECT_ROOT / "MarceditApp.xcodeproj"),
        "-scheme", "MarceditUITests",
        "-destination", "platform=macOS",
        "-resultBundlePath", str(results_path),
    ]

    success, _ = run_command(xctest_cmd, "Running XCUITests")

    print()
    if success:
        print(f"{Colors.GREEN}✓ All XCUITests passed{Colors.ENDC}")
        if results_path.exists():
            print(f"{Colors.DIM}  Result bundle: {results_path}{Colors.ENDC}")
            print(f"{Colors.DIM}  Open with: open {results_path}{Colors.ENDC}")
    else:
        print(f"{Colors.RED}✗ XCUITests failed{Colors.ENDC}")
        print(f"{Colors.DIM}  Check output above.{Colors.ENDC}")
        if results_path.exists():
            print(f"{Colors.DIM}  Result bundle: {results_path}{Colors.ENDC}")
            print(f"{Colors.DIM}  Open with: open {results_path}{Colors.ENDC}")

    return success


def show_build_info():
    """Show information about existing builds."""
    print(f"{Colors.HEADER}Build Information{Colors.ENDC}")
    print()
    
    if not BUILD_DIR.exists():
        print(f"{Colors.YELLOW}Build directory doesn't exist yet.{Colors.ENDC}")
        return
    
    for config in ["Debug", "Release"]:
        app_path = BUILD_DIR / config / f"{APP_NAME}.app"
        print(f"{Colors.BOLD}{config}:{Colors.ENDC}")
        
        if app_path.exists():
            stat = app_path.stat()
            mod_time = datetime.fromtimestamp(stat.st_mtime)
            
            # Get app size
            total_size = sum(f.stat().st_size for f in app_path.rglob('*') if f.is_file())
            size_mb = total_size / (1024 * 1024)
            
            # Try to get version from Info.plist
            plist_path = app_path / "Contents" / "Info.plist"
            version = "Unknown"
            if plist_path.exists():
                try:
                    result = subprocess.run(
                        ["defaults", "read", str(plist_path), "CFBundleShortVersionString"],
                        capture_output=True, text=True
                    )
                    if result.returncode == 0:
                        version = result.stdout.strip()
                except Exception:
                    pass
            
            print(f"  {Colors.GREEN}✓ Found{Colors.ENDC}")
            print(f"    Path: {app_path}")
            print(f"    Version: {version}")
            print(f"    Size: {size_mb:.1f} MB")
            print(f"    Modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        else:
            print(f"  {Colors.DIM}Not built{Colors.ENDC}")
        print()
    
    # Also check the direct app bundle path (current build structure)
    direct_app = BUILD_DIR / f"{APP_NAME}.app"
    if direct_app.exists():
        print(f"{Colors.BOLD}Current Build:{Colors.ENDC}")
        stat = direct_app.stat()
        mod_time = datetime.fromtimestamp(stat.st_mtime)
        total_size = sum(f.stat().st_size for f in direct_app.rglob('*') if f.is_file())
        size_mb = total_size / (1024 * 1024)
        print(f"  {Colors.GREEN}✓ Found{Colors.ENDC}")
        print(f"    Path: {direct_app}")
        print(f"    Size: {size_mb:.1f} MB")
        print(f"    Modified: {mod_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print()

def wait_for_key():
    """Wait for user to press Enter."""
    print()
    input(f"{Colors.DIM}Press Enter to continue...{Colors.ENDC}")

def main():
    """Main TUI loop."""
    while True:
        print_header()
        print_menu()

        choice = input(f"{Colors.CYAN}Select an option: {Colors.ENDC}").strip().lower()
        print()

        if choice == '1':
            build("Debug")
            wait_for_key()
        elif choice == '2':
            build("Release")
            wait_for_key()
        elif choice == '3':
            # Build & Run
            if build("Debug"):
                run_app()
            wait_for_key()
        elif choice == '4':
            run_app()
            wait_for_key()
        elif choice == '5':
            clean_build_dir(interactive=True)
            wait_for_key()
        elif choice == '6':
            show_build_info()
            wait_for_key()
        elif choice == '7':
            run_tests()
            wait_for_key()
        elif choice == '8':
            run_pytest(test_target="all", coverage=False)
            wait_for_key()
        elif choice == '9':
            run_pytest(test_target="core", coverage=False)
            wait_for_key()
        elif choice == '10':
            run_pytest(test_target="reflow", coverage=False)
            wait_for_key()
        elif choice == '11':
            run_pytest(test_target="all", coverage=True)
            wait_for_key()
        elif choice == '12':
            run_pipeline_verification()
            wait_for_key()
        elif choice == '13':
            run_automated_crash_test()
            wait_for_key()
        elif choice == '14':
            run_ui_interaction_test()
            wait_for_key()
        elif choice == '15':
            run_full_stability_suite()
            wait_for_key()
        elif choice == '16':
            reproduce_text_selection_crash()
            wait_for_key()
        elif choice == '17':
            reproduce_text_selection_crash_xctest()
            wait_for_key()
        elif choice == '18':
            run_both_crash_tests()
            wait_for_key()
        elif choice == '19':
            run_redaction_cleanup_tests()
            wait_for_key()
        elif choice == '20':
            generate_uitest_corpus()
            wait_for_key()
        elif choice == '21':
            run_xcuitests()
            wait_for_key()
        elif choice == 'q' or choice == 'quit' or choice == 'exit':
            print(f"{Colors.GREEN}Goodbye!{Colors.ENDC}")
            break
        else:
            print(f"{Colors.RED}Invalid option. Please try again.{Colors.ENDC}")
            wait_for_key()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.GREEN}Goodbye!{Colors.ENDC}")
        sys.exit(0)
