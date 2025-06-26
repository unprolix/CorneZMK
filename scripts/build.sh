#!/bin/bash
set -e

USER_ID=$(id -u)
GROUP_ID=$(id -g)

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

DOCKER_IMAGE=zmkfirmware/zmk-build-arm:stable

# zmk repo itself
ZMK_PATH="$SCRIPT_DIR/zmk-firmware"

# config repo for our actual keyboard
CONFIG_REPO=CorneZMK

KEYBOARD_NAME="ergokeeb_corne"
USB_DEBUGGING=y

# Default shield type
SHIELD_TYPE="nice_view"

# Default sides to build (both)
BUILD_LEFT=true
BUILD_RIGHT=true

# Parse command line arguments
while [[ $# -gt 0 ]]; do
  case $1 in
    --shield=*)
      SHIELD_TYPE="${1#*=}"
      ;;
    --left-only)
      BUILD_LEFT=true
      BUILD_RIGHT=false
      ;;
    --right-only)
      BUILD_LEFT=false
      BUILD_RIGHT=true
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --shield=TYPE    Shield type to build (nice_view or nice_view_gem)"
      echo "  --left-only      Build only left side"
      echo "  --right-only     Build only right side"
      echo "  --help           Show this help message"
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

# Validate shield type
if [[ "$SHIELD_TYPE" != "nice_view" && "$SHIELD_TYPE" != "nice_view_gem" ]]; then
  echo "Error: Invalid shield type '$SHIELD_TYPE'. Must be 'nice_view' or 'nice_view_gem'"
  exit 1
fi

CONFIG_PATH="${SCRIPT_DIR}/${CONFIG_REPO}/config"
BUILD_DIR="${SCRIPT_DIR}/build"
RESULTS_DIR="${SCRIPT_DIR}/results"
WORKSPACE_DIR="${SCRIPT_DIR}/workspace"


# Set build directories and output paths based on shield type
if [[ "$SHIELD_TYPE" == "nice_view" ]]; then
  BUILD_DIR_LEFT=${BUILD_DIR}/${KEYBOARD_NAME}_left
  BUILD_DIR_RIGHT=${BUILD_DIR}/${KEYBOARD_NAME}_right
  RESULT_FIRMWARE_LEFT="${KEYBOARD_NAME}_left.uf2"
  RESULT_FIRMWARE_RIGHT="${KEYBOARD_NAME}_right.uf2"
else
  # For nice_view_gem
  BUILD_DIR_LEFT=${BUILD_DIR}/${KEYBOARD_NAME}_left_gem
  BUILD_DIR_RIGHT=${BUILD_DIR}/${KEYBOARD_NAME}_right_gem
  RESULT_FIRMWARE_LEFT="${KEYBOARD_NAME}_left_gem.uf2"
  RESULT_FIRMWARE_RIGHT="${KEYBOARD_NAME}_right_gem.uf2"
fi

BUILD_OUTPUT_LEFT=${BUILD_DIR_LEFT}/zephyr/zmk.uf2
BUILD_OUTPUT_RIGHT=${BUILD_DIR_RIGHT}/zephyr/zmk.uf2


if [ "$USB_DEBUGGING" = "y" ]; then
    BUILD_COMMAND_EXTRA="--snippet zmk-usb-logging"
else
    BUILD_COMMAND_EXTRA=""
fi



# Build commands for left and right sides based on shield type
if [[ "$SHIELD_TYPE" == "nice_view" ]]; then
  SHIELD_PARAM="nice_view"
  BUILD_DIR_SUFFIX_LEFT="${KEYBOARD_NAME}_left"
  BUILD_DIR_SUFFIX_RIGHT="${KEYBOARD_NAME}_right"
  
  # Standard build commands for nice_view
  ACTUAL_BUILD_COMMAND_LEFT="west build -d /workspace/build/${BUILD_DIR_SUFFIX_LEFT} -b ${KEYBOARD_NAME}_left ${BUILD_COMMAND_EXTRA} -- -DSHIELD=${SHIELD_PARAM} -DZMK_CONFIG=/workspace/${CONFIG_REPO}/config"
  ACTUAL_BUILD_COMMAND_RIGHT="west build -d /workspace/build/${BUILD_DIR_SUFFIX_RIGHT} -b ${KEYBOARD_NAME}_right ${BUILD_COMMAND_EXTRA} -- -DSHIELD=${SHIELD_PARAM} -DZMK_CONFIG=/workspace/${CONFIG_REPO}/config"
