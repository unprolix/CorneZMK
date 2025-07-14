#!/usr/bin/env python3

"""
ZMK Firmware Local Build Script for Corne Keyboard (Python Version)

This script builds ZMK firmware locally (no Docker) for a variety of keyboards and dongles, with
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
import json
from pathlib import Path
from datetime import datetime

# Setup logging with timestamps
def log(message, level="INFO"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}")
    sys.stdout.flush()  # Ensure output is shown immediately

# Add the lib directory to the Python path so we can import the setup module
script_dir = Path(__file__).resolve().parent
lib_dir = script_dir / "lib"
sys.path.insert(0, str(lib_dir))

import setup
setup.initialize_venv(["pyyaml", "west", "pyelftools"])
import yaml

# Check for required tools before proceeding
def check_required_tools():
    """Check if all required tools are installed"""
    required_tools = {
        # West is now installed in the virtual environment
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


def find_root_dir(start_dir=None):
    """Find CorneZMK root directory by looking up two levels from the script location"""
    # Use the script directory as the starting point
    script_dir = Path(__file__).resolve().parent
    
    # The root directory is two levels up from the script directory (scripts/build-local.py)
    root_dir = script_dir.parent
    
    # Verify this is actually the CorneZMK directory
    if (root_dir / "config").is_dir() and (root_dir / "etc").is_dir():
        return root_dir
    else:
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
    checked_locations = []
    
    # Check in CorneZMK/boards
    primary_location = os.path.join(root_dir, "boards", "arm", keyboard_name)
    checked_locations.append(primary_location)
    if os.path.isdir(primary_location):
        board_found = True
        log(f"Found board definition at {primary_location}")
    
    # Check in all modules in zmk_path
    if not board_found:
        # Get all directories in zmk_path that might be modules
        try:
            for item in os.listdir(zmk_path):
                module_path = os.path.join(zmk_path, item)
                if os.path.isdir(module_path):
                    # Check if this module has a boards/arm directory
                    board_dir = os.path.join(module_path, "boards", "arm", keyboard_name)
                    checked_locations.append(board_dir)
                    if os.path.isdir(board_dir):
                        board_found = True
                        log(f"Found board definition in module: {board_dir}")
                        break
        except Exception as e:
            log(f"Error scanning modules: {e}", level="ERROR")
    
    if not board_found:
        log(f"Warning: Custom board definition not found for {keyboard_name}")
        log(f"Checked locations:")
        for location in checked_locations:
            log(f"  - {location}")
        log(f"Will attempt to retrieve modules from west.yml...")
        if exit_on_error:
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
        # Clone directly into the zmk_path instead of creating a nested directory
        subprocess.run(["git", "clone", "https://github.com/zmkfirmware/zmk.git", "."], cwd=zmk_path, check=True)

    # Get path to Python executable in the virtual environment
    if sys.platform == 'win32':
        python_executable = os.path.join(setup.VENV_DIR, "Scripts", "python.exe")
    else:
        python_executable = os.path.join(setup.VENV_DIR, "bin", "python")

    # Initialize ZMK workspace if needed
    if not os.path.isfile(os.path.join(zmk_path, ".west", "config")):
        log("Initializing ZMK workspace...")
        
        # Change to ZMK directory and initialize west using the venv Python
        os.chdir(zmk_path)
        subprocess.run([python_executable, "-m", "west", "init", "-l", "app"], check=True)

    # Copy west.yml file
    shutil.copy(os.path.join(root_dir, "config", "west.yml"), os.path.join(zmk_path, "app", "west.yml"))

    # Update ZMK dependencies
    log("Updating ZMK dependencies...")
    
    # Change to ZMK directory and update west using the venv Python
    os.chdir(zmk_path)
    subprocess.run([python_executable, "-m", "west", "update"], check=True)


def build_firmware(side, build_command, zmk_path, root_dir, timing_callback=None, build_opts=None):
    """Build firmware for a specific side"""
    log(f"Starting build for {side} side")
    
    # Change to ZMK directory
    os.chdir(zmk_path)
    
    # Get path to Python executable in the virtual environment
    if sys.platform == 'win32':
        python_executable = os.path.join(setup.VENV_DIR, "Scripts", "python.exe")
    else:
        python_executable = os.path.join(setup.VENV_DIR, "bin", "python")
    
    # Prepare build command using the virtual environment's Python
    # Instead of running 'west build' directly, run it as 'python -m west build'
    if build_command.startswith("west "):
        # Replace 'west ' with 'python -m west '
        build_command = f"{python_executable} -m {build_command}"
    
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


def get_repo_name(root_dir):
    """Get repository name from git or directory name"""
    try:
        # Try to get the repository name from git
        original_dir = os.getcwd()
        os.chdir(root_dir)
        try:
            # Check if this is a git repository
            result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], 
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                  universal_newlines=True, check=False)
            if result.returncode == 0:
                # Get the repository name from the remote URL or directory name
                result = subprocess.run(["git", "config", "--get", "remote.origin.url"], 
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
                                      universal_newlines=True, check=False)
                if result.returncode == 0 and result.stdout.strip():
                    # Extract repo name from URL (handles various formats)
                    url = result.stdout.strip()
                    # Remove .git suffix if present
                    if url.endswith(".git"):
                        url = url[:-4]
                    # Get the last part of the URL (the repo name)
                    repo_name = os.path.basename(url)
                    return repo_name
        finally:
            os.chdir(original_dir)
    except Exception as e:
        log(f"Error getting git repository name: {e}", level="WARNING")
    
    # Fallback to directory name
    return os.path.basename(os.path.abspath(root_dir))

def save_build_stat(side, build_opts, start_time, end_time, duration, returncode):
    """Save build statistics to a JSON file in ~/.local/var/<repo-name>/build-stats.json"""
    try:
        # Get repository name
        repo_name = get_repo_name(root_dir)
        
        # Create stats directory in user's local directory
        stats_dir = os.path.join(str(Path.home()), ".local", "var", repo_name)
        os.makedirs(stats_dir, exist_ok=True)
        
        # Create stats file
        stats_file = os.path.join(stats_dir, "build-stats.json")
        
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
            
        log(f"Build statistics saved to {stats_file}")
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
    shield_name = device.get("shield_name", "corne")  # Get shield_name from config, default to corne
    
    log(f"Building for device: {device_name} (keyboard: {keyboard_name}, shield: {shield_name})")
    
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
    zmk_path = os.path.join(str(Path.home()), "pkg", "zmk")
    config_path = os.path.join(root_dir, "config")
    results_dir = os.path.join(root_dir, "results")
    
    # Ensure ZMK directory exists
    if not os.path.isdir(zmk_path):
        log(f"Creating ZMK directory at {zmk_path}...")
        os.makedirs(zmk_path, exist_ok=True)
    
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
    
    # Function to build a specific side
    def build_side(side, build_opts, zmk_path, root_dir, results_dir, keyboard_name, shield_name):
        """Build firmware for a specific side"""
        log(f"Building {side} side firmware")
        
        # Use shield_name from the device config to construct the shield parameter
        # For split keyboards, append _left or _right to the shield name
        shield_param = f"{shield_name}_{side}" if side in ["left", "right"] else shield_name
        
        build_command = f"west build -p -b nice_nano_v2 -d build/{side} app -- -DSHIELD={shield_param} {' '.join(build_opts)}"
        
        start_time = datetime.now()
        side_success, side_returncode = build_firmware(side, build_command, zmk_path, root_dir, build_opts=build_opts)
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        save_build_stat(side, build_opts, start_time, end_time, duration, side_returncode)
        
        if side_success:
            build_output = os.path.join(zmk_path, "build", side, "zephyr", "zmk.uf2")
            result_firmware = os.path.join(results_dir, f"{keyboard_name}_{side}-nice_nano_v2-zmk.uf2")
            copy_firmware(side, build_output, result_firmware, results_dir, root_dir)
            return True
        return False
    
    # Build left side if requested
    if build_left:
        if not build_side("left", build_opts, zmk_path, root_dir, results_dir, keyboard_name, shield_name):
            success = False
    
    # Build right side if requested
    if build_right:
        if not build_side("right", build_opts, zmk_path, root_dir, results_dir, keyboard_name, shield_name):
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
