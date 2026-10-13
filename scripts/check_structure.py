#!/usr/bin/env python3
# Copyright 2026 Maktab-e-Digital Systems Lahore.
# SPDX-License-Identifier: Apache-2.0
"""Enforce the MEDS-S1 repository conventions.

Each check protects repository consistency and makes violations visible to CI.
The checks are intentionally mechanical; they verify conventions that can be
reliably detected, while design correctness still requires review and testing.

Rules checked (see docs/guidelines/CODING_STANDARD.md):
  S1  every source directory has a README.md
  S2  every .sv and .py file carries an SPDX licence identifier
  S3  RTL module name matches its file name
  S4  RTL modules use the mandated prefixes
  S5  ports use the _i / _o / _io direction suffixes
  S6  no legacy always blocks, reg/wire declarations, or $random
  S7  no memory array declared outside meds_s1_sram
  S8  every testbench follows tb_<module>.sv and has a matching RTL module
  S9  configs/*.yaml parse and declare the required keys
  S10 no file exceeds the size limit without a waiver

Exit status is the number of violations, capped at 100.

Usage:
    python3 scripts/check_structure.py
    python3 scripts/check_structure.py --fix-readmes
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from typing import TypeAlias

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Keep this list explicit so adding a source directory also requires deciding
# how its purpose and contribution workflow should be documented.
README_DIRS = (
    "rtl",
    "rtl/core",
    "rtl/cache",
    "rtl/fabric",
    "rtl/peripherals",
    "rtl/socket",
    "rtl/common",
    "rtl/generated",
    "verif",
    "verif/unit",
    "verif/cosim",
    "verif/riscof",
    "verif/formal",
    "verif/conformance",
    "sw",
    "sw/bsp",
    "sw/apps",
    "sw/drivers",
    "gen",
    "configs",
    "boards",
    "extensions",
    "scripts",
    "docs",
    "docs/guidelines",
    "docs/modules",
    "docs/adr",
)

MODULE_PREFIXES = ("s1_", "meds_s1_", "meds_v_", "tb_")
MAX_LINES = 800
SIZE_WAIVERS = {
    "scripts/gen_project_catalogue.py",
    "scripts/gen_diagrams.py",
}
REQUIRED_CONFIG_KEYS = {"name", "isa", "privilege", "backbone", "memory_map"}
SKIP_DIRECTORY_NAMES = {".git", "build", "__pycache__", "ext", "node_modules"}

Problem: TypeAlias = tuple[str, str, str]


class Checker:
    """Collect structural violations and print them grouped by rule."""

    def __init__(self) -> None:
        self.problems: list[Problem] = []

    def bad(self, rule: str, location: pathlib.Path | str, message: str) -> None:
        """Record a violation using a repository-relative path when possible."""
        if isinstance(location, pathlib.Path):
            try:
                display_path = str(location.relative_to(ROOT))
            except ValueError:
                display_path = str(location)
        else:
            display_path = location
        self.problems.append((rule, display_path, message))

    # S1 -----------------------------------------------------------------
    def check_readmes(self, fix_missing: bool) -> None:
        for directory_name in README_DIRS:
            directory_path = ROOT / directory_name
            if not directory_path.is_dir():
                continue

            readme_path = directory_path / "README.md"
            if readme_path.exists():
                continue

            if fix_missing:
                # Create a deliberately incomplete stub: the owner must still
                # document the directory's actual contents and contribution flow.
                readme_path.write_text(
                    f"# `{directory_name}/`\n\n"
                    "**TODO** — state what lives here, what does *not*, how to add "
                    "something, and the definition of done.\n\n"
                    "See `docs/guidelines/CODING_STANDARD.md` R-D1.\n",
                    encoding="utf-8",
                )
                continue

            self.bad("S1", directory_name, "directory has no README.md (R-D1)")

    # S2 -----------------------------------------------------------------
    def check_spdx(self) -> None:
        source_files = (*ROOT.rglob("*.sv"), *ROOT.rglob("*.py"))
        for source_path in source_files:
            if self._skip(source_path):
                continue

            # The required licence header belongs at the start of the file;
            # reading only the header also avoids loading large sources in full.
            header = source_path.read_text(
                encoding="utf-8", errors="replace"
            )[:800]
            if "SPDX-License-Identifier" not in header:
                self.bad(
                    "S2",
                    source_path,
                    "missing SPDX-License-Identifier header (R-D2)",
                )

    # S3/S4/S5 -----------------------------------------------------------
    def check_rtl(self) -> None:
        module_pattern = re.compile(r"^\s*module\s+([A-Za-z_][\w$]*)", re.M)
        port_pattern = re.compile(
            r"^\s*(?:input|output|inout)\b[^;]*?"
            r"([A-Za-z_]\w*)\s*(?:\[[^\]]*\])?\s*[,)]\s*$"
        )

        for source_path in sorted(ROOT.rglob("*.sv")):
            if self._skip(source_path):
                continue

            source_text = source_path.read_text(encoding="utf-8", errors="replace")
            module_names = module_pattern.findall(source_text)
            if not module_names:
                continue  # Package-only files do not declare RTL modules.

            if source_path.stem not in module_names:
                self.bad(
                    "S3",
                    source_path,
                    f"no module named '{source_path.stem}' "
                    f"(found {', '.join(module_names)}) (R-N1)",
                )

            for module_name in module_names:
                if not module_name.startswith(MODULE_PREFIXES):
                    self.bad(
                        "S4",
                        source_path,
                        f"module '{module_name}' lacks a mandated prefix "
                        f"{MODULE_PREFIXES} (R-N2)",
                    )

            # Port suffixes describe hardware interfaces, not task/function
            # arguments. Skip verification files and nested task/function bodies.
            if "verif" in source_path.parts:
                continue

            subprogram_depth = 0
            for line in source_text.splitlines():
                if re.match(r"\s*(task|function)\b", line):
                    subprogram_depth += 1
                elif re.match(r"\s*end(task|function)\b", line):
                    subprogram_depth = max(0, subprogram_depth - 1)

                if subprogram_depth:
                    continue

                port_match = port_pattern.match(line)
                if not port_match:
                    continue

                port_name = port_match.group(1)
                if port_name in ("clk_i", "rst_ni"):
                    continue
                if not port_name.endswith(("_i", "_o", "_io")):
                    self.bad(
                        "S5",
                        source_path,
                        f"port '{port_name}' lacks _i/_o/_io suffix (R-N3)",
                    )

    # S6/S7 --------------------------------------------------------------
    def check_style(self) -> None:
        banned_patterns = (
            (
                re.compile(r"\balways\s*@\s*\("),
                "use always_ff/always_comb/always_latch (R-C1)",
            ),
            (re.compile(r"^\s*reg\s+", re.M), "use `logic`, not `reg` (R-C2)"),
            (re.compile(r"^\s*wire\s+", re.M), "use `logic`, not `wire` (R-C2)"),
            (re.compile(r"\$random\b"), "use $urandom, which is seeded reproducibly (R-V4)"),
        )
        memory_array_pattern = re.compile(
            r"^\s*logic\s*(?:\[[^\]]*\]\s*)+\w+\s*\[[^\]]*\]\s*;",
            re.M,
        )

        for source_path in sorted(ROOT.rglob("*.sv")):
            if self._skip(source_path):
                continue

            source_text = source_path.read_text(encoding="utf-8", errors="replace")
            for pattern, message in banned_patterns:
                if pattern.search(source_text):
                    self.bad("S6", source_path, message)

            # Testbench memories are stimulus/scoreboard data, not synthesizable
            # SRAM instances, so the memory-location rule excludes verification.
            if (
                memory_array_pattern.search(source_text)
                and source_path.name != "meds_s1_sram.sv"
                and "verif" not in source_path.parts
            ):
                self.bad(
                    "S7",
                    source_path,
                    "memory array declared outside meds_s1_sram "
                    "(INTERFACES.md section 8, R-C5)",
                )

    # S8 -----------------------------------------------------------------
    def check_testbenches(self) -> None:
        rtl_module_names = {
            source_path.stem
            for source_path in ROOT.rglob("rtl/**/*.sv")
            if not self._skip(source_path)
        }
        testbench_directory = ROOT / "verif" / "unit"

        for testbench_path in sorted(testbench_directory.glob("*.sv")):
            if not testbench_path.name.startswith("tb_"):
                self.bad(
                    "S8",
                    testbench_path,
                    "unit testbench must be named tb_<module>.sv (R-V1)",
                )
                continue

            dut_name = testbench_path.stem.removeprefix("tb_")
            if dut_name not in rtl_module_names:
                self.bad(
                    "S8",
                    testbench_path,
                    f"no RTL module '{dut_name}' for this testbench (R-V1)",
                )

    # S9 -----------------------------------------------------------------
    def check_configs(self) -> None:
        try:
            import yaml
        except ImportError:
            self.bad(
                "S9",
                "configs",
                "cannot validate YAML files because PyYAML is not installed",
            )
            return

        config_directory = ROOT / "configs"
        if not config_directory.is_dir():
            return

        config_paths = sorted(config_directory.glob("*.yaml"))
        if not config_paths:
            self.bad("S9", "configs", "no configuration files (SPEC section 5.3)")
            return

        for config_path in config_paths:
            try:
                config_data = yaml.safe_load(
                    config_path.read_text(encoding="utf-8")
                ) or {}
            except (OSError, UnicodeError, yaml.YAMLError) as error:
                self.bad("S9", config_path, f"YAML does not parse: {error}")
                continue

            if not isinstance(config_data, dict):
                self.bad("S9", config_path, "configuration must be a YAML mapping")
                continue

            missing_keys = REQUIRED_CONFIG_KEYS - set(config_data)
            if missing_keys:
                self.bad(
                    "S9",
                    config_path,
                    f"missing required keys: {', '.join(sorted(missing_keys))}",
                )

    # S10 ----------------------------------------------------------------
    def check_size(self) -> None:
        source_files = (*ROOT.rglob("*.sv"), *ROOT.rglob("*.py"))
        for source_path in source_files:
            if self._skip(source_path):
                continue

            relative_path = str(source_path.relative_to(ROOT))
            if relative_path in SIZE_WAIVERS:
                continue

            line_count = len(
                source_path.read_text(encoding="utf-8", errors="replace").splitlines()
            )
            if line_count > MAX_LINES:
                self.bad(
                    "S10",
                    source_path,
                    f"{line_count} lines exceeds the {MAX_LINES}-line limit; "
                    "split it or add a waiver with a reason (R-C6)",
                )

    @staticmethod
    def _skip(source_path: pathlib.Path) -> bool:
        """Exclude vendored, generated, and transient files from source checks."""
        path_parts = set(source_path.parts)
        return bool(path_parts & SKIP_DIRECTORY_NAMES) or "rtl/generated" in str(
            source_path
        )

    def report(self) -> int:
        if not self.problems:
            print("structure check: OK")
            return 0

        problems_by_rule: dict[str, list[tuple[str, str]]] = {}
        for rule, path, message in self.problems:
            problems_by_rule.setdefault(rule, []).append((path, message))

        print(f"structure check: {len(self.problems)} violation(s)\n")
        for rule in sorted(problems_by_rule):
            print(f"  [{rule}]")
            for path, message in sorted(problems_by_rule[rule]):
                print(f"    {path}: {message}")
            print()

        print(
            "See docs/guidelines/CODING_STANDARD.md for the rule that each "
            "check maps to."
        )
        return min(len(self.problems), 100)


def main() -> int:
    """Parse command-line options, run every gate, and return the result."""
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument(
        "--fix-readmes",
        action="store_true",
        help="create a stub README.md in any directory missing one",
    )
    arguments = argument_parser.parse_args()

    checker = Checker()
    checker.check_readmes(arguments.fix_readmes)
    checker.check_spdx()
    checker.check_rtl()
    checker.check_style()
    checker.check_testbenches()
    checker.check_configs()
    checker.check_size()
    return checker.report()


if __name__ == "__main__":
    sys.exit(main())
