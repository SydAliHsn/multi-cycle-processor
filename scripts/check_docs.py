#!/usr/bin/env python3
# Copyright 2026 Maktab-e-Digital Systems Lahore.
# SPDX-License-Identifier: Apache-2.0
"""Check directory READMEs (R-D1); module contract pages are optional."""
from __future__ import annotations

import sys

from check_structure import Checker


def main() -> int:
    checker = Checker()
    checker.check_readmes()
    return checker.report()


if __name__ == "__main__":
    sys.exit(main())
