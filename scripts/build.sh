#!/bin/bash

#############################################################
# ZMK Firmware Build Script for Corne Keyboard
# 
# This script builds ZMK firmware for the Corne keyboard with
# options to build only left side, only right side, or both.
#
# Usage: ./build.sh [options]
# Options:
#   --shield=TYPE    Shield type to build (nice_view or nice_view_gem)
#   --left-only      Build only left side
#   --right-only     Build only right side
#   --help           Show this help message
#############################################################

# Exit on any error
set -e

# Enable command tracing if DEBUG environment variable is set
if [[ -n "$DEBUG" ]]; then
  set -x
fi

#############################################################
# Function Definitions
#############################################################

# Display help message
show_help() {
  echo "Usage: $0 [options]"
  echo "Options:"
  echo "  --shield=TYPE    Shield type to build (nice_view or nice_view_gem)"
  echo "  --left-only      Build only left side"
  echo "  --right-only     Build only right side"
  echo "  --help           Show this help message"
  exit 0
}

# Check if required directories and files exist
check_prerequisites() {
  # Check config repo structure
  if [ ! -d "${CONFIG_PATH}" ]; then
    echo "Error: Config directory not found at ${CONFIG_PATH}"
    exit 1
  fi

  if [ ! -f "${CONFIG_PATH}/${KEYBOARD_NAME}.keymap" ]; then
    echo "Error: ${KEYBOARD_NAME}.keymap not found in ${CONFIG_PATH}"
    exit 1
  fi

  # Check for custom board definitions
  if [ ! -d "${ROOT_DIR}/boards/arm/${KEYBOARD_NAME}" ]; then
    echo "Error: Custom board definition not found at ${ROOT_DIR}/boards/arm/${KEYBOARD_NAME}"
    exit 1
  fi
}

# Setup ZMK environment
setup_zmk() {
  # Ensure ZMK directory exists
  if [ ! -d "${ZMK_PATH}" ]; then
    echo "Creating ZMK directory..."
    mkdir -p "${ZMK_PATH}"
  fi

  # Clone ZMK if not present
  if [ ! -d "${ZMK_PATH}/app" ]; then
    echo "ZMK not found. Cloning ZMK repository..."
    git clone https://github.com/zmkfirmware/zmk.git "${ZMK_PATH}"
  fi

  # Check if ZMK directory has correct ownership
  if [ -d "${ZMK_PATH}" ]; then
    # Check if any files are owned by root
    if find "${ZMK_PATH}" -user root -print -quit 2>/dev/null | grep -q .; then
      echo "Fixing ZMK directory ownership..."
      if ! sudo chown -R ${USER_ID}:${GROUP_ID} "${ZMK_PATH}"; then
        echo "Error: Failed to fix ZMK directory ownership. Please run: sudo chown -R $(id -u):$(id -g) ${ZMK_PATH}"
        exit 1
      fi
    fi
  fi

  # Initialize ZMK workspace if needed
  if [ ! -f "${ZMK_PATH}/.west/config" ]; then
    echo "Initializing ZMK workspace..."
    docker run --rm \
      -v ${ZMK_PATH}:/zmk \
      -w /zmk \
      -e GIT_CONFIG_COUNT=1 \
      -e GIT_CONFIG_KEY_0=safe.directory \
      -e GIT_CONFIG_VALUE_0=/zmk \
      --user ${USER_ID}:${GROUP_ID} \
      ${DOCKER_IMAGE} \
      bash -c "git config --global --add safe.directory '*' && west init -l app"
  fi

  # Copy west.yml file
  cp ${ROOT_DIR}/config/west.yml ${ZMK_PATH}/app/west.yml

  # Update ZMK dependencies
  echo "Updating ZMK dependencies..."
  docker run --rm \
    -v ${ZMK_PATH}:/zmk \
    -w /zmk \
    -e GIT_CONFIG_COUNT=1 \
    -e GIT_CONFIG_KEY_0=safe.directory \
    -e GIT_CONFIG_VALUE_0=/zmk \
    --user ${USER_ID}:${GROUP_ID} \
    ${DOCKER_IMAGE} \
    bash -c "git config --global --add safe.directory '*' && west update"
}

# Build firmware for a specific side
build_firmware() {
  local side=$1
  local build_command=$2
  
  echo "Building ${side} side firmware with ${SHIELD_TYPE} shield"
  if ! docker run --rm \
    -v ${ZMK_PATH}:/zmk \
    -v ${ROOT_DIR}:/workspace \
    -w /zmk/app \
    -e ZEPHYR_BASE=/zmk/zephyr \
    -e BOARD_ROOT=/workspace \
    --user ${USER_ID}:${GROUP_ID} \
    ${DOCKER_IMAGE} \
    ${build_command}; then
    echo "Error: Failed to build ${side} side firmware"
    exit 1
  fi
}

