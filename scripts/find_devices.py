#!/usr/bin/env python3

import os
import sys
import yaml
import subprocess
import re
import argparse
from pathlib import Path

def get_script_dir():
    """Get the directory where this script is located, resolving symlinks."""
    script_path = os.path.realpath(__file__)
    return os.path.dirname(script_path)

def load_devices_config():
    """Load the devices configuration from the devices.conf file."""
    script_dir = get_script_dir()
    repo_root = os.path.dirname(os.path.dirname(script_dir))
    config_path = os.path.join(repo_root, "CorneZMK", "etc", "devices.conf")
    
    # If the path doesn't exist, try a relative path from the current directory
    if not os.path.exists(config_path):
        config_path = os.path.join(repo_root, "etc", "devices.conf")
    
    # If still not found, try an absolute path
    if not os.path.exists(config_path):
        config_path = "/home/jjb/src/zmk/CorneZMK/etc/devices.conf"
    
    if not os.path.exists(config_path):
        print(f"Error: Could not find devices.conf at {config_path}", file=sys.stderr)
        sys.exit(1)
    
    with open(config_path, 'r') as f:
        # Skip comments at the beginning of the file
        content = ""
        for line in f:
            if not line.strip().startswith('#') or content:
                content += line
        
        try:
            config = yaml.safe_load(content)
            return config.get('devices', {})
        except yaml.YAMLError as e:
            print(f"Error parsing devices.conf: {e}", file=sys.stderr)
            sys.exit(1)

def find_matching_devices(devices_config, debug=False, list_all=False):
    """Find bootloader devices that match the configurations in devices.conf."""
    matching_devices = []
    all_devices = []
    
    if debug:
        print("\nScanning for bootloader devices...")
        # Show all block devices for debugging
        print("Available block devices:")
        try:
            result = subprocess.check_output(['ls', '-la', '/dev/sd*'], universal_newlines=True, stderr=subprocess.PIPE)
            print(result)
        except subprocess.CalledProcessError as e:
            print(f"No /dev/sd* devices found: {e.stderr if hasattr(e, 'stderr') else ''}")
    
    # First try direct USB device detection
    try:
        if debug:
            print("\nChecking USB devices directly...")
        
        # Get list of USB devices using lsusb
        lsusb_output = subprocess.check_output(['lsusb'], universal_newlines=True)
        
        # Parse lsusb output to find matching devices
        for line in lsusb_output.splitlines():
            match = re.search(r'ID (\w+):(\w+)', line)
            if match:
                vendor_id = match.group(1).lower()
                product_id = match.group(2).lower()
                
                if debug:
                    print(f"Found USB device: vendor_id={vendor_id}, product_id={product_id}")
                
                # Check if this device matches any in our config
                for nickname, device_info in devices_config.items():
                    if (device_info.get('vendor_id', '').lower() == vendor_id and 
                        device_info.get('product_id', '').lower() == product_id):
                        
                        # For matching USB devices, try to find corresponding block device
                        if debug:
                            print(f"USB device matches config: {nickname} ({vendor_id}:{product_id})")
                            print(f"Searching for corresponding block device...")
                        
                        # Try to find a block device with matching vendor/product ID
                        for sd_path in Path('/sys/block').glob('sd*'):
                            sd_device = f"/dev/{sd_path.name}"
                            try:
                                udev_info = subprocess.check_output(
                                    ['udevadm', 'info', '--query=all', '--name', sd_device],
                                    stderr=subprocess.DEVNULL,
                                    universal_newlines=True
                                )
                                
                                # Check if this block device has matching vendor/product ID
                                if (f"ID_VENDOR_ID={vendor_id}" in udev_info or 
                                    f"ID_USB_VENDOR_ID={vendor_id}" in udev_info) and \
                                   (f"ID_MODEL_ID={product_id}" in udev_info or 
                                    f"ID_USB_MODEL_ID={product_id}" in udev_info):
                                    
                                    matching_devices.append((nickname, sd_device))
                                    if debug:
                                        print(f"Found matching block device: {nickname} -> {sd_device}")
                            except subprocess.CalledProcessError:
                                continue
    except subprocess.CalledProcessError:
        if debug:
            print("Failed to run lsusb command")
    
    # Also check all block devices directly - focusing on removable storage devices
    for dev_path in Path('/sys/block').glob('*'):
        device_name = dev_path.name
        device_path = f"/dev/{device_name}"
        
        # Skip devices that don't exist or aren't block devices
        if not os.path.exists(device_path):
            if debug:
                print(f"Device path does not exist: {device_path}")
            continue
            
        if not device_path.startswith("/dev/sd"):
            if debug:
                print(f"Skipping non-sd device: {device_path}")
            continue
            
        # Get device information using udevadm
        try:
            udev_info = subprocess.check_output(
                ['udevadm', 'info', '--query=all', '--name', device_path],
                stderr=subprocess.DEVNULL,
                universal_newlines=True
            )
        except subprocess.CalledProcessError:
            continue
            
        if debug:
            print(f"Checking block device: {device_path}")
        
        # Extract vendor and product IDs from udevadm output
        vendor_id = None
        product_id = None
        removable = False
        
        for line in udev_info.splitlines():
            if "ID_VENDOR_ID" in line or "ID_USB_VENDOR_ID" in line:
                match = re.search(r'=([\da-fA-F]+)', line)
                if match:
                    vendor_id = match.group(1).lower()
            elif "ID_MODEL_ID" in line or "ID_USB_MODEL_ID" in line:
                match = re.search(r'=([\da-fA-F]+)', line)
                if match:
                    product_id = match.group(1).lower()
            elif "ATTR{removable}" in line:
                match = re.search(r'="(\d+)"', line)
                if match and match.group(1) == "1":
                    removable = True
        
        # Only consider removable devices (typical for bootloader mode)
        if not removable and not device_path.startswith("/dev/sd"):
            if debug:
                print(f"Skipping non-removable device: {device_path}")
            continue
        
        if vendor_id and product_id:
            # Get device description if available
            description = "Unknown"
            for line in udev_info.splitlines():
                if "ID_MODEL=" in line:
                    match = re.search(r'=(.*)', line)
                    if match:
                        description = match.group(1)
                        break
                        
            if list_all:
                all_devices.append((vendor_id, product_id, device_path, description))
                
            # Check if this device matches any in our config
            for nickname, device_info in devices_config.items():
                if (device_info.get('vendor_id', '').lower() == vendor_id and 
                    device_info.get('product_id', '').lower() == product_id):
                    matching_devices.append((nickname, device_path))
                    if debug:
                        print(f"Found bootloader device: {nickname} -> {device_path} ({vendor_id}:{product_id})")
    
    # We're only looking for bootloader devices, which appear as block devices
    # So we don't need to check for USB devices that aren't mounted as block devices
    
    if list_all:
        return matching_devices, all_devices
    return matching_devices

