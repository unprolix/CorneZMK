#!/usr/bin/env python3

"""
ZMK Firmware Build Script for Corne Keyboard (Python Version)

This script builds ZMK firmware for the Corne keyboard with
options to build only left side, only right side, or both.
Device information is loaded from devices.conf.

Usage: ./build.py [options]
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
from pathlib import Path
import os
import sys
import argparse
import subprocess
import shutil
import platform
import json
import time
from datetime import datetime, timedelta

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
setup.initialize_venv(["pyyaml"])
import yaml


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
            return yaml.safe_load(file)
    except Exception as e:
        print(f"Error loading devices configuration: {e}")
        sys.exit(1)


def check_prerequisites(config_path, keyboard_name, zmk_path, exit_on_error=True):
    """Check if required directories and files exist"""
    # Check config repo structure
    if not os.path.isdir(config_path):
        print(f"Error: Config directory not found at {config_path}")
        if exit_on_error:
            sys.exit(1)
        return False

    if not os.path.isfile(os.path.join(config_path, f"{keyboard_name}.keymap")):
        print(f"Error: {keyboard_name}.keymap not found in {config_path}")
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
        print(f"Warning: Custom board definition not found for {keyboard_name}")
        print(f"Checked locations:")
        print(f"  - {os.path.join(root_dir, 'boards', 'arm', keyboard_name)}")
        print(f"  - {os.path.join(zmk_path, 'corne-j-keyboard-zmk', 'boards', 'arm', keyboard_name)}")
        print(f"Will attempt to retrieve modules from west.yml...")
        if exit_on_error:
            return False
        return False
    
    return True


def get_local_workspace(root_dir):
    """Return a local workspace directory for Docker builds and print its location."""
    project_name = Path(root_dir).name
    workspace = Path.home() / ".local" / "var" / project_name / "zmk-workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    print(f"Using workspace directory: {workspace}")
    return workspace

def sync_workspace(src, dst, exclude=None):
    """Sync files from src to dst, optionally excluding some patterns."""
    import shutil
    import stat
    import fnmatch
    import time
    import sys
    
    print(f"Syncing {src} to {dst}")
    
    # Check if source exists
    if not os.path.exists(src):
        print(f"Source directory {src} does not exist. Creating empty destination directory.")
        os.makedirs(dst, exist_ok=True)
        return
    
    def ignore_patterns(_, names):
        if not exclude:
            return []
        ignored = set()
        for pat in exclude:
            ignored.update(fnmatch.filter(names, pat))
        return ignored
    
    def remove_readonly(func, path, _):
        """Clear the readonly bit and reattempt the removal"""
        os.chmod(path, stat.S_IWRITE)
        func(path)
    
    if os.path.exists(dst):
        print(f"Removing existing directory: {dst}")
        # Try multiple times in case of race conditions or slow filesystems
        max_retries = 3
        for attempt in range(max_retries):
            try:
                if os.name == 'nt':
                    shutil.rmtree(dst, onerror=remove_readonly)
                else:
                    shutil.rmtree(dst, ignore_errors=False, onerror=remove_readonly)
                break
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"Error: Failed to remove directory after {max_retries} attempts: {e}")
                    # Try to continue anyway - the copy might still work
                    break
                print(f"Retrying directory removal (attempt {attempt + 1}/{max_retries})...")
                time.sleep(1)
    
    # Ensure the parent directory exists
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    
    print("Starting file copy...")
    try:
        shutil.copytree(src, dst, ignore=ignore_patterns if exclude else None)
        print("File copy completed successfully")
    except Exception as e:
        print(f"Error during file copy: {e}", file=sys.stderr)
        # If the copy failed, ensure we don't leave partial/corrupt state
        if os.path.exists(dst):
            try:
                shutil.rmtree(dst, ignore_errors=True)
            except:
                pass
        raise

def resolve_docker_mount_path(path):
    # No longer needed, but kept for compatibility
    return os.path.abspath(path)

def setup_zmk(zmk_path, root_dir, docker_image):
    workspace = get_local_workspace(root_dir)
    # Define workspace ZMK directory
    ws_zmk = workspace / "zmk-firmware"
    
    # Check if source zmk_path exists
    if not os.path.exists(zmk_path):
        print(f"ZMK source directory {zmk_path} does not exist.")
        # We'll use the workspace directory directly
        zmk_path = str(ws_zmk)
    else:
        # Sync existing ZMK to workspace
        sync_workspace(zmk_path, ws_zmk)
        zmk_path = str(ws_zmk)

    """Setup ZMK environment"""
    # Ensure ZMK directory exists
    if not os.path.isdir(zmk_path):
        print("Creating ZMK directory...")
        os.makedirs(zmk_path, exist_ok=True)

    # Clone ZMK if not present (either in original path or workspace)
    if not os.path.isdir(os.path.join(zmk_path, "app")):
        print("ZMK not found. Cloning ZMK repository...")
        # Clone directly to the workspace directory
        subprocess.run(["git", "clone", "https://github.com/zmkfirmware/zmk.git", zmk_path], check=True)

    # Check if ZMK directory has correct ownership
    if os.path.isdir(zmk_path):
        # Check if any files are owned by root
        try:
            result = subprocess.run(["find", zmk_path, "-user", "root", "-print", "-quit"], 
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.stdout:
                print("Fixing ZMK directory ownership...")
                user_id = os.getuid()
                group_id = os.getgid()
                try:
                    subprocess.run(["sudo", "chown", "-R", f"{user_id}:{group_id}", zmk_path], check=True)
                except subprocess.CalledProcessError:
                    print(f"Error: Failed to fix ZMK directory ownership. Please run: sudo chown -R {user_id}:{group_id} {zmk_path}")
                    sys.exit(1)
        except Exception as e:
            print(f"Warning: Could not check file ownership: {e}")

    # Initialize ZMK workspace if needed
    if not os.path.isfile(os.path.join(zmk_path, ".west", "config")):
        print("Initializing ZMK workspace...")
        user_id = os.getuid()
        group_id = os.getgid()
        
        cmd = [
            "docker", "run", "--rm",
            "-v", f"{zmk_path}:/zmk",
            "-w", "/zmk",
            "-e", "GIT_CONFIG_COUNT=1",
            "-e", "GIT_CONFIG_KEY_0=safe.directory",
            "-e", "GIT_CONFIG_VALUE_0=/zmk",
            "--user", f"{user_id}:{group_id}",
            docker_image,
            "bash", "-c", "git config --global --add safe.directory '*' && west init -l app"
        ]
        
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
            args=(process.stdout, lambda x: print(f"[stdout] {x}"))
        )
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(process.stderr, lambda x: print(f"[stderr] {x}", file=sys.stderr))
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
            print(f"Error: Command failed (exit code {returncode})")
            sys.exit(1)

    # Copy west.yml file
    shutil.copy(os.path.join(root_dir, "config", "west.yml"), os.path.join(zmk_path, "app", "west.yml"))

    # Update ZMK dependencies
    log("Updating ZMK dependencies...")
    user_id = os.getuid()
    group_id = os.getgid()
    
    docker_zmk_path = resolve_docker_mount_path(zmk_path)
    
    # First, check if we can run a simple Docker command
    log("Testing Docker with a simple command...")
    test_cmd = ["docker", "run", "--rm", "--network", "host", "hello-world"]
    test_result = subprocess.run(test_cmd, capture_output=True, text=True)
    log(f"Docker test command output: {test_result.stdout}")
    if test_result.returncode != 0:
        log(f"Docker test command failed: {test_result.stderr}", level="ERROR")
    
    cmd = [
        "docker", "run", "--rm",
        "--network", "host",  # Use host networking
        "-v", f"{docker_zmk_path}:/zmk",
        "-w", "/zmk",
        "-e", "GIT_CONFIG_COUNT=1",
        "-e", "GIT_CONFIG_KEY_0=safe.directory",
        "-e", "GIT_CONFIG_VALUE_0=/workspace/zmk-firmware",
        "--user", f"{user_id}:{group_id}",
        docker_image,
        "bash", "-c", "git config --global --add safe.directory '*' && west update"
    ]
    
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
        args=(process.stdout, lambda x: print(f"[stdout] {x}"))
    )
    stderr_thread = threading.Thread(
        target=read_stream,
        args=(process.stderr, lambda x: print(f"[stderr] {x}", file=sys.stderr))
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
        print(f"Error: Command failed (exit code {returncode})")
        sys.exit(1)


def build_firmware(side, build_command, docker_image, zmk_path, root_dir, timing_callback=None, build_opts=None):
    log(f"Starting build for {side} side")
    log(f"Source ZMK path: {zmk_path}")
    log(f"Source root dir: {root_dir}")
    
    workspace = get_local_workspace(root_dir)
    ws_zmk = workspace / "zmk-firmware"
    ws_root = workspace / "project-root"
    
    log(f"Syncing ZMK to workspace: {ws_zmk}")
    sync_start = time.time()
    sync_workspace(zmk_path, ws_zmk)
    log(f"Syncing project root to workspace: {ws_root}")
    sync_workspace(root_dir, ws_root)
    log(f"Sync completed in {time.time() - sync_start:.1f} seconds")
    
    zmk_path = str(ws_zmk)
    root_dir = str(ws_root)
    log(f"Using workspace ZMK path: {zmk_path}")
    log(f"Using workspace root dir: {root_dir}")

    """Build firmware for a specific side"""
    print(f"Building {side} side firmware")
    user_id = os.getuid()
    group_id = os.getgid()

    docker_zmk_path = resolve_docker_mount_path(zmk_path)
    docker_root_dir = resolve_docker_mount_path(root_dir)
    # Add network diagnostics
    log("Running Docker network diagnostics...")
    subprocess.run(["docker", "network", "ls"], check=False)
    
    cmd = [
        "docker", "run", "--rm",
        "--network", "host",  # Use host networking
        "-v", f"{docker_zmk_path}:/zmk",
        "-v", f"{docker_root_dir}:/workspace",
        "-w", "/zmk/app",
        "-e", "ZEPHYR_BASE=/zmk/zephyr",
        "-e", "BOARD_ROOT=/workspace",
        "--user", f"{user_id}:{group_id}",
        docker_image
    ]
    
    log(f"Docker command: {' '.join(cmd)}")

    
    # Add the build command as separate arguments
    cmd.extend(build_command.split())
    
    start_time = datetime.now()
    try:
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
            args=(process.stdout, lambda x: print(f"[stdout] {x}"))
        )
        stderr_thread = threading.Thread(
            target=read_stream,
            args=(process.stderr, lambda x: print(f"[stderr] {x}", file=sys.stderr))
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
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        if timing_callback is not None and build_opts is not None:
            timing_callback(side, build_opts, start_time, end_time, duration, returncode)
        if returncode != 0:
            print(f"Error: Failed to build {side} side firmware (exit code {returncode})")
            sys.exit(1)
    except Exception as e:
        print(f"Error: Exception during build: {e}")
        sys.exit(1)



def copy_firmware(side, build_output, result_firmware, results_dir, root_dir):
    """Copy firmware files to results directory"""
    # Extract the build directory suffix from the build_output path
    build_dir_parts = os.path.normpath(build_output).split(os.sep)
    if len(build_dir_parts) >= 3:
        build_dir_suffix = build_dir_parts[-3]  # e.g., eyelash_corne_left
        
        # Construct the workspace path where the files are actually built
        # Use the actual directory name from the path, not just the last component
        project_name = os.path.basename(os.path.normpath(root_dir))
        
        # Try multiple possible workspace paths
        workspace_paths = [
            Path.home() / ".local" / "var" / project_name / "zmk-workspace" / "project-root" / "build" / build_dir_suffix / "zephyr" / "zmk.uf2",
            Path.home() / ".local" / "var" / "CorneZMK" / "zmk-workspace" / "project-root" / "build" / build_dir_suffix / "zephyr" / "zmk.uf2",
            Path.home() / ".local" / "var" / "zmk-workspace" / "project-root" / "build" / build_dir_suffix / "zephyr" / "zmk.uf2"
        ]
        
        # Use the first path that exists
        workspace_build_output = None
        for path in workspace_paths:
            if os.path.isfile(path):
                workspace_build_output = path
                break
        
        # If none of the paths exist, use the first one for reporting
        if workspace_build_output is None:
            workspace_build_output = workspace_paths[0]
        
        # Log the path we're looking for
        print(f"Looking for {side} side firmware at: {workspace_build_output}")
        
        if os.path.isfile(workspace_build_output):
            # Create results directory if it doesn't exist
            os.makedirs(results_dir, exist_ok=True)
            target_path = os.path.join(results_dir, result_firmware)
            shutil.copy(workspace_build_output, target_path)
            print(f"{side} side firmware copied to {target_path}")
            return True
        else:
            # Try an alternative path format as fallback
            alt_build_dir_suffix = f"{build_dir_parts[-3]}_{build_dir_parts[-2]}"
            alt_workspace_build_output = Path.home() / ".local" / "var" / project_name / "zmk-workspace" / "project-root" / "build" / alt_build_dir_suffix / "zephyr" / "zmk.uf2"
            print(f"Trying alternative path: {alt_workspace_build_output}")
            
            if os.path.isfile(alt_workspace_build_output):
                os.makedirs(results_dir, exist_ok=True)
                target_path = os.path.join(results_dir, result_firmware)
                shutil.copy(alt_workspace_build_output, target_path)
                print(f"{side} side firmware copied to {target_path}")
                return True
            else:
                print(f"Error: {side} side firmware not found at either path")
                return False
    else:
        print(f"Error: Could not determine build directory suffix from {build_output}")
        return False


def generate_build_info(script_dir):
    """Generate build info by calling generate_build_info.sh"""
    gen_build_info_script = os.path.join(script_dir, "generate_build_info.sh")
    
    # Check if the script exists
    if not os.path.isfile(gen_build_info_script):
        print(f"ERROR: generate_build_info.sh not found at {gen_build_info_script}")
        sys.exit(1)
    
    # Save current directory
    current_dir = os.getcwd()
    
    try:
        # Change to the scripts directory to run generate_build_info.sh
        os.chdir(script_dir)
        
        # Run the script with full path
        subprocess.run([gen_build_info_script], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running generate_build_info.sh: {e}")
        sys.exit(1)
    finally:
        # Return to previous directory
        os.chdir(current_dir)


def update_devices_conf(devices_conf_path, device_name, keyboard_name):
    """Update devices.conf with proper firmware names if needed"""
    with open(devices_conf_path, 'r') as file:
        config = yaml.safe_load(file)
    
    # Check if device exists
    if device_name not in config.get('devices', {}):
        print(f"Error: Device '{device_name}' not found in devices.conf")
        sys.exit(1)
    
    device_config = config['devices'][device_name]
    
    # Update firmware names if they are placeholders
    firmware_config = device_config.get('firmware', {})
    
    if 'standard' in firmware_config:
        std_config = firmware_config['standard']
        if isinstance(std_config, dict):
            if std_config.get('left') == "xxxx_left":
                std_config['left'] = f"{keyboard_name}_left.uf2"
            if std_config.get('right') == "xxxx_right":
                std_config['right'] = f"{keyboard_name}_right.uf2"
    
    if 'with_dongle' in firmware_config:
        dongle_config = firmware_config['with_dongle']
        if isinstance(dongle_config, dict):
            if dongle_config.get('left') == "xxxx_with_dongle_left":
                dongle_config['left'] = f"{keyboard_name}_with_dongle_left.uf2"
            if dongle_config.get('right') == "xxxx_with_dongle_right":
                dongle_config['right'] = f"{keyboard_name}_with_dongle_right.uf2"
    
    # Write updated config back to file
    with open(devices_conf_path, 'w') as file:
        yaml.dump(config, file, default_flow_style=False)
    
    return config['devices'][device_name]


def save_build_stat(side, build_opts, start_time, end_time, duration, returncode):
    # Determine project dir name
    project_dir = Path(__file__).resolve().parent.parent.name
    stats_dir = Path.home() / ".local" / "var" / project_dir
    stats_dir.mkdir(parents=True, exist_ok=True)
    stats_file = stats_dir / "build-stats.json"
    now = datetime.now()
    # Load existing stats
    if stats_file.exists():
        try:
            with open(stats_file, "r") as f:
                stats = json.load(f)
        except Exception:
            stats = []
    else:
        stats = []
    # Remove stats older than 2 months
    two_months_ago = now - timedelta(days=62)
    stats = [s for s in stats if s.get("start_time") and datetime.fromisoformat(s["start_time"]) >= two_months_ago]
    # Add new stat
    entry = {
        "side": side,
        "build_opts": build_opts,
        "start_time": start_time.isoformat(),
        "end_time": end_time.isoformat(),
        "duration_sec": duration,
        "returncode": returncode
    }
    stats.append(entry)
    # Save
    with open(stats_file, "w") as f:
        json.dump(stats, f, indent=2)

def main():
    # Initialize the virtual environment (re-executes under venv if needed)
    setup.initialize_venv()
    # Now in venv, parse command line arguments
    parser = argparse.ArgumentParser(description="ZMK Firmware Build Script for Corne Keyboard")
    parser.add_argument("--shield", dest="shield_type",
                        help="Shield type to build (from device config or nice_view/nice_view_gem)")
    parser.add_argument("--left-only", dest="left_only", action="store_true",
                        help="Build only left side")
    parser.add_argument("--right-only", dest="right_only", action="store_true",
                        help="Build only right side")
    parser.add_argument("--device", dest="device_name", default="corne_ergokeeb",
                        help="Device to build for (from devices.conf)")
    parser.add_argument("--no-debug", dest="no_debug", action="store_true",
                        help="Disable USB debugging")
    
    args = parser.parse_args()
    
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Find CorneZMK root directory
    global root_dir
    root_dir = find_root_dir(script_dir)
    
    if not root_dir:
        print("Error: Cannot determine CorneZMK root directory")
        print("Please run this script from the CorneZMK directory or its scripts subdirectory")
        sys.exit(1)
    
    # Load device configuration
    devices_conf_path = os.path.join(root_dir, "etc", "devices.conf")
    devices_config = load_devices_config(devices_conf_path)
    
    # Get device information
    if args.device_name not in devices_config.get('devices', {}):
        print(f"Error: Device '{args.device_name}' not found in devices.conf")
        sys.exit(1)
    
    # Get device configuration
    device_config = devices_config['devices'][args.device_name]
    
    # Get keyboard name from device config
    keyboard_name = device_config.get('keyboard_name')
    if not keyboard_name:
        print(f"Error: No keyboard_name specified for device '{args.device_name}' in devices.conf")
        sys.exit(1)
    
    # Get build options from device config
    build_options = device_config.get('build_options', {})
    
    # Get available shield types and default shield
    available_shield_types = build_options.get('shield_types', ["nice_view", "nice_view_gem"])
    default_shield = build_options.get('default_shield', "nice_view")
    
    # Use command line shield type or default from config
    shield_type = args.shield_type if args.shield_type else default_shield
    
    # Validate shield type
    if shield_type not in available_shield_types:
        print(f"Error: Invalid shield type '{shield_type}' for device '{args.device_name}'")
        print(f"Available shield types: {', '.join(available_shield_types)}")
        sys.exit(1)
    
    # Determine which sides to build
    build_left = True
    build_right = True
    
    if args.left_only:
        build_right = False
        print("Build flag set: left side only")
    
    if args.right_only:
        build_left = False
        print("Build flag set: right side only")
    
    # Enable USB debugging based on config and command line options
    usb_debugging = "n" if args.no_debug else build_options.get('usb_debugging', "y")
    
    # ZMK repository path
    # Determine the actual path to the script and find the ZMK firmware directory
    script_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    zmk_path = os.path.join(script_path, "zmk-firmware")
    
    # Verify the ZMK firmware directory exists
    if not os.path.exists(zmk_path):
        print(f"Error: ZMK firmware directory not found at {zmk_path}")
        print("Looking for ZMK firmware in alternate locations...")
        
        # Try alternate locations
        alternate_paths = [
            os.path.join(root_dir, "zmk-firmware"),
            os.path.join(os.path.dirname(script_path), "zmk-firmware"),
            "/home/jjb/src/floof/zmk/CorneZMK/zmk-firmware"
        ]
        
        for alt_path in alternate_paths:
            if os.path.exists(alt_path):
                print(f"Found ZMK firmware at: {alt_path}")
                zmk_path = alt_path
                break
        else:
            print("Error: Could not find ZMK firmware directory. Please specify the path manually.")
            sys.exit(1)
    
    # Docker image for building
    docker_image = "zmkfirmware/zmk-build-arm:stable"
    
    # Directory paths
    config_path = os.path.join(root_dir, "config")
    build_dir = os.path.join(root_dir, "build")
    results_dir = os.path.join(root_dir, "results")
    
    # Get firmware configuration based on shield type
    firmware_config = device_config.get('firmware', {})
    
    # Determine build directories and output paths based on shield type
    if shield_type == "nice_view_gem":
        shield_suffix = "_gem"
        firmware_type = "nice_view_gem"
    elif shield_type == "nice_view":
        shield_suffix = ""
        firmware_type = "standard"
    else:
        shield_suffix = f"_{shield_type}"
        firmware_type = shield_type
    
    # Set build directories and output paths
    build_dir_left = os.path.join(build_dir, f"{keyboard_name}_left{shield_suffix}")
    build_dir_right = os.path.join(build_dir, f"{keyboard_name}_right{shield_suffix}")
    build_dir_suffix_left = f"{keyboard_name}_left{shield_suffix}"
    build_dir_suffix_right = f"{keyboard_name}_right{shield_suffix}"
    
    # Get firmware filenames from config
    if firmware_type in firmware_config:
        if isinstance(firmware_config[firmware_type], dict):
            result_firmware_left = firmware_config[firmware_type].get('left', f"{keyboard_name}_left{shield_suffix}.uf2")
            result_firmware_right = firmware_config[firmware_type].get('right', f"{keyboard_name}_right{shield_suffix}.uf2")
        else:
            # Single firmware file (e.g., for dongle)
            result_firmware_left = firmware_config[firmware_type]
            result_firmware_right = firmware_config[firmware_type]
    else:
        # Fallback to default naming convention
        result_firmware_left = f"{keyboard_name}_left{shield_suffix}.uf2"
        result_firmware_right = f"{keyboard_name}_right{shield_suffix}.uf2"
    
    build_output_left = os.path.join(build_dir_left, "zephyr", "zmk.uf2")
    build_output_right = os.path.join(build_dir_right, "zephyr", "zmk.uf2")
    
    # Set up build command extras based on USB debugging
    if usb_debugging == "y":
        build_command_extra = "--snippet zmk-usb-logging"
    else:
        build_command_extra = ""
    
    # Set up build commands
    build_command_left = f"west build -d /workspace/build/{build_dir_suffix_left} -b {keyboard_name}_left {build_command_extra} -- -DSHIELD={shield_type} -DZMK_CONFIG=/workspace/config"
    build_command_right = f"west build -d /workspace/build/{build_dir_suffix_right} -b {keyboard_name}_right {build_command_extra} -- -DSHIELD={shield_type} -DZMK_CONFIG=/workspace/config"
    
    print(f"Building ZMK firmware for {keyboard_name} with {shield_type} shield...")
    print(f"Device: {args.device_name} ({device_config.get('description', '')})")
    print(f"USB debugging: {'enabled' if usb_debugging == 'y' else 'disabled'}")
    print(f"Using ZMK from: {zmk_path}")
    print(f"Results will be placed in: {results_dir}")
    
    # Ensure results directory exists
    os.makedirs(results_dir, exist_ok=True)
    
    # Setup ZMK environment first to ensure all modules are available
    setup_zmk(zmk_path, root_dir, docker_image)
    
    # Check prerequisites after setup to ensure all modules are available
    prereqs_ok = check_prerequisites(config_path, keyboard_name, zmk_path, exit_on_error=False)
    if not prereqs_ok:
        print("Retrying prerequisites check after ZMK setup...")
        # Try one more time after setup
        if not check_prerequisites(config_path, keyboard_name, zmk_path):
            print("Error: Prerequisites check failed even after ZMK setup")
            sys.exit(1)
    
    # Clean previous builds
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    os.makedirs(build_dir, exist_ok=True)
    
    # Generate build info
    print("Creating compile-time macro")
    generate_build_info(script_dir)
    
    # Debug output for build flags
    print(f"Build flags: LEFT={build_left}, RIGHT={build_right}")
    
    # Build firmware for selected sides
    build_opts = {
        "shield_type": shield_type,
        "device_name": args.device_name,
        "usb_debugging": usb_debugging,
        "firmware_type": firmware_type,
        "build_dir_suffix_left": build_dir_suffix_left,
        "build_dir_suffix_right": build_dir_suffix_right
    }
    if build_left:
        build_firmware("left", build_command_left, docker_image, zmk_path, root_dir, timing_callback=save_build_stat, build_opts=build_opts)
    
    if build_right:
        build_firmware("right", build_command_right, docker_image, zmk_path, root_dir, timing_callback=save_build_stat, build_opts=build_opts)
    
    print("Build complete!")
    
    # Copy firmware files to results directory
    if build_left:
        copy_firmware("Left", build_output_left, result_firmware_left, results_dir, root_dir)
    
    if build_right:
        copy_firmware("Right", build_output_right, result_firmware_right, results_dir, root_dir)


if __name__ == "__main__":
    main()
