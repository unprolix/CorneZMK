#!/bin/bash

# Default values
MOUNT_POINT=~/mnt/corne
DESTINATION_FIRMWARE_NAME=CURRENT.UF2
READY_TIME=20
# Get the real directory where this script is located, resolving symlinks
get_script_dir() {
    local source="${BASH_SOURCE[0]}"
    local dir=""
    
    # Resolve $source until the file is no longer a symlink
    while [ -L "$source" ]; do
        dir="$(cd -P "$(dirname "$source")" && pwd)"
        source="$(readlink "$source")"
        # If $source was a relative symlink, we need to resolve it relative to the path where the symlink file was located
        [[ $source != /* ]] && source="$dir/$source"
    done
    
    dir="$(cd -P "$(dirname "$source")" && pwd)"
    echo "$dir"
}

SCRIPT_DIR="$(get_script_dir)"
REPO_BASE_DIR="$(dirname "$SCRIPT_DIR")"
RESULTS_DIR="$REPO_BASE_DIR/results"

FIND_DEVICE_SCRIPT="$SCRIPT_DIR/find_nicenano.sh"
NEW_FIRMWARE="${RESULTS_DIR}/zmk_dongle.uf2"


# Help message
show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -h, --help                  Show this help message"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            ;;
    esac
done

echo "Flashing dongle with firmware: ${NEW_FIRMWARE}"

# Check if firmware file exists
if [ ! -f "$NEW_FIRMWARE" ]; then
    echo "Error: Firmware file not found at $NEW_FIRMWARE"
    echo "Make sure you've built the firmware first"
    exit 1
fi

# Call the find_device.sh script
DEVICE=$("$FIND_DEVICE_SCRIPT")
if [ $? -ne 0 ]; then
    echo "No nice!nano found"
    exit 1
fi

echo "Found dongle at: $DEVICE"
mkdir -p "$MOUNT_POINT"
sudo mount "$DEVICE" "$MOUNT_POINT"
sudo cp "$NEW_FIRMWARE" "$MOUNT_POINT/$DESTINATION_FIRMWARE_NAME"
echo "Flashing firmware... please wait"
sleep $READY_TIME
sudo umount "$MOUNT_POINT"
echo "Flashing complete!"
