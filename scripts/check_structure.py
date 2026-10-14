#!/usr/bin/env python3
# Copyright 2026 Maktab-e-Digital Systems Lahore.
# SPDX-License-Identifier: Apache-2.0
"""Check the mechanical rules in docs/guidelines/CODING_STANDARDS.md.

Checks cover directory READMEs, module port naming, explicit procedural block
types, logic declarations, randomized stimulus, and testbench filenames.
Semantic RTL checks, including latch inference, belong to the HDL linter.

Usage:
    python3 scripts/check_structure.py
    python3 scripts/check_structure.py --fix-readmes
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
from collections.abc import Iterator

ROOT = pathlib.Path(__file__).resolve().parent.parent
SOURCE_ROOTS = (
    "rtl", "verif", "sw", "fpga", "scripts", "docs", "gen", "configs",
    "boards", "extensions",
)
SKIP_DIRECTORY_NAMES = {
    ".git", "build", "obj_dir", "__pycache__", "ext", "node_modules",
}
PORT_SUFFIXES = {
    "input": ("_i", "_ni"),
    "output": ("_o", "_no"),
    "inout": ("_io", "_nio"),
}
IDENTIFIER = re.compile(r"(?:[A-Za-z_$][\w$]*|\\\S+)\Z")
NON_CODE = re.compile(r'//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\])*"|\(\*(?!\)).*?\*\)', re.S)
TOKEN = re.compile(r"\\\S+|[A-Za-z_$][\w$]*|[^\s]")
OPENING = {"(": ")", "[": "]", "{": "}"}


def source_tokens(text: str) -> list[str]:
    """Keep keywords in comments, strings and attributes out of source checks."""
    code = NON_CODE.sub(lambda match: "\n" * match.group().count("\n") + " ", text)
    return TOKEN.findall(code)


def split_top_level(tokens: list[str], separator: str) -> list[list[str]]:
    """Split declarations without splitting dimensions or default expressions."""
    parts: list[list[str]] = [[]]
    depth = 0
    for token in tokens:
        if token == separator and depth == 0:
            parts.append([])
            continue
        parts[-1].append(token)
        if token in OPENING:
            depth += 1
        elif token in OPENING.values():
            depth -= 1
    return parts


def group_end(tokens: list[str], start: int) -> int:
    """Return the index after a balanced parenthesis, bracket or brace group."""
    closing = OPENING[tokens[start]]
    index = start + 1
    while index < len(tokens):
        if tokens[index] == closing:
            return index + 1
        if tokens[index] in OPENING:
            index = group_end(tokens, index)
        else:
            index += 1
    return len(tokens)


def declaration_ports(tokens: list[str]) -> list[tuple[str, str]]:
    """Read ANSI ports, including inherited directions and array dimensions."""
    ports = []
    direction = None
    for declaration in split_top_level(tokens, ","):
        if declaration and declaration[0] in PORT_SUFFIXES:
            direction = declaration[0]
        if direction is None:
            continue
        declaration = split_top_level(declaration, "=")[0]
        identifiers = []
        index = 0
        while index < len(declaration):
            token = declaration[index]
            if token in OPENING:
                index = group_end(declaration, index)
                continue
            if IDENTIFIER.fullmatch(token):
                identifiers.append(token)
            index += 1
        if identifiers:
            ports.append((direction, identifiers[-1]))
    return ports


def module_ports(tokens: list[str]) -> Iterator[tuple[str, list[tuple[str, str]]]]:
    """Read ordinary ANSI and non-ANSI module ports, excluding subprograms.

    This is a declaration scanner, not an HDL compiler. Preprocessor expansion
    and validation of SystemVerilog syntax remain the compiler's responsibility.
    """
    index = 0
    while index < len(tokens):
        if tokens[index] != "module":
            index += 1
            continue
        index += 1
        if index < len(tokens) and tokens[index] in ("automatic", "static"):
            index += 1
        if index >= len(tokens):
            return
        name = tokens[index]
        index += 1
        if index + 1 < len(tokens) and tokens[index] == "#" and tokens[index + 1] == "(":
            index = group_end(tokens, index + 1)
        header = []
        if index < len(tokens) and tokens[index] == "(":
            end = group_end(tokens, index)
            header = tokens[index + 1:end - 1]
            index = end
        ports = declaration_ports(header)
        ansi = bool(ports)
        header_names = {token for token in header if IDENTIFIER.fullmatch(token)}
        while index < len(tokens) and tokens[index] != "endmodule":
            token = tokens[index]
            if token in ("task", "function"):
                end_token = "end" + token
                while index < len(tokens) and tokens[index] != end_token:
                    index += 1
            elif not ansi and token in PORT_SUFFIXES:
                end = index
                while end < len(tokens) and tokens[end] != ";":
                    end += 1
                ports.extend(
                    port for port in declaration_ports(tokens[index:end])
                    if port[1] in header_names
                )
                index = end
            index += 1
        yield name, ports


class Checker:
    """Collect structural violations and print them grouped by standard rule."""

    def __init__(self) -> None:
        self.problems: list[tuple[str, str, str]] = []

    def bad(self, rule: str, location: pathlib.Path | str, message: str) -> None:
        if isinstance(location, pathlib.Path):
            try:
                location = location.relative_to(ROOT)
            except ValueError:
                pass
        self.problems.append((rule, str(location), message))

    def check_readmes(self, fix_missing: bool = False) -> None:
        for source_root in SOURCE_ROOTS:
            directory = ROOT / source_root
            if not directory.is_dir():
                continue
            directories = [directory, *(p for p in directory.rglob("*") if p.is_dir())]
            for path in sorted(directories):
                if self._skip(path) or (path / "README.md").is_file():
                    continue
                if fix_missing:
                    (path / "README.md").write_text(
                        f"# {path.relative_to(ROOT).as_posix()}\n\n"
                        "TODO: Describe this directory's contents and purpose.\n\n"
                        "See `docs/guidelines/CODING_STANDARDS.md` R-D1.\n",
                        encoding="utf-8",
                    )
                else:
                    self.bad("R-D1", path, "directory has no README.md")

    def check_rtl(self) -> None:
        for source_path in sorted((ROOT / "rtl").rglob("*.sv")):
            if self._skip(source_path):
                continue
            tokens = source_tokens(source_path.read_text(encoding="utf-8", errors="replace"))
            for module_name, ports in module_ports(tokens):
                for direction, port in ports:
                    if re.search(r"_(?:i|o|io)_n$", port):
                        self.bad("R-N3", source_path,
                                 f"{module_name}: place the active-low marker before "
                                 f"the direction suffix in '{port}' (for example rst_ni)")
                    elif not port.endswith(PORT_SUFFIXES[direction]):
                        self.bad("R-N2", source_path,
                                 f"{module_name}: {direction} port '{port}' must end in "
                                 f"{' or '.join(PORT_SUFFIXES[direction])}")
                for required_port in ("clk_i", "rst_ni"):
                    if ports.count(("input", required_port)) != 1:
                        self.bad("R-N5", source_path,
                                 f"{module_name}: declare exactly one input {required_port}")

    def check_style(self) -> None:
        banned_tokens = {
            "always": ("R-C1", "use always_ff/always_comb/always_latch"),
            "reg": ("R-C2", "use logic, not reg"),
            "wire": ("R-C2", "use logic, not wire"),
            "$random": ("R-V4", "use $urandom; seed tests when reproducibility is needed"),
        }
        for source_path in sorted(ROOT.rglob("*.sv")):
            if self._skip(source_path):
                continue
            tokens = set(source_tokens(source_path.read_text(encoding="utf-8", errors="replace")))
            for token, (rule, message) in banned_tokens.items():
                if token in tokens:
                    self.bad(rule, source_path, message)

    def check_testbenches(self) -> None:
        rtl_filenames = {
            path.stem for path in (ROOT / "rtl").rglob("*.sv")
            if not self._skip(path)
        }
        for path in sorted((ROOT / "verif" / "unit").glob("*.sv")):
            if self._skip(path):
                continue
            if not path.name.startswith("tb_"):
                self.bad("R-V1", path, "unit testbench must be named tb_<filename>.sv")
            elif path.stem.removeprefix("tb_") not in rtl_filenames:
                self.bad("R-N1", path, "no RTL source filename matches this testbench")

    @staticmethod
    def _skip(source_path: pathlib.PurePath) -> bool:
        # Work relative to the repository so a parent named build or ext cannot
        # accidentally disable every check. Path parts also work on Windows.
        try:
            parts = source_path.relative_to(ROOT).parts
        except ValueError:
            parts = source_path.parts
        return bool(set(parts) & SKIP_DIRECTORY_NAMES) or any(
            pair in (("rtl", "generated"), ("fpga", "synth"))
            for pair in zip(parts, parts[1:])
        )

    def report(self) -> int:
        if not self.problems:
            print("structure check: OK")
            return 0
        print(f"structure check: {len(self.problems)} violation(s)\n")
        for rule, path, message in sorted(self.problems):
            print(f"  [{rule}] {path}: {message}")
        print("\nSee docs/guidelines/CODING_STANDARDS.md for the rules.")
        return min(len(self.problems), 100)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fix-readmes", action="store_true",
                        help="create a README stub in each undocumented source directory")
    args = parser.parse_args()
    checker = Checker()
    checker.check_readmes(args.fix_readmes)
    checker.check_rtl()
    checker.check_style()
    checker.check_testbenches()
    return checker.report()


if __name__ == "__main__":
    sys.exit(main())
