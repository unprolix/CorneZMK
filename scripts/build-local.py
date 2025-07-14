#!/usr/bin/env python3

"""
ZMK Firmware Local Build Script for Corne Keyboard (Python Version)

This script builds ZMK firmware locally (no Docker) for the Corne keyboard with
options to build only left side, only right side, or both.
Device information is loaded from devices.conf.

Usage: ./build-local.py [options]
Options:
  --shield=TYPE    Shield type to build (from device config or nice_view/nice_view_gem)
  --left-only      Build only left side
  --right-only     Build only right side
  --device=NAME    Device to build for (from devices.conf)
  --no-debug       Disable USB debugging
  --help           Show this help message
"""

import os
import sys
import argparse
import subprocess
import shutil
import platform
import json
import time
from pathlib import Path
from datetime import datetime, timedelta
import shutil

# Setup logging with timestamps
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")
    sys.stdout.flush()  # Ensure output is shown immediately

# Add the lib directory to the Python path so we can import the setup module
script_dir = Path(__file__).resolve().parent
lib_dir = script_dir / "lib"
sys.path.insert(0, str(lib_dir))

# Check for required tools before importing modules
def check_required_tools():
    """Check if all required tools are installed"""
    required_tools = {
        "west": {
            "command": ["west", "--version"],
            "package": "pip install west",
            "description": "Zephyr's meta-tool"
        },
        "cmake": {
            "command": ["cmake", "--version"],
            "package": "pacman -S extra/cmake",
            "description": "Build system generator"
        },
        "git": {
            "command": ["git", "--version"],
            "package": "pacman -S extra/git",
            "description": "Version control system"
        }
    }
    
    missing_tools = []
    
    for tool, info in required_tools.items():
        try:
            subprocess.run(info["command"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            log(f"Found {tool}: {info['description']}")
        except (subprocess.SubprocessError, FileNotFoundError):
            missing_tools.append((tool, info["package"], info["description"]))
    
    if missing_tools:
        log("Missing required tools:", level="ERROR")
        for tool, package, description in missing_tools:
            log(f"  - {tool}: {description}", level="ERROR")
            log(f"    Install with: {package}", level="ERROR")
        sys.exit(1)

# Check for required tools
check_required_tools()

# Now import modules that might require the tools
try:
    import setup
    setup.initialize_venv(["pyyaml"])
    import yaml
except ImportError:
    log("Failed to import required Python modules. Try installing them with:", level="ERROR")
    log("  pip install pyyaml", level="ERROR")
    sys.exit(1)


def find_root_dir(start_dir):
    """Find CorneZMK root directory"""
    current_dir = Path(start_dir).resolve()
    
    # Check if current directory is CorneZMK
    if current_dir.name == "CorneZMK":
        return current_dir
    
    # Check if current directory contains CorneZMK
    if (current_dir / "CorneZMK").exists():
        return current_dir / "CorneZMK"
    
    # Check if scripts directory is in current path
    if current_dir.name == "scripts" and current_dir.parent.exists():
        parent_dir = current_dir.parent
        if parent_dir.name == "CorneZMK":
            return parent_dir
    
    # Check if we're in zmk/CorneZMK
    if "/zmk/CorneZMK" in str(current_dir):
        parts = str(current_dir).split("/zmk/CorneZMK")
        return Path(f"{parts[0]}/zmk/CorneZMK")
    
    # Check if we're in src/zmk/CorneZMK
    if "/src/zmk/CorneZMK" in str(current_dir):
        parts = str(current_dir).split("/src/zmk/CorneZMK")
        return Path(f"{parts[0]}/src/zmk/CorneZMK")
    
    return None


def load_devices_config(config_path):
    """Load device configuration from YAML file"""
    try:
        with open(config_path, 'r') as file:
            config = yaml.safe_load(file)
            # Check if the config has a 'devices' root key
            if 'devices' in config:
                return config['devices']
            return config
    except Exception as e:
        log(f"Error loading devices configuration: {e}", level="ERROR")
        sys.exit(1)


def check_prerequisites(config_path, keyboard_name, zmk_path, exit_on_error=True):
    """Check if required directories and files exist"""
    # Check config repo structure
    if not os.path.isdir(config_path):
        log(f"Error: Config directory not found at {config_path}", level="ERROR")
        if exit_on_error:
            sys.exit(1)
        return False

    if not os.path.isfile(os.path.join(config_path, f"{keyboard_name}.keymap")):
        log(f"Error: {keyboard_name}.keymap not found in {config_path}", level="ERROR")
        if exit_on_error:
            sys.exit(1)
        return False

    # Check for custom board definitions in multiple possible locations
    board_found = False
    
    # Check in CorneZMK/boards
    if os.path.isdir(os.path.join(root_dir, "boards", "arm", keyboard_name)):
        board_found = True
    
    # Check in imported modules
    if not board_found:
        # Check for board in corne-j-keyboard-zmk module (for eyelash_corne)
        if os.path.isdir(os.path.join(zmk_path, "corne-j-keyboard-zmk", "boards", "arm", keyboard_name)):
            board_found = True
    
    if not board_found:
        log(f"Warning: Custom board definition not found for {keyboard_name}")
        log(f"Checked locations:")
        log(f"  - {os.path.join(root_dir, 'boards', 'arm', keyboard_name)}")
        log(f"  - {os.path.join(zmk_path, 'corne-j-keyboard-zmk', 'boards', 'arm', keyboard_name)}")
        log(f"Will attempt to retrieve modules from west.yml...")
        if exit_on_error:
            return False
        return False
    
    return True


def setup_zmk(zmk_path, root_dir):
    """Setup ZMK environment"""
    # Ensure ZMK directory exists
    if not os.path.isdir(zmk_path):
        log("Creating ZMK directory...")
        os.makedirs(zmk_path, exist_ok=True)

    # Clone ZMK if not present
    if not os.path.isdir(os.path.join(zmk_path, "app")):
        log("ZMK not found. Cloning ZMK repository...")
        subprocess.run(["git", "clone", "https://github.com/zmkfirmware/zmk.git", zmk_path], check=True)

    # Initialize ZMK workspace if needed
    if not os.path.isfile(os.path.join(zmk_path, ".west", "config")):
        log("Initializing ZMK workspace...")
        
        # Change to ZMK directory and initialize west
        os.chdir(zmk_path)
        subprocess.run(["west", "init", "-l", "app"], check=True)

    # Copy west.yml file
    shutil.copy(os.path.join(root_dir, "config", "west.yml"), os.path.join(zmk_path, "app", "west.yml"))

    # Update ZMK dependencies
    log("Updating ZMK dependencies...")
    
    # Change to ZMK directory and update west
    os.chdir(zmk_path)
    subprocess.run(["west", "update"], check=True)


def build_firmware(side, build_command, zmk_path, root_dir, timing_callback=None, build_opts=None):
    """Build firmware for a specific side"""
    log(f"Starting build for {side} side")
    
    # Change to ZMK directory
    os.chdir(zmk_path)
    
    # Prepare build command
    cmd = build_command.split()
    
    # Use Popen with pipes for both stdout and stderr
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        bufsize=1,
        errors='replace'  # Handle any encoding issues gracefully
    )
    
    # Read from both stdout and stderr in real-time
    def read_stream(stream, print_func):
        for line in iter(stream.readline, ''):
            if line:
                print_func(line.rstrip())
        stream.close()
    
    # Start threads to read both streams
    import threading
    stdout_thread = threading.Thread(
        target=read_stream,
        args=(process.stdout, lambda x: log(f"[stdout] {x}"))
    )
    stderr_thread = threading.Thread(
        target=read_stream,
        args=(process.stderr, lambda x: log(f"[stderr] {x}", level="ERROR"))
    )
    
    stdout_thread.daemon = True
    stderr_thread.daemon = True
    stdout_thread.start()
    stderr_thread.start()
    
    # Wait for process to complete
    returncode = process.wait()
    
    # Wait for threads to finish
    stdout_thread.join(timeout=1)
    stderr_thread.join(timeout=1)
    
    if returncode != 0:
        log(f"Error: Build command failed (exit code {returncode})", level="ERROR")
        return False, returncode
    
    return True, returncode


def copy_firmware(side, build_output, result_firmware, results_dir, root_dir):
    """Copy firmware files to results directory"""
    # Create results directory if it doesn't exist
    os.makedirs(results_dir, exist_ok=True)
    
    # Check if firmware file exists
    if not os.path.isfile(build_output):
        log(f"Error: Firmware file not found at {build_output}", level="ERROR")
        return False
    
    # Copy firmware file
    try:
        shutil.copy(build_output, result_firmware)
        log(f"Firmware copied to {result_firmware}")
        return True
    except Exception as e:
        log(f"Error copying firmware: {e}", level="ERROR")
        return False


def generate_build_info(script_dir):
    """Generate build info by calling generate_build_info.sh"""
    # Change to script directory to ensure relative paths work
    original_dir = os.getcwd()
    os.chdir(script_dir)
    
    try:
        # Get current git commit hash
        try:
            commit_hash = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], 
                                                universal_newlines=True).strip()
            commit_arg = ["--commit", commit_hash]
        except:
            commit_arg = []
        
        # Run generate_build_info.sh
        subprocess.run(["./generate_build_info.sh"] + commit_arg, check=True)
        log("Generated build info")
    except Exception as e:
        log(f"Error generating build info: {e}", level="ERROR")
    finally:
        # Change back to original directory
        os.chdir(original_dir)


