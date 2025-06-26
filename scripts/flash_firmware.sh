#!/bin/bash

# Default values
SIDE="left"
VARIANT="default"
MOUNT_POINT=~/mnt/corne
DESTINATION_FIRMWARE_NAME=CURRENT.UF2
READY_TIME=20

# Help message
show_help() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  -s, --side <left|right>     Specify side (left or right, default: left)"
    echo "  -v, --variant <default|gem> Specify firmware variant (default or gem, default: default)"
    echo "  -h, --help                  Show this help message"
    exit 0
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -s|--side)
            SIDE="$2"
            if [[ "$SIDE" != "left" && "$SIDE" != "right" ]]; then
                echo "Error: Side must be 'left' or 'right'"
                exit 1
            fi
            shift 2
            ;;
        -v|--variant)
            VARIANT="$2"
            if [[ "$VARIANT" != "default" && "$VARIANT" != "gem" ]]; then
                echo "Error: Variant must be 'default' or 'gem'"
                exit 1
            fi
            shift 2
            ;;
        -h|--help)
            show_help
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            ;;
    esac
done

# Determine firmware file based on options
if [[ "$VARIANT" == "default" ]]; then
    NEW_FIRMWARE="results/ergokeeb_corne_${SIDE}.uf2"
else
    NEW_FIRMWARE="results/ergokeeb_corne_${SIDE}_gem.uf2"
fi

echo "Flashing ${SIDE} side with ${VARIANT} firmware: ${NEW_FIRMWARE}"

# Get the absolute path to find_device.sh in the same directory as this script
FIND_DEVICE_SCRIPT="$(dirname "$(readlink -f "$0")")/find_device.sh"

# Make sure the script exists and is executable
if [ ! -x "$FIND_DEVICE_SCRIPT" ]; then
    echo "Error: Could not find executable find_device.sh at $FIND_DEVICE_SCRIPT"
    exit 1
fi

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

echo "Found nice!nano at: $DEVICE"
mkdir -p "$MOUNT_POINT"
sudo mount "$DEVICE" "$MOUNT_POINT"
sudo cp "$NEW_FIRMWARE" "$MOUNT_POINT/$DESTINATION_FIRMWARE_NAME"
echo "Flashing firmware... please wait"
sleep $READY_TIME
sudo umount "$MOUNT_POINT"
echo "Flashing complete!"
