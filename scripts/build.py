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
import yaml
import shutil
from pathlib import Path
import platform



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


def check_prerequisites(config_path, keyboard_name):
    """Check if required directories and files exist"""
    # Check config repo structure
    if not os.path.isdir(config_path):
        print(f"Error: Config directory not found at {config_path}")
        sys.exit(1)

    if not os.path.isfile(os.path.join(config_path, f"{keyboard_name}.keymap")):
        print(f"Error: {keyboard_name}.keymap not found in {config_path}")
        sys.exit(1)

    # Check for custom board definitions
    if not os.path.isdir(os.path.join(root_dir, "boards", "arm", keyboard_name)):
        print(f"Error: Custom board definition not found at {os.path.join(root_dir, 'boards', 'arm', keyboard_name)}")
        sys.exit(1)


def setup_zmk(zmk_path, root_dir, docker_image):
    """Setup ZMK environment"""
    # Ensure ZMK directory exists
    if not os.path.isdir(zmk_path):
        print("Creating ZMK directory...")
        os.makedirs(zmk_path, exist_ok=True)

    # Clone ZMK if not present
    if not os.path.isdir(os.path.join(zmk_path, "app")):
        print("ZMK not found. Cloning ZMK repository...")
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
        
        subprocess.run(cmd, check=True)

    # Copy west.yml file
    shutil.copy(os.path.join(root_dir, "config", "west.yml"), os.path.join(zmk_path, "app", "west.yml"))

    # Update ZMK dependencies
    print("Updating ZMK dependencies...")
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
        "bash", "-c", "git config --global --add safe.directory '*' && west update"
    ]
    
    subprocess.run(cmd, check=True)


def build_firmware(side, build_command, docker_image, zmk_path, root_dir):
    """Build firmware for a specific side"""
    print(f"Building {side} side firmware")
    user_id = os.getuid()
    group_id = os.getgid()
    
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{zmk_path}:/zmk",
        "-v", f"{root_dir}:/workspace",
        "-w", "/zmk/app",
        "-e", "ZEPHYR_BASE=/zmk/zephyr",
        "-e", "BOARD_ROOT=/workspace",
        "--user", f"{user_id}:{group_id}",
        docker_image
    ]
    
    # Add the build command as separate arguments
    cmd.extend(build_command.split())
    
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        print(f"Error: Failed to build {side} side firmware")
        sys.exit(1)


def copy_firmware(side, build_output, result_firmware, results_dir):
    """Copy firmware files to results directory"""
    if os.path.isfile(build_output):
        # Create results directory if it doesn't exist
        os.makedirs(results_dir, exist_ok=True)
        shutil.copy(build_output, os.path.join(results_dir, result_firmware))
        print(f"{side} side firmware: {os.path.join(results_dir, result_firmware)}")
    else:
        print(f"Warning: {side} side firmware not found at {build_output}")


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


def main():
    # Parse command line arguments
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
    zmk_path = os.path.join(root_dir, "zmk-firmware")
    
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
    
    # Check prerequisites
    check_prerequisites(config_path, keyboard_name)
    
    # Setup ZMK environment
    setup_zmk(zmk_path, root_dir, docker_image)
    
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
    if build_left:
        build_firmware("left", build_command_left, docker_image, zmk_path, root_dir)
    
    if build_right:
        build_firmware("right", build_command_right, docker_image, zmk_path, root_dir)
    
    print("Build complete!")
    
    # Copy firmware files to results directory
    if build_left:
        copy_firmware("Left", build_output_left, result_firmware_left, results_dir)
    
    if build_right:
        copy_firmware("Right", build_output_right, result_firmware_right, results_dir)


if __name__ == "__main__":
    main()
