#!/usr/bin/env python3

"""
ZMK Firmware Flashing Script for Corne Keyboard (Python Version)

This script flashes ZMK firmware to a Corne keyboard using the device
information from devices.conf. It uses find_devices.py to locate the
appropriate device.

Usage: ./flash_firmware.py [options]
Options:
  --side=SIDE      Specify side (left or right, default: left)
  --variant=TYPE   Specify firmware variant (default or gem, default: default)
  --device=NAME    Device to flash (from devices.conf, default: corne_ergokeeb)
  --help           Show this help message
"""

import os
import sys
import argparse
import subprocess
import yaml
import time
import shutil
from pathlib import Path

# Default values
DEFAULT_SIDE = "left"
DEFAULT_VARIANT = "default"
DEFAULT_DEVICE = "corne_ergokeeb"
DEFAULT_MOUNT_POINT = os.path.expanduser("~/mnt/corne")
DEFAULT_DESTINATION_FIRMWARE_NAME = "CURRENT.UF2"
DEFAULT_READY_TIME = 20  # seconds to wait for flashing to complete


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


def find_device(script_dir, debug=False):
    """Find the appropriate device using find_devices.py"""
    find_devices_script = os.path.join(script_dir, "find_devices.py")
    
    # Check if the script exists
    if not os.path.isfile(find_devices_script):
        print(f"Error: find_devices.py not found at {find_devices_script}")
        sys.exit(1)
    
    try:
        # Run find_devices.py to locate the device
        cmd = [sys.executable, find_devices_script]  # Use sys.executable to ensure correct Python interpreter
        if debug:
            cmd.append("--debug")
            
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        # The script outputs the device path to stdout
        output = result.stdout.strip()
        
        # Parse the output to get the device path
        # find_devices.py outputs the device path on its own line
        device_paths = [line for line in output.split('\n') if line.startswith('/dev/')]
        
        if not device_paths:
            print("No bootloader device found")
            if debug:
                print(f"find_devices.py output: {output}")
            sys.exit(1)
        
        # Use the first device found
        device_path = device_paths[0]
        print(f"Found bootloader device: {device_path}")
        return device_path
    except subprocess.CalledProcessError as e:
        print(f"Error running find_devices.py: {e}")
        if e.stdout:
            print(f"Output: {e.stdout}")
        if e.stderr:
            print(f"Error: {e.stderr}")
        sys.exit(1)


def verify_device(device_path, device_config, debug=False):
    """Verify that the found device matches the expected device configuration"""
    if not os.path.exists(device_path):
        print(f"Error: Device path {device_path} does not exist")
        sys.exit(1)
    
    try:
        # Use udevadm to get device information
        udev_info = subprocess.run(
            ['udevadm', 'info', '--query=all', '--name', device_path],
            capture_output=True,
            text=True,
            check=True
        )
        
        # Extract vendor and product IDs
        vendor_id = None
        product_id = None
        
        for line in udev_info.stdout.splitlines():
            if "ID_VENDOR_ID=" in line:
                vendor_id = line.split('=')[1].strip('"').lower()
            elif "ID_USB_VENDOR_ID=" in line:
                vendor_id = line.split('=')[1].strip('"').lower()
            elif "ID_MODEL_ID=" in line:
                product_id = line.split('=')[1].strip('"').lower()
            elif "ID_USB_MODEL_ID=" in line:
                product_id = line.split('=')[1].strip('"').lower()
        
        if debug:
            print(f"Found device: vendor_id={vendor_id}, product_id={product_id}")
            print(f"Expected: vendor_id={device_config.get('vendor_id', '').lower()}, "
                  f"product_id={device_config.get('product_id', '').lower()}")
        
        # Verify that the device matches the expected configuration
        if (vendor_id != device_config.get('vendor_id', '').lower() or
                product_id != device_config.get('product_id', '').lower()):
            print(f"Warning: Device at {device_path} does not match expected configuration")
            print(f"Found: vendor_id={vendor_id}, product_id={product_id}")
            print(f"Expected: vendor_id={device_config.get('vendor_id', '')}, "
                  f"product_id={device_config.get('product_id', '')}")
            
            response = input("Continue anyway? (y/n): ")
            if response.lower() != 'y':
                sys.exit(1)
        
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error verifying device: {e}")
        if e.stdout:
            print(f"Output: {e.stdout}")
        if e.stderr:
            print(f"Error: {e.stderr}")
        sys.exit(1)


