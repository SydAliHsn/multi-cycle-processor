# Project checks

Run these commands from the repository root with Python 3.10 or newer:

```text
python scripts/check_structure.py
python scripts/check_docs.py
python scripts/run_unit_tests.py
python -m unittest discover -s scripts -p "test_*.py"
```

`check_structure.py` checks source-directory READMEs, RTL port naming (including
`clk_i` and `rst_ni`), procedural block types, `logic` usage, `$urandom` usage,
and unit testbench filenames. It accepts ordinary ANSI and non-ANSI module
declarations, inherited port directions, multiline declarations, and arrays.
Comments, strings, and attributes do not trigger style violations. Generated,
vendored, and build files are excluded.

The port scanner does not expand preprocessor macros or infer whether arbitrary
signals are clocks, resets, or active-low. It checks declared port suffixes and
the required clock/reset inputs. HDL compilation, lint, and review remain
necessary for syntax, clock usage, latch inference, and other semantic checks.
Verification modules are not required to expose RTL clock/reset ports.

`check_docs.py` runs the README checks independently. Module contract pages and
SPDX headers are optional under the current standards; existing documentation
and license notices are retained. There are no mandatory module prefixes,
module/file-name equality checks, array-location restrictions, file-size limits,
or YAML configuration requirements.

`run_unit_tests.py` requires Verilator and its C++ build toolchain. It discovers
`tb_*.sv` files in `verif/unit/`, builds each testbench with the RTL sources and
central lint waivers, and runs the resulting executable. The testbench top module
must match its testbench filename. A run passes only with exit status zero and a
complete `=== PASS : <n> checks ===` summary line. Build output stays in `build/unit/`.

The Python regression tests use temporary fixtures and mocked simulator results;
they do not require Verilator or PyYAML. The make targets described in the coding
standards are not yet provided by this repository; use the commands above for
the checks implemented here.
