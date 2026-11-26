#!/usr/bin/env bash
# Build wipskin_native.so for Rocky 8+ / Rocky 9 (glibc 2.28) via Docker.
#
# Usage (repo root or native/):
#   bash native/docker-build.sh
#
# Requires Docker. On Windows use WSL2 or Git Bash with Docker Desktop.
# Output: python/wipskin/_native/wipskin_native.so
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
IMAGE_NAME="${WIPSKIN_NATIVE_IMAGE:-wipskin-native-manylinux_2_28}"
OUT_SO="/src/python/wipskin/_native/wipskin_native.so"

echo "Building image ${IMAGE_NAME}..."
docker build -t "${IMAGE_NAME}" -f "${SCRIPT_DIR}/Dockerfile" "${SCRIPT_DIR}"

echo "Building wheel and installing .so inside container..."
docker run --rm \
    -v "${REPO_ROOT}:/src" \
    -w /src/native \
    "${IMAGE_NAME}" \
    bash -lc '
        set -euo pipefail
        mkdir -p /src/native/dist /src/python/wipskin/_native
        rm -f /src/native/dist/wipskin_native-*.whl
        maturin build --release -o /src/native/dist
        WHEEL="$(ls -1 /src/native/dist/wipskin_native-*.whl | head -n 1)"
        EXTRACT="$(mktemp -d)"
        python -m zipfile -e "${WHEEL}" "${EXTRACT}"
        SO_SRC="$(find "${EXTRACT}" -type f -name "wipskin_native*.so" | head -n 1)"
        if [[ -z "${SO_SRC}" ]]; then
            echo "error: no wipskin_native*.so inside ${WHEEL}" >&2
            exit 1
        fi
        cp "${SO_SRC}" "'"${OUT_SO}"'"
        rm -rf "${EXTRACT}"
        ls -la "'"${OUT_SO}"'"
    '

echo "Wrote ${REPO_ROOT}/python/wipskin/_native/wipskin_native.so"
