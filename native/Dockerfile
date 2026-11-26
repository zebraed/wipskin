# Build wipskin_native for Rocky/RHEL 8+ (glibc 2.28).
# One .so works on Rocky 8 and Rocky 9 Maya hosts.
#
# manylinux_2_28 is AlmaLinux 8 based (same glibc family as Rocky 8).
# Building on a newer base (e.g. Rocky 9) would break Rocky 8.
FROM quay.io/pypa/manylinux_2_28_x86_64

# abi3-py310: any CPython >= 3.10 can build; 3.10 matches the declared ABI floor.
ENV PATH="/root/.cargo/bin:/opt/python/cp310-cp310/bin:${PATH}"

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \
    | sh -s -- -y --default-toolchain stable --profile minimal \
    && pip install --no-cache-dir 'maturin>=1.14,<2.0'

WORKDIR /src/native