# Copy firmware files to results directory
copy_firmware() {
  local side=$1
  local build_output=$2
  local result_firmware=$3
  
  if [ -f "${build_output}" ]; then
    # Create results directory if it doesn't exist
    mkdir -p "${RESULTS_DIR}"
    cp ${build_output} ${RESULTS_DIR}/${result_firmware}
    echo "${side} side firmware: ${RESULTS_DIR}/${result_firmware}"
  else
    echo "Warning: ${side} side firmware not found at ${build_output}"
  fi
}

#############################################################
# Main Script
#############################################################

# Config repository name
CONFIG_REPO="CorneZMK"

# Keyboard name
KEYBOARD_NAME="ergokeeb_corne"

# Enable USB debugging by default
USB_DEBUGGING="y"

# Default shield type
SHIELD_TYPE="nice_view"

# Default sides to build (both)
BUILD_LEFT=true
BUILD_RIGHT=true


# Get user and group IDs
USER_ID=$(id -u)
GROUP_ID=$(id -g)

# Get the directory of this script
# Get the real path of the script, resolving any symlinks
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
# Get the directory containing the real script
SCRIPT_DIR="$(dirname "${SCRIPT_PATH}")"

# Find CorneZMK root directory
find_root_dir() {
  local current_dir="$1"
  
  # Check if current directory is CorneZMK
  if [[ "${current_dir##*/}" == "CorneZMK" ]]; then
    echo "$current_dir"
    return 0
  fi
  
  # Check if current directory contains CorneZMK
  if [[ -d "$current_dir/CorneZMK" ]]; then
    echo "$current_dir/CorneZMK"
    return 0
  fi
  
  # Check if scripts directory is in current path
  if [[ "${current_dir##*/}" == "scripts" && -d "$current_dir/.." ]]; then
    local parent_dir="$(cd "$current_dir/.." && pwd)"
    if [[ "${parent_dir##*/}" == "CorneZMK" ]]; then
      echo "$parent_dir"
      return 0
    fi
  fi
  
  # Check if we're in zmk/CorneZMK
  if [[ "$current_dir" == *"/zmk/CorneZMK"* ]]; then
    echo "${current_dir%/zmk/CorneZMK*}/zmk/CorneZMK"
    return 0
  fi
  
  # Check if we're in src/zmk/CorneZMK
  if [[ "$current_dir" == *"/src/zmk/CorneZMK"* ]]; then
    echo "${current_dir%/src/zmk/CorneZMK*}/src/zmk/CorneZMK"
    return 0
  fi
  
  return 1
}

# Try to find the root directory
ROOT_DIR=$(find_root_dir "$SCRIPT_DIR")

# If not found, try with current directory
if [[ -z "$ROOT_DIR" ]]; then
  ROOT_DIR=$(find_root_dir "$(pwd)")
  if [[ -z "$ROOT_DIR" ]]; then
    echo "Error: Cannot determine CorneZMK root directory"
    echo "Please run this script from the CorneZMK directory or its scripts subdirectory"
    exit 1
  fi
fi

# ZMK repository path
ZMK_PATH="${ROOT_DIR}/zmk-firmware"

# Docker image for building
DOCKER_IMAGE="zmkfirmware/zmk-build-arm:stable"

# Log paths if DEBUG is enabled
if [[ -n "$DEBUG" ]]; then
  echo "DEBUG: SCRIPT_DIR: ${SCRIPT_DIR}"
  echo "DEBUG: ROOT_DIR: ${ROOT_DIR}"
  echo "DEBUG: ZMK_PATH: ${ZMK_PATH}"
fi

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --shield=*)
      SHIELD_TYPE="${1#*=}"
      ;;
    --left-only)
      BUILD_LEFT=true
      BUILD_RIGHT=false
      echo "Build flag set: left side only"
      ;;
    --right-only)
      BUILD_LEFT=false
      BUILD_RIGHT=true
      echo "Build flag set: right side only"
      ;;
    --help)
      show_help
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
  shift
done

# Validate shield type
if [[ "$SHIELD_TYPE" != "nice_view" && "$SHIELD_TYPE" != "nice_view_gem" ]]; then
  echo "Error: Invalid shield type '$SHIELD_TYPE'. Must be 'nice_view' or 'nice_view_gem'"
  exit 1
fi

# Directory paths
CONFIG_PATH="${ROOT_DIR}/config"
BUILD_DIR="${ROOT_DIR}/build"
RESULTS_DIR="${ROOT_DIR}/results"

# Set build directories and output paths based on shield type
if [[ "$SHIELD_TYPE" == "nice_view" ]]; then
  BUILD_DIR_LEFT=${BUILD_DIR}/${KEYBOARD_NAME}_left
  BUILD_DIR_RIGHT=${BUILD_DIR}/${KEYBOARD_NAME}_right
  RESULT_FIRMWARE_LEFT="${KEYBOARD_NAME}_left.uf2"
  RESULT_FIRMWARE_RIGHT="${KEYBOARD_NAME}_right.uf2"
  BUILD_DIR_SUFFIX_LEFT="${KEYBOARD_NAME}_left"
  BUILD_DIR_SUFFIX_RIGHT="${KEYBOARD_NAME}_right"
