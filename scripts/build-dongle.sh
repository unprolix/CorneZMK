#!/bin/bash

#############################################################
# ZMK Dongle Build Script
# 
# This script builds ZMK firmware for the dongle board
#
# Usage: ./build_dongle.sh [--clean]
#############################################################

set -e

# Enable command tracing if DEBUG environment variable is set
if [[ -n "$DEBUG" ]]; then
  set -x
fi

# Default settings
BOARD_TYPE="zmk_dongle"
CLEAN_BUILD=false

# Get user and group IDs
USER_ID=$(id -u)
GROUP_ID=$(id -g)

# Get the directory of this script
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "${SCRIPT_PATH}")"

# Find CorneZMK root directory (reuse logic from main build.sh)
find_root_dir() {
  local current_dir="$1"
  
  if [[ "${current_dir##*/}" == "CorneZMK" ]]; then
    echo "$current_dir"
    return 0
  fi
  
  if [[ -d "$current_dir/CorneZMK" ]]; then
    echo "$current_dir/CorneZMK"
    return 0
  fi
  
  if [[ "${current_dir##*/}" == "scripts" && -d "$current_dir/.." ]]; then
    local parent_dir="$(cd "$current_dir/.." && pwd)"
    if [[ "${parent_dir##*/}" == "CorneZMK" ]]; then
      echo "$parent_dir"
      return 0
    fi
  fi
  
  if [[ "$current_dir" == *"/zmk/CorneZMK"* ]]; then
    echo "${current_dir%/zmk/CorneZMK*}/zmk/CorneZMK"
    return 0
  fi
  
  if [[ "$current_dir" == *"/src/zmk/CorneZMK"* ]]; then
    echo "${current_dir%/src/zmk/CorneZMK*}/src/zmk/CorneZMK"
    return 0
  fi
  
  return 1
}

# Try to find the root directory
ROOT_DIR=$(find_root_dir "$SCRIPT_DIR")

if [[ -z "$ROOT_DIR" ]]; then
  ROOT_DIR=$(find_root_dir "$(pwd)")
  if [[ -z "$ROOT_DIR" ]]; then
    echo "Error: Cannot determine CorneZMK root directory"
    echo "Please run this script from the CorneZMK directory or its scripts subdirectory"
    exit 1
  fi
fi

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --clean)
      CLEAN_BUILD=true
      echo "Clean flag set: will clean build directory"
      ;;
    --help)
      echo "Usage: $0 [--clean]"
      echo "Options:"
      echo "  --clean    Clean build directory before building"
      echo "  --help     Show this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Use --help for usage information"
      exit 1
      ;;
  esac
  shift
done

# Directory paths
ZMK_PATH="${ROOT_DIR}/zmk-firmware"
CONFIG_PATH="${ROOT_DIR}/config"
BUILD_DIR="${ROOT_DIR}/build"
RESULTS_DIR="${ROOT_DIR}/results"
BUILD_DIR_BOARD="${BUILD_DIR}/${BOARD_TYPE}"
BUILD_OUTPUT_BOARD="${BUILD_DIR_BOARD}/zephyr/zmk.uf2"
RESULT_FIRMWARE_BOARD="${BOARD_TYPE}.uf2"

# Docker image for building
DOCKER_IMAGE="zmkfirmware/zmk-build-arm:stable"

echo "Building ZMK firmware for ${BOARD_TYPE}..."
echo "Using ZMK from: ${ZMK_PATH}"
echo "Results will be placed in: ${RESULTS_DIR}"

# Check prerequisites
if [ ! -d "${CONFIG_PATH}" ]; then
  echo "Error: Config directory not found at ${CONFIG_PATH}"
  exit 1
fi

if [ ! -f "${CONFIG_PATH}/${BOARD_TYPE}.keymap" ]; then
  echo "Error: ${BOARD_TYPE}.keymap not found in ${CONFIG_PATH}"
  exit 1
fi

if [ ! -d "${ROOT_DIR}/boards/arm/${BOARD_TYPE}" ]; then
  echo "Error: Board definition not found at ${ROOT_DIR}/boards/arm/${BOARD_TYPE}"
  exit 1
fi

# Setup ZMK (reuse from main build.sh)
if [ ! -d "${ZMK_PATH}" ]; then
  echo "Creating ZMK directory..."
  mkdir -p "${ZMK_PATH}"
fi

if [ ! -d "${ZMK_PATH}/app" ]; then
  echo "ZMK not found. Cloning ZMK repository..."
  git clone https://github.com/zmkfirmware/zmk.git "${ZMK_PATH}"
fi

# Check ownership
if [ -d "${ZMK_PATH}" ]; then
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

# Clean build directory if requested
if [[ "$CLEAN_BUILD" == "true" ]]; then
  echo "Cleaning build directory..."
  rm -rf ${BUILD_DIR_BOARD}
fi

# Create build directory
mkdir -p ${BUILD_DIR}
mkdir -p ${RESULTS_DIR}

# Generate build info
echo "Creating compile-time macro"
CURRENT_DIR=$(pwd)
cd "${SCRIPT_DIR}" || exit 1
if [ -f "generate_build_info.sh" ]; then
  ./generate_build_info.sh
fi
cd "${CURRENT_DIR}" || exit 1

# Build firmware
echo "Building ${BOARD_TYPE} firmware"
BUILD_COMMAND_BOARD="west build -d /workspace/build/${BOARD_TYPE} -b ${BOARD_TYPE} -- -DZMK_CONFIG=/workspace/config"

if ! docker run --rm \
  -v ${ZMK_PATH}:/zmk \
  -v ${ROOT_DIR}:/workspace \
  -w /zmk/app \
  -e ZEPHYR_BASE=/zmk/zephyr \
  -e BOARD_ROOT=/workspace \
  --user ${USER_ID}:${GROUP_ID} \
  ${DOCKER_IMAGE} \
  ${BUILD_COMMAND_BOARD}; then
  echo "Error: Failed to build ${BOARD_TYPE} firmware"
  exit 1
fi

# Copy firmware to results
if [ -f "${BUILD_OUTPUT_BOARD}" ]; then
  cp ${BUILD_OUTPUT_BOARD} ${RESULTS_DIR}/${RESULT_FIRMWARE_BOARD}
  echo "Build complete!"
  echo "Firmware: ${RESULTS_DIR}/${RESULT_FIRMWARE_BOARD}"
else
  echo "Error: ${BOARD_TYPE} firmware not found at ${BUILD_OUTPUT_BOARD}"
  exit 1
fi