def flash_firmware(device_path, firmware_path, mount_point, destination_name, ready_time):
    """Flash the firmware to the device"""
    # Check if firmware file exists
    if not os.path.isfile(firmware_path):
        print(f"Error: Firmware file not found at {firmware_path}")
        print("Make sure you've built the firmware first")
        sys.exit(1)
    
    print(f"Found bootloader device at: {device_path}")
    
    # Create mount point if it doesn't exist
    os.makedirs(mount_point, exist_ok=True)
    
    try:
        # Mount the device
        print(f"Mounting {device_path} to {mount_point}")
        subprocess.run(['sudo', 'mount', device_path, mount_point], check=True)
        
        # Copy the firmware
        print(f"Copying firmware from {firmware_path} to {os.path.join(mount_point, destination_name)}")
        subprocess.run(['sudo', 'cp', firmware_path, os.path.join(mount_point, destination_name)], check=True)
        
        # Wait for flashing to complete
        print(f"Flashing firmware... please wait {ready_time} seconds")
        time.sleep(ready_time)
        
        # Unmount the device
        print("Unmounting device")
        subprocess.run(['sudo', 'umount', mount_point], check=True)
        
        print("Flashing complete!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error flashing firmware: {e}")
        # Try to unmount the device if it was mounted
        try:
            subprocess.run(['sudo', 'umount', mount_point], check=False)
        except:
            pass
        sys.exit(1)


def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="ZMK Firmware Flashing Script for Corne Keyboard")
    parser.add_argument("--side", dest="side", default=DEFAULT_SIDE,
                        help=f"Specify side (left or right, default: {DEFAULT_SIDE})")
    parser.add_argument("--variant", dest="variant", default=DEFAULT_VARIANT,
                        help=f"Specify firmware variant (default or gem, default: {DEFAULT_VARIANT})")
    parser.add_argument("--device", dest="device_name", default=DEFAULT_DEVICE,
                        help=f"Device to flash (from devices.conf, default: {DEFAULT_DEVICE})")
    parser.add_argument("--debug", dest="debug", action="store_true",
                        help="Enable debug output")
    parser.add_argument("--mount-point", dest="mount_point", default=DEFAULT_MOUNT_POINT,
                        help=f"Mount point for the device (default: {DEFAULT_MOUNT_POINT})")
    parser.add_argument("--ready-time", dest="ready_time", type=int, default=DEFAULT_READY_TIME,
                        help=f"Time to wait for flashing to complete in seconds (default: {DEFAULT_READY_TIME})")
    
    args = parser.parse_args()
    
    # Validate side
    if args.side not in ["left", "right"]:
        print(f"Error: Side must be 'left' or 'right', got '{args.side}'")
        sys.exit(1)
    
    # Validate variant
    if args.variant not in ["default", "gem"]:
        print(f"Error: Variant must be 'default' or 'gem', got '{args.variant}'")
        sys.exit(1)
    
    # Get the directory of this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Find CorneZMK root directory
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
        print("Available devices:")
        for device_name in devices_config.get('devices', {}).keys():
            print(f"  - {device_name}")
        sys.exit(1)
    
    # Get device configuration
    device_config = devices_config['devices'][args.device_name]
    
    # Get keyboard name from device config
    keyboard_name = device_config.get('keyboard_name')
    if not keyboard_name:
        print(f"Error: No keyboard_name specified for device '{args.device_name}' in devices.conf")
        sys.exit(1)
    
    # Determine firmware file based on options
    firmware_config = device_config.get('firmware', {})
    
    if args.variant == "default":
        firmware_type = "standard"
    elif args.variant == "gem":
        firmware_type = "nice_view_gem"
    else:
        firmware_type = args.variant
    
    # Get firmware filename from config
    if firmware_type in firmware_config:
        if isinstance(firmware_config[firmware_type], dict):
            firmware_file = firmware_config[firmware_type].get(args.side)
            if not firmware_file:
                print(f"Error: No firmware file specified for {args.side} side with variant {args.variant}")
                sys.exit(1)
        else:
            # Single firmware file (e.g., for dongle)
            firmware_file = firmware_config[firmware_type]
    else:
        # Fallback to default naming convention
        firmware_file = f"{keyboard_name}_{args.side}.uf2"
    
    # Set the firmware path
    results_dir = os.path.join(root_dir, "results")
    firmware_path = os.path.join(results_dir, firmware_file)
    
    print(f"Flashing {args.side} side with {args.variant} firmware: {firmware_path}")
    
    # Find the bootloader device
    device_path = find_device(script_dir, args.debug)
    
    # Verify the device
    verify_device(device_path, device_config, args.debug)
    
    # Flash the firmware
    flash_firmware(
        device_path,
        firmware_path,
        args.mount_point,
        DEFAULT_DESTINATION_FIRMWARE_NAME,
        args.ready_time
    )


if __name__ == "__main__":
    main()
