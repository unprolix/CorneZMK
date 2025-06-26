#!/bin/bash

# nice_nano_finder.sh - Find nice!nano devices in various modes

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

# Device constants
# get these by looking at output of `lsusb`
readonly VENDOR_ID="239a"
readonly MODEL_ID="00b3"

# used for display, not for identification
readonly DEVICE_NAME="nice!nano"

find_device() {
   local found=false
   local found_dev=
   local debug=${DEBUG:-false}
   
   if [[ "$debug" == true ]]; then
       echo "Looking for ${DEVICE_NAME} with vendor ID ${VENDOR_ID} and model ID ${MODEL_ID}"
   fi
   
   if lsusb | grep -q "${VENDOR_ID}:${MODEL_ID}"; then
       if [[ "$debug" == true ]]; then
           echo "Found ${DEVICE_NAME} in lsusb:"
           lsusb | grep "${VENDOR_ID}:${MODEL_ID}"
       fi
       found=true
   fi
   
   for dev in /sys/block/*; do
       if [[ -e "$dev" ]]; then
           local device=$(basename "$dev")
           local devpath="/dev/$device"
           
           if [[ -b "$devpath" ]]; then
               if [[ "$debug" == true ]]; then
                   echo "Checking block device: $devpath"
               fi
               
               local udev_info=$(udevadm info --query=all --name="$devpath" 2>/dev/null)
               
               # Check both ID_VENDOR_ID and ID_USB_VENDOR_ID
               if echo "$udev_info" | grep -E "(ID_VENDOR_ID=${VENDOR_ID}|ID_USB_VENDOR_ID=${VENDOR_ID})" >/dev/null; then
                   # Check both ID_MODEL_ID and ID_USB_MODEL_ID
                   if echo "$udev_info" | grep -E "(ID_MODEL_ID=${MODEL_ID}|ID_USB_MODEL_ID=${MODEL_ID})" >/dev/null; then
                       if [[ "$debug" == true ]]; then
                           echo "Found ${DEVICE_NAME} at $devpath:"
                           lsblk "$devpath"
                           echo "Device info:"
                           echo "$udev_info" | grep -E "(ID_VENDOR|ID_MODEL|ID_SERIAL|ID_USB)"
                       fi
                       found=true
                       found_dev=$devpath
                   fi
               fi
           fi
       fi
   done
   
   if [[ "$found" == false ]]; then
       echo "No ${DEVICE_NAME} devices found"
       return 1
   fi
   
   echo $found_dev
   return 0
}

find_device