else
  # For nice_view_gem
  BUILD_DIR_LEFT=${BUILD_DIR}/${KEYBOARD_NAME}_left_gem
  BUILD_DIR_RIGHT=${BUILD_DIR}/${KEYBOARD_NAME}_right_gem
  RESULT_FIRMWARE_LEFT="${KEYBOARD_NAME}_left_gem.uf2"
  RESULT_FIRMWARE_RIGHT="${KEYBOARD_NAME}_right_gem.uf2"
  BUILD_DIR_SUFFIX_LEFT="${KEYBOARD_NAME}_left_gem"
  BUILD_DIR_SUFFIX_RIGHT="${KEYBOARD_NAME}_right_gem"
fi

BUILD_OUTPUT_LEFT=${BUILD_DIR_LEFT}/zephyr/zmk.uf2
BUILD_OUTPUT_RIGHT=${BUILD_DIR_RIGHT}/zephyr/zmk.uf2

# Set up build command extras based on USB debugging
if [ "$USB_DEBUGGING" = "y" ]; then
  BUILD_COMMAND_EXTRA="--snippet zmk-usb-logging"
else
  BUILD_COMMAND_EXTRA=""
fi

# Set up build commands
BUILD_COMMAND_LEFT="west build -d /workspace/build/${BUILD_DIR_SUFFIX_LEFT} -b ${KEYBOARD_NAME}_left ${BUILD_COMMAND_EXTRA} -- -DSHIELD=${SHIELD_TYPE} -DZMK_CONFIG=/workspace/config"
BUILD_COMMAND_RIGHT="west build -d /workspace/build/${BUILD_DIR_SUFFIX_RIGHT} -b ${KEYBOARD_NAME}_right ${BUILD_COMMAND_EXTRA} -- -DSHIELD=${SHIELD_TYPE} -DZMK_CONFIG=/workspace/config"

echo "Building ZMK firmware for ${KEYBOARD_NAME} with ${SHIELD_TYPE} shield..."
echo "Using ZMK from: ${ZMK_PATH}"
echo "Results will be placed in: ${RESULTS_DIR}"

# Ensure results directory exists
mkdir -p ${RESULTS_DIR}

# Check prerequisites
check_prerequisites

# Setup ZMK environment
setup_zmk

# Clean previous builds
rm -rf ${BUILD_DIR}
mkdir -p ${BUILD_DIR}

# Generate build info
echo "Creating compile-time macro"
# Save current directory
CURRENT_DIR=$(pwd)

# Use absolute path for generate_build_info.sh
GEN_BUILD_INFO_SCRIPT="${SCRIPT_DIR}/generate_build_info.sh"

# Check if the script exists
if [ ! -f "${GEN_BUILD_INFO_SCRIPT}" ]; then
  echo "ERROR: generate_build_info.sh not found at ${GEN_BUILD_INFO_SCRIPT}"
  ls -la "${SCRIPT_DIR}"
  exit 1
fi

# Change to the scripts directory to run generate_build_info.sh
cd "${SCRIPT_DIR}" || { echo "Error: Failed to change to scripts directory"; exit 1; }

# Run the script with full path
"${GEN_BUILD_INFO_SCRIPT}"

# Return to previous directory
cd "${CURRENT_DIR}" || { echo "Error: Failed to return to original directory"; exit 1; }

# Debug output for build flags
echo "Build flags: LEFT=${BUILD_LEFT}, RIGHT=${BUILD_RIGHT}"

# Build firmware for selected sides
# Log build flags if DEBUG is enabled
if [[ -n "$DEBUG" ]]; then
  echo "DEBUG: Build flags before building: LEFT=${BUILD_LEFT}, RIGHT=${BUILD_RIGHT}"
fi

# Build left side if requested
if [[ "$BUILD_LEFT" == "true" ]]; then
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Building left side firmware"; fi
  build_firmware "left" "${BUILD_COMMAND_LEFT}"
else
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Skipping left side build"; fi
fi

# Build right side if requested
if [[ "$BUILD_RIGHT" == "true" ]]; then
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Building right side firmware"; fi
  build_firmware "right" "${BUILD_COMMAND_RIGHT}"
else
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Skipping right side build"; fi
fi

echo "Build complete!"

# Copy firmware files to results directory
# Log build flags if DEBUG is enabled
if [[ -n "$DEBUG" ]]; then
  echo "DEBUG: Build flags before copying: LEFT=${BUILD_LEFT}, RIGHT=${BUILD_RIGHT}"
fi

# Copy left side firmware if built
if [[ "$BUILD_LEFT" == "true" ]]; then
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Copying left side firmware"; fi
  copy_firmware "Left" "${BUILD_OUTPUT_LEFT}" "${RESULT_FIRMWARE_LEFT}"
else
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Skipping left side copy"; fi
fi

# Copy right side firmware if built
if [[ "$BUILD_RIGHT" == "true" ]]; then
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Copying right side firmware"; fi
  copy_firmware "Right" "${BUILD_OUTPUT_RIGHT}" "${RESULT_FIRMWARE_RIGHT}"
else
  if [[ -n "$DEBUG" ]]; then echo "DEBUG: Skipping right side copy"; fi
fi
