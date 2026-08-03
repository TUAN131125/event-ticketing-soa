#!/usr/bin/env python3
"""Fail when a Prompt-2A canonical artifact still contains a stub marker."""

import sys

sys.dont_write_bytecode = True

from contract_utils import find_placeholders


def main() -> int:
    errors = find_placeholders()
    for error in errors:
        print(f"ERROR {error}")
    if errors:
        print(f"PLACEHOLDER_CHECK FAIL errors={len(errors)}")
        return 1
    print("PLACEHOLDER_CHECK PASS errors=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
