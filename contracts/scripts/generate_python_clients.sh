#!/usr/bin/env bash
set -euo pipefail
echo "Client generation requires an explicit external OUTPUT_DIR and reviewed toolchain; never write generated artifacts into the canonical catalog." >&2
exit 2
