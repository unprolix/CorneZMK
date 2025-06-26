#!/bin/bash
MOUNT_POINT=~/mnt/corne
NEW_FIRMWARE=results/ergokeeb_corne_left.uf2
DESTINATION_FIRMWARE_NAME=CURRENT.UF2
READY_TIME=20

# Get the absolute path to find_device.sh in the same directory as this script
FIND_DEVICE_SCRIPT="$(dirname "$(readlink -f "$0")")/find_device.sh"

# Make sure the script exists and is executable
if [ ! -x "$FIND_DEVICE_SCRIPT" ]; then
    echo "Error: Could not find executable find_device.sh at $FIND_DEVICE_SCRIPT"
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
sleep $READY_TIME
sudo umount "$MOUNT_POINT"
