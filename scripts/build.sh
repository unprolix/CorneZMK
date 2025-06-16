#!/bin/bash
set -e

# we are trying to replicate the build of CONFIG_REPO that works
# perfectly when invoked via the github actions associated with the
# existing repository. NO CHANGES to the repository should be required
# for this build to work flawlessly. we just have to understand the
# equivalents of what the github-based workflow does. this should be
# 100% standard.

KEYBOARD_BASE="ergokeeb_corne"
RESULT_FIRMWARE_LEFT="ergokeeb_corne_left.uf2"
RESULT_FIRMWARE_RIGHT="ergokeeb_corne_right.uf2"

USB_DEBUGGING=y

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# zmk itself
ZMK_PATH="$SCRIPT_DIR/zmk-firmware"

# config repo for our actual keyboard
CONFIG_REPO=CorneZMK
CONFIG_PATH="${SCRIPT_DIR}/${CONFIG_REPO}/config"
BUILD_DIR="${SCRIPT_DIR}/build"
RESULTS_DIR="${SCRIPT_DIR}/results"
WORKSPACE_DIR="${SCRIPT_DIR}/workspace"
DOCKER_IMAGE=zmkfirmware/zmk-build-arm:stable

USER_ID=$(id -u)
GROUP_ID=$(id -g)

if [ "$USB_DEBUGGING" = "y" ]; then
    BUILD_COMMAND_EXTRA="--snippet zmk-usb-logging"
else
    BUILD_COMMAND_EXTRA=""
fi



# Build commands for left and right sides - using custom board definition with nice_view shield
ACTUAL_BUILD_COMMAND_LEFT="west build -d /workspace/build/${KEYBOARD_BASE}_left -b ${KEYBOARD_BASE}_left ${BUILD_COMMAND_EXTRA} -- -DSHIELD=nice_view -DZMK_CONFIG=/workspace/${CONFIG_REPO}/config"
ACTUAL_BUILD_COMMAND_RIGHT="west build -d /workspace/build/${KEYBOARD_BASE}_right -b ${KEYBOARD_BASE}_right ${BUILD_COMMAND_EXTRA} -- -DSHIELD=nice_view -DZMK_CONFIG=/workspace/${CONFIG_REPO}/config"

echo "Building ZMK firmware for ${KEYBOARD_BASE}..."
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


echo "Building left side firmware"
docker run --rm \
    -v ${ZMK_PATH}:/zmk \
    -v ${SCRIPT_DIR}:/workspace \
    -w /zmk/app \
    -e ZEPHYR_BASE=/zmk/zephyr \
    -e BOARD_ROOT=/workspace/${CONFIG_REPO} \
    --user ${USER_ID}:${GROUP_ID} \
    ${DOCKER_IMAGE} \
    ${ACTUAL_BUILD_COMMAND_LEFT}

echo "Building right side firmware"
docker run --rm \
    -v ${ZMK_PATH}:/zmk \
    -v ${SCRIPT_DIR}:/workspace \
    -w /zmk/app \
    -e ZEPHYR_BASE=/zmk/zephyr \
    -e BOARD_ROOT=/workspace/${CONFIG_REPO} \
    --user ${USER_ID}:${GROUP_ID} \
    ${DOCKER_IMAGE} \
    ${ACTUAL_BUILD_COMMAND_RIGHT}

echo "Build complete!"
echo "Left side firmware:  ${BUILD_DIR}/${KEYBOARD_BASE}_left/zephyr/zmk.uf2"
echo "Right side firmware: ${BUILD_DIR}/${KEYBOARD_BASE}_right/zephyr/zmk.uf2"

# Copy firmware files to root for easy access
cp ${BUILD_DIR}/${KEYBOARD_BASE}_left/zephyr/zmk.uf2 ${RESULTS_DIR}/${RESULT_FIRMWARE_LEFT}
cp ${BUILD_DIR}/${KEYBOARD_BASE}_right/zephyr/zmk.uf2 ${RESULTS_DIR}/${RESULT_FIRMWARE_RIGHT}

echo "Firmware files copied to:"
echo "  ${RESULTS_DIR}/${RESULT_FIRMWARE_LEFT}"
echo "  ${RESULTS_DIR}/${RESULT_FIRMWARE_RIGHT}"