def check_bootloader_device(device_path, debug=False):
    """Check if a device is in bootloader mode by examining its properties."""
    try:
        # Get device information using udevadm
        udev_info = subprocess.check_output(
            ['udevadm', 'info', '--query=all', '--name', device_path],
            stderr=subprocess.DEVNULL,
            universal_newlines=True
        )
        
        # Characteristics of bootloader devices:
        # 1. Usually removable
        # 2. Often have specific vendor/product IDs
        # 3. Usually appear as a mass storage device
        removable = False
        is_usb = False
        vendor_id = None
        product_id = None
        
        for line in udev_info.splitlines():
            if "ATTR{removable}" in line and "=\"1\"" in line:
                removable = True
            elif "ID_BUS=\"usb\"" in line:
                is_usb = True
            elif "ID_VENDOR_ID" in line or "ID_USB_VENDOR_ID" in line:
                match = re.search(r'=\"([\da-fA-F]+)\"', line)
                if match:
                    vendor_id = match.group(1).lower()
            elif "ID_MODEL_ID" in line or "ID_USB_MODEL_ID" in line:
                match = re.search(r'=\"([\da-fA-F]+)\"', line)
                if match:
                    product_id = match.group(1).lower()
        
        # A device is likely in bootloader mode if it's removable, USB, and has vendor/product IDs
        is_bootloader = removable and is_usb and vendor_id and product_id
        
        if debug and is_bootloader:
            print(f"Device {device_path} appears to be in bootloader mode:")
            print(f"  Vendor ID: {vendor_id}, Product ID: {product_id}")
            print(f"  Removable: {removable}, USB: {is_usb}")
        
        if is_bootloader:
            return True, vendor_id, product_id
        return False, None, None
        
    except subprocess.CalledProcessError:
        return False, None, None

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Find ZMK devices in bootloader mode from devices.conf')
    parser.add_argument('--debug', action='store_true', help='Enable debug output')
    parser.add_argument('--list-all', action='store_true', help='List all bootloader devices')
    parser.add_argument('--show-config', action='store_true', help='Show parsed device configuration')
    parser.add_argument('--raw-usb', action='store_true', help='Show raw USB device information')
    args = parser.parse_args()
    
    # Load device configurations
    devices_config = load_devices_config()
    
    if args.show_config or args.debug:
        print("\nLoaded device configurations:")
        for nickname, info in devices_config.items():
            print(f"  {nickname}: vendor_id={info.get('vendor_id', 'N/A')} product_id={info.get('product_id', 'N/A')}")
    
    # Show raw USB device information if requested
    if args.raw_usb or args.debug:
        try:
            print("\nRaw USB device information:")
            lsusb_output = subprocess.check_output(['lsusb'], universal_newlines=True)
            print(lsusb_output)
        except subprocess.CalledProcessError:
            print("Failed to run lsusb command")
    
    # Direct check of block devices
    if args.debug:
        print("\nDirect check of block devices:")
        try:
            result = subprocess.check_output(['ls', '-la', '/dev/sd*'], universal_newlines=True)
            print(result)
        except subprocess.CalledProcessError as e:
            print(f"No /dev/sd* devices found")
    
    # Scan for bootloader devices
    matching_devices = []
    all_devices = []
    
    # Check all potential block devices that might be in bootloader mode
    for dev_path in Path('/sys/block').glob('sd*'):
        device_path = f"/dev/{dev_path.name}"
        
        if args.debug:
            print(f"Checking potential bootloader device: {device_path}")
        
        # Get device information using udevadm
        try:
            udev_info = subprocess.check_output(
                ['udevadm', 'info', '--query=all', '--name', device_path],
                stderr=subprocess.DEVNULL,
                universal_newlines=True
            )
            
            # Extract vendor and product IDs and serial number
            vendor_id = None
            product_id = None
            serial = None
            description = "Unknown"
            
            for line in udev_info.splitlines():
                if "ID_VENDOR_ID=" in line:
                    vendor_id = line.split('=')[1].strip('"').lower()
                elif "ID_USB_VENDOR_ID=" in line:
                    vendor_id = line.split('=')[1].strip('"').lower()
                elif "ID_MODEL_ID=" in line:
                    product_id = line.split('=')[1].strip('"').lower()
                elif "ID_USB_MODEL_ID=" in line:
                    product_id = line.split('=')[1].strip('"').lower()
                elif "ID_MODEL=" in line:
                    description = line.split('=')[1].strip('"')
            
            if args.debug and vendor_id and product_id:
                print(f"  Found device with vendor_id={vendor_id}, product_id={product_id}")
            
            # Check if this device matches any in our config
            if vendor_id and product_id:
                for nickname, device_info in devices_config.items():
                    config_vendor_id = device_info.get('vendor_id', '').lower()
                    config_product_id = device_info.get('product_id', '').lower()
                    
                    if args.debug:
                        print(f"  Comparing with {nickname}: {config_vendor_id}:{config_product_id}")
                    
                    if config_vendor_id == vendor_id and config_product_id == product_id:
                        matching_devices.append((nickname, device_path))
                        if args.debug:
                            print(f"  MATCH FOUND: {nickname} -> {device_path}")
                
                # Add to all devices list if requested
                if args.list_all:
                    all_devices.append((vendor_id, product_id, device_path, description))
        except subprocess.CalledProcessError:
            if args.debug:
                print(f"  Failed to get udev info for {device_path}")
    
    # Display results
    if matching_devices:
        for nickname, device_path in matching_devices:
            if args.debug:
                print(f"{nickname}: {device_path}")
            else:
                print(f"{device_path}")
    elif args.debug:
        print("No matching bootloader devices found")
        
    # Display all bootloader devices if requested
    if args.list_all and all_devices:
        print("\nAll bootloader devices:")
        for vendor_id, product_id, device_path, description in all_devices:
            print(f"{device_path} (vendor_id={vendor_id}, product_id={product_id}) - {description}")
            
    if args.debug and not matching_devices:
        print("\nNo matches found. Check if the device is in bootloader mode and properly connected.")
        print("Also verify that the vendor_id and product_id in devices.conf match your device.")
        print("You can use 'lsusb' to see connected USB devices and their IDs.")

if __name__ == "__main__":
    main()