def update_devices_conf(devices_conf_path, device_name, keyboard_name):
    """Update devices.conf with proper firmware names if needed"""
    try:
        # Load devices.conf
        with open(devices_conf_path, 'r') as file:
            devices_conf = yaml.safe_load(file)
        
        # Check if device exists
        if device_name not in devices_conf:
            log(f"Warning: Device {device_name} not found in devices.conf", level="WARNING")
            return
        
        # Check if firmware names are set
        device = devices_conf[device_name]
        modified = False
        
        if 'left_firmware' not in device or not device['left_firmware']:
            device['left_firmware'] = f"{keyboard_name}_left-nice_nano_v2-zmk.uf2"
            modified = True
        
        if 'right_firmware' not in device or not device['right_firmware']:
            device['right_firmware'] = f"{keyboard_name}_right-nice_nano_v2-zmk.uf2"
            modified = True
        
        # Save updated devices.conf if modified
        if modified:
            with open(devices_conf_path, 'w') as file:
                yaml.dump(devices_conf, file, default_flow_style=False)
            log(f"Updated devices.conf with firmware names for {device_name}")
    except Exception as e:
        log(f"Error updating devices.conf: {e}", level="ERROR")


def save_build_stat(side, build_opts, start_time, end_time, duration, returncode):
    """Save build statistics to a JSON file"""
    try:
        # Create stats directory if it doesn't exist
        stats_dir = os.path.join(script_dir, "..", "stats")
        os.makedirs(stats_dir, exist_ok=True)
        
        # Create stats file
        stats_file = os.path.join(stats_dir, "build_stats.json")
        
        # Load existing stats if file exists
        stats = []
        if os.path.isfile(stats_file):
            try:
                with open(stats_file, 'r') as file:
                    stats = json.load(file)
            except:
                stats = []
        
        # Add new stats
        stats.append({
            "timestamp": datetime.now().isoformat(),
            "side": side,
            "build_opts": build_opts,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "duration_seconds": duration,
            "returncode": returncode,
            "success": returncode == 0
        })
        
        # Save stats
        with open(stats_file, 'w') as file:
            json.dump(stats, file, indent=2)
    except Exception as e:
        log(f"Error saving build stats: {e}", level="ERROR")


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Build ZMK firmware for Corne keyboard")
    parser.add_argument("--shield", dest="shield", help="Shield type to build")
    parser.add_argument("--left-only", dest="left_only", action="store_true", help="Build only left side")
    parser.add_argument("--right-only", dest="right_only", action="store_true", help="Build only right side")
    parser.add_argument("--device", dest="device", help="Device to build for (from devices.conf)")
    parser.add_argument("--no-debug", dest="no_debug", action="store_true", help="Disable USB debugging")
    
    args = parser.parse_args()
    
    # Find root directory
    global root_dir
    root_dir = find_root_dir(os.getcwd())
    if not root_dir:
        log("Error: Could not find CorneZMK root directory", level="ERROR")
        sys.exit(1)
    
    log(f"CorneZMK root directory: {root_dir}")
    
    # Load device configuration
    devices_conf_path = os.path.join(root_dir, "etc", "devices.conf")
    devices_conf = load_devices_config(devices_conf_path)
    
    # Determine device to build for
    device_name = args.device or next(iter(devices_conf.keys()))
    if device_name not in devices_conf:
        log(f"Error: Device {device_name} not found in devices.conf", level="ERROR")
        sys.exit(1)
    
    device = devices_conf[device_name]
    keyboard_name = device.get("keyboard_name", "corne")
    
    log(f"Building for device: {device_name} (keyboard: {keyboard_name})")
    
    # Get build options from device configuration
    build_options = device.get('build_options', {})
    
    # Get available shield types and default shield
    available_shield_types = build_options.get('shield_types', ["nice_view", "nice_view_gem"])
    default_shield = build_options.get('default_shield', "nice_view")
    
    # Determine shield type
    shield_type = args.shield if args.shield else default_shield
    
    # Validate shield type
    if shield_type not in available_shield_types:
        log(f"Error: Invalid shield type '{shield_type}' for device '{device_name}'", level="ERROR")
        log(f"Available shield types: {', '.join(available_shield_types)}", level="ERROR")
        sys.exit(1)
    
    # Determine which sides to build
    build_left = not args.right_only
    build_right = not args.left_only
    
    if not build_left and not build_right:
        log("Error: Must build at least one side", level="ERROR")
        sys.exit(1)
    
    # Setup paths
    zmk_path = os.path.join(root_dir, "..", "zmk-firmware")
    config_path = os.path.join(root_dir, "config")
    results_dir = os.path.join(root_dir, "results")
    
    # Check prerequisites
    check_prerequisites(config_path, keyboard_name, zmk_path)
    
    # Setup ZMK
    setup_zmk(zmk_path, root_dir)
    
    # Generate build info
    generate_build_info(script_dir)
    
    # Update devices.conf with firmware names
    update_devices_conf(devices_conf_path, device_name, keyboard_name)
    
    # Build firmware
    success = True
    
    # Determine build options
    build_opts = []
    if args.no_debug:
        build_opts.append("-DCONFIG_ZMK_USB_LOGGING=n")
    
    # Build left side if requested
    if build_left:
        log("Building left side firmware")
        # Use standard shield name (corne_left) instead of constructing from keyboard_name
        left_build_command = f"west build -p -b nice_nano_v2 -d build/left app -- -DSHIELD=corne_left {' '.join(build_opts)}"
        
        start_time = datetime.now()
        left_success, left_returncode = build_firmware("left", left_build_command, zmk_path, root_dir, build_opts=build_opts)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        save_build_stat("left", build_opts, start_time, end_time, duration, left_returncode)
        
        if left_success:
            left_build_output = os.path.join(zmk_path, "build", "left", "zephyr", "zmk.uf2")
            left_result_firmware = os.path.join(results_dir, f"{keyboard_name}_left-nice_nano_v2-zmk.uf2")
            copy_firmware("left", left_build_output, left_result_firmware, results_dir, root_dir)
        else:
            success = False
    
    # Build right side if requested
    if build_right:
        log("Building right side firmware")
        # Use standard shield name (corne_right) instead of constructing from keyboard_name
        right_build_command = f"west build -p -b nice_nano_v2 -d build/right app -- -DSHIELD=corne_right {' '.join(build_opts)}"
        
        start_time = datetime.now()
        right_success, right_returncode = build_firmware("right", right_build_command, zmk_path, root_dir, build_opts=build_opts)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        save_build_stat("right", build_opts, start_time, end_time, duration, right_returncode)
        
        if right_success:
            right_build_output = os.path.join(zmk_path, "build", "right", "zephyr", "zmk.uf2")
            right_result_firmware = os.path.join(results_dir, f"{keyboard_name}_right-nice_nano_v2-zmk.uf2")
            copy_firmware("right", right_build_output, right_result_firmware, results_dir, root_dir)
        else:
            success = False
    
    # Print summary
    if success:
        log("Build completed successfully")
        log(f"Firmware files are in {results_dir}")
    else:
        log("Build failed", level="ERROR")
        sys.exit(1)


if __name__ == "__main__":
    main()