else
  # For nice_view_gem
  SHIELD_PARAM="nice_view_adapter nice_view_gem"
  BUILD_DIR_SUFFIX_LEFT="${KEYBOARD_NAME}_left_gem"
  BUILD_DIR_SUFFIX_RIGHT="${KEYBOARD_NAME}_right_gem"
  
  # For nice_view_gem, we need to completely disable the ZMK display module to avoid compilation errors
  # The nice_view_gem has its own display handling
  ACTUAL_BUILD_COMMAND_LEFT="west build -d /workspace/build/${BUILD_DIR_SUFFIX_LEFT} -b ${KEYBOARD_NAME}_left ${BUILD_COMMAND_EXTRA} -- -DSHIELD=${SHIELD_PARAM} -DZMK_CONFIG=/workspace/${CONFIG_REPO}/config -DCONFIG_ZMK_DISPLAY=n"
  ACTUAL_BUILD_COMMAND_RIGHT="west build -d /workspace/build/${BUILD_DIR_SUFFIX_RIGHT} -b ${KEYBOARD_NAME}_right ${BUILD_COMMAND_EXTRA} -- -DSHIELD=${SHIELD_PARAM} -DZMK_CONFIG=/workspace/${CONFIG_REPO}/config -DCONFIG_ZMK_DISPLAY=n"
fi

echo "Building ZMK firmware for ${KEYBOARD_NAME} with ${SHIELD_TYPE} shield..."
echo "Using ZMK from: ${ZMK_PATH}"
echo "Results will be placed in: ${RESULTS_DIR}"

# Ensure results directory exists
mkdir -p ${RESULTS_DIR}

# Check config repo structure
if [ ! -d "${CONFIG_PATH}" ]; then
    echo "Error: Config directory not found at ${CONFIG_PATH}"
    exit 1
fi

if [ ! -f "${CONFIG_PATH}/ergokeeb_corne.keymap" ]; then
    echo "Error: ergokeeb_corne.keymap not found in ${CONFIG_PATH}"
    exit 1
fi

# Check for custom board definitions
if [ ! -d "${SCRIPT_DIR}/${CONFIG_REPO}/boards/arm/ergokeeb_corne" ]; then
    echo "Error: Custom board definition not found at ${SCRIPT_DIR}/${CONFIG_REPO}/boards/arm/ergokeeb_corne"
    exit 1
fi

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
        sudo chown -R ${USER}:${USER} "${ZMK_PATH}"
    fi
fi

# Initialize ZMK workspace if needed
echo "Checking ZMK workspace..."
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

# Clean previous builds
rm -rf ${BUILD_DIR}
mkdir -p ${BUILD_DIR}

echo "Creating compile-time macro"
${SCRIPT_DIR}/${CONFIG_REPO}/scripts/generate_build_info.sh


# Build left side if requested
if [[ "$BUILD_LEFT" == true ]]; then
  echo "Building left side firmware with ${SHIELD_TYPE} shield"
  docker run --rm \
      -v ${ZMK_PATH}:/zmk \
      -v ${SCRIPT_DIR}:/workspace \
      -w /zmk/app \
      -e ZEPHYR_BASE=/zmk/zephyr \
      -e BOARD_ROOT=/workspace/${CONFIG_REPO} \
      --user ${USER_ID}:${GROUP_ID} \
      ${DOCKER_IMAGE} \
      ${ACTUAL_BUILD_COMMAND_LEFT}
fi

# Build right side if requested
if [[ "$BUILD_RIGHT" == true ]]; then
  echo "Building right side firmware with ${SHIELD_TYPE} shield"
  docker run --rm \
      -v ${ZMK_PATH}:/zmk \
      -v ${SCRIPT_DIR}:/workspace \
      -w /zmk/app \
      -e ZEPHYR_BASE=/zmk/zephyr \
      -e BOARD_ROOT=/workspace/${CONFIG_REPO} \
      --user ${USER_ID}:${GROUP_ID} \
      ${DOCKER_IMAGE} \
      ${ACTUAL_BUILD_COMMAND_RIGHT}
fi

echo "Build complete!"

# Copy firmware files to results directory
if [[ "$BUILD_LEFT" == true && -f "${BUILD_OUTPUT_LEFT}" ]]; then
  cp ${BUILD_OUTPUT_LEFT} ${RESULTS_DIR}/${RESULT_FIRMWARE_LEFT}
  echo "Left side firmware: ${RESULTS_DIR}/${RESULT_FIRMWARE_LEFT}"
fi

if [[ "$BUILD_RIGHT" == true && -f "${BUILD_OUTPUT_RIGHT}" ]]; then
  cp ${BUILD_OUTPUT_RIGHT} ${RESULTS_DIR}/${RESULT_FIRMWARE_RIGHT}
  echo "Right side firmware: ${RESULTS_DIR}/${RESULT_FIRMWARE_RIGHT}"
fi
