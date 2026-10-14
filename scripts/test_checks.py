"""Regression tests for the project checks; no HDL tools are required."""
from __future__ import annotations

import io
import pathlib
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import check_docs
import check_structure as structure
import run_unit_tests as runner

REPOSITORY = pathlib.Path(__file__).resolve().parent.parent


class RepositoryFixture(unittest.TestCase):
    def setUp(self) -> None:
        temporary_parent = REPOSITORY / "build" / "script-tests"
        temporary_parent.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix="case-", dir=temporary_parent)
        self.root = pathlib.Path(temporary.name).resolve()
        # Keep automatic recursive cleanup inside the dedicated fixture directory.
        self.assertEqual(self.root.parent, temporary_parent.resolve())
        self.addCleanup(temporary.cleanup)
        root_patch = patch.object(structure, "ROOT", self.root)
        root_patch.start()
        self.addCleanup(root_patch.stop)

    def write(self, name: str, text: str) -> pathlib.Path:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path


class StructureTest(RepositoryFixture):
    def rtl_problems(self, source: str) -> list[tuple[str, str, str]]:
        self.write("rtl/arbitrary_filename.sv", source)
        checker = structure.Checker()
        checker.check_rtl()
        return checker.problems

    def test_current_rules_accept_removed_requirements(self) -> None:
        self.write("rtl/README.md", "# RTL\n")
        self.write("scripts/README.md", "# Scripts\n")
        self.write("scripts/helper.py", "# No license header required.\n" * 801)
        self.write("rtl/arbitrary_filename.sv", """
module processor_regfile(input logic clk_i, input logic rst_ni,
                         output logic [31:0] result_o);
  logic [31:0] registers [32];
  always_comb result_o = '0;
endmodule
""")
        # Fail if an undeclared YAML dependency is reintroduced, even on machines
        # where PyYAML happens to be installed.
        with patch.dict(sys.modules, {"yaml": None}), patch.object(sys, "argv", ["check_structure.py"]):
            with redirect_stdout(io.StringIO()):
                self.assertEqual(structure.main(), 0)
                self.assertEqual(check_docs.main(), 0)

    def test_parameterized_multiline_ports_and_arrays(self) -> None:
        self.assertEqual(self.rtl_problems("""
module processor_regfile #(parameter int WIDTH = 32, N_READ = 2) (
  input logic clk_i, rst_ni,
  input logic [WIDTH-1:0] a_i [N_READ], b_i [N_READ],
  (* keep = "true" *) input logic enable_ni,
  output logic ready_no,
  inout logic bus_io,
  output logic [WIDTH-1:0]
    result_o [N_READ]
);
  function automatic logic helper(input logic unconstrained);
    return unconstrained;
  endfunction
endmodule
"""), [])

    def test_nested_default_expressions_do_not_split_ports(self) -> None:
        self.assertEqual(self.rtl_problems("""
module example(input logic clk_i, rst_ni,
               input logic [1:0] value_i = {1'b0, 1'b1},
               output logic result_o);
endmodule
"""), [])

    def test_non_ansi_ports_exclude_task_arguments(self) -> None:
        self.assertEqual(self.rtl_problems("""
module example(clk_i, rst_ni, data_i, result_o);
input logic clk_i, rst_ni;
input logic [7:0] data_i;
output logic [7:0] result_o;
task helper;
  input logic data_i;
  input logic unrelated;
endtask
endmodule
"""), [])

    def test_port_suffixes_match_direction(self) -> None:
        problems = self.rtl_problems("""
module example(input logic clk_i, rst_ni,
               input logic request_o, output logic result_i, inout logic bus_o);
endmodule
""")
        self.assertEqual([p[0] for p in problems], ["R-N2"] * 3)

    def test_final_port_is_checked(self) -> None:
        problems = self.rtl_problems("""
module example(
 input logic clk_i,
 input logic rst_ni,
 output logic result
);
endmodule
""")
        self.assertEqual(len(problems), 1)
        self.assertIn("result", problems[0][2])

    def test_inherited_direction_is_checked(self) -> None:
        problems = self.rtl_problems("""
module example(input logic clk_i, rst_ni, good_i, bad_o);
endmodule
""")
        self.assertEqual([p[0] for p in problems], ["R-N2"])

    def test_misplaced_active_low_marker_is_rejected(self) -> None:
        problems = self.rtl_problems("""
module example(input logic clk_i, rst_ni, enable_i_n);
endmodule
""")
        self.assertEqual([p[0] for p in problems], ["R-N3"])

    def test_each_module_requires_clock_and_reset_inputs(self) -> None:
        problems = self.rtl_problems("""
module good(input logic clk_i, rst_ni); endmodule
module missing(input logic data_i); endmodule
""")
        self.assertEqual([p[0] for p in problems], ["R-N5", "R-N5"])
        self.assertTrue(all("missing:" in p[2] for p in problems))

    def test_duplicate_clock_is_rejected(self) -> None:
        problems = self.rtl_problems("module example(input logic clk_i, clk_i, rst_ni); endmodule")
        self.assertEqual([p[0] for p in problems], ["R-N5"])

    def test_testbench_does_not_need_rtl_clock_ports(self) -> None:
        self.write("verif/unit/tb_example.sv", "module tb_example; endmodule")
        checker = structure.Checker()
        checker.check_rtl()
        self.assertEqual(checker.problems, [])

    def test_all_legacy_always_forms_are_rejected(self) -> None:
        for statement in ("always @*", "always @(*)", "always @(a_i)", "always", "always #5"):
            with self.subTest(statement=statement):
                self.write("rtl/example.sv", statement + " begin end\n(* keep = 1 *) logic foo;")
                checker = structure.Checker()
                checker.check_style()
                self.assertEqual([p[0] for p in checker.problems], ["R-C1"])

    def test_inline_legacy_declarations_and_random_are_rejected(self) -> None:
        self.write("rtl/example.sv", "module example(input wire data_i); reg value; initial value = $random; endmodule")
        checker = structure.Checker()
        checker.check_style()
        self.assertCountEqual([p[0] for p in checker.problems], ["R-C2", "R-C2", "R-V4"])

    def test_comments_strings_and_attributes_are_not_code(self) -> None:
        self.write("rtl/example.sv", r'''
// Use $urandom instead of $random; never use always, wire, or reg.
/* module fake(input wire broken); always @* reg x; endmodule */
module example(input logic clk_i, rst_ni);
  (* note = "always reg wire $random" *) logic result;
  initial $display("escaped quote: \" always wire reg $random //");
  always_ff @(posedge clk_i) result <= $urandom;
endmodule
''')
        checker = structure.Checker()
        checker.check_rtl()
        checker.check_style()
        self.assertEqual(checker.problems, [])

    def test_generated_and_build_files_are_skipped(self) -> None:
        for directory in ("rtl/generated", "fpga/synth", "obj_dir", "build", "ext"):
            self.write(directory + "/example.sv", "module bad; always @* begin end endmodule")
        checker = structure.Checker()
        checker.check_rtl()
        checker.check_style()
        self.assertEqual(checker.problems, [])
        self.assertFalse(checker._skip(self.root / "rtl" / "core" / "example.sv"))

    def test_generated_path_exclusion_is_portable(self) -> None:
        for path_type in (pathlib.PureWindowsPath, pathlib.PurePosixPath):
            with self.subTest(path_type=path_type):
                self.assertTrue(structure.Checker._skip(path_type("rtl/generated/example.sv")))
                self.assertFalse(structure.Checker._skip(path_type("rtl/core/example.sv")))

    def test_testbench_matches_filename_not_module_name(self) -> None:
        self.write("rtl/custom_name.sv", "module processor_regfile; endmodule")
        self.write("verif/unit/tb_custom_name.sv", "module tb_custom_name; endmodule")
        checker = structure.Checker()
        checker.check_testbenches()
        self.assertEqual(checker.problems, [])

    def test_bad_testbench_filenames_are_rejected(self) -> None:
        self.write("verif/unit/wrong.sv", "")
        self.write("verif/unit/tb_missing.sv", "")
        checker = structure.Checker()
        checker.check_testbenches()
        self.assertCountEqual([p[0] for p in checker.problems], ["R-V1", "R-N1"])

    def test_nested_source_directory_needs_readme(self) -> None:
        self.write("rtl/README.md", "# RTL")
        self.write("rtl/new_component/source.sv", "")
        checker = structure.Checker()
        checker.check_readmes()
        self.assertEqual([p[0] for p in checker.problems], ["R-D1"])
        checker = structure.Checker()
        checker.check_readmes(fix_missing=True)
        self.assertEqual(checker.problems, [])
        self.assertIn("CODING_STANDARDS.md", (self.root / "rtl/new_component/README.md").read_text())


class RunnerTest(RepositoryFixture):
    def simulate(self, stdout: str, returncode: int = 0, build_returncode: int = 0) -> dict:
        responses = [subprocess.CompletedProcess([], build_returncode, "", "build diagnostics")]
        if build_returncode == 0:
            responses.append(subprocess.CompletedProcess([], returncode, stdout, ""))
        with patch.object(runner, "BUILD", self.root / "build"), patch.object(runner, "ROOT", self.root):
            with patch.object(runner.subprocess, "run", side_effect=responses):
                return runner.run_one(self.root / "tb_example.sv", [], keep=True)

    def test_complete_pass_summary_is_accepted(self) -> None:
        result = self.simulate("simulator startup\r\n=== PASS : 12 checks ===\r\nfinished\n")
        self.assertTrue(result["ok"])
        self.assertEqual(result["checks"], 12)

    def test_incomplete_or_embedded_pass_text_is_rejected(self) -> None:
        for output in ("=== PASS", "=== PASSING WITHOUT CHECKS", "=== PASS : 3 checks",
                       "prefix === PASS : 3 checks ===", "=== PASS : 3 checks === suffix",
                       "=== PASS :\n3 checks ===", ""):
            with self.subTest(output=output):
                self.assertFalse(self.simulate(output)["ok"])

    def test_nonzero_exit_fails_even_with_pass_summary(self) -> None:
        self.assertFalse(self.simulate("=== PASS : 12 checks ===", returncode=1)["ok"])

    def test_build_failure_is_reported(self) -> None:
        result = self.simulate("", build_returncode=1)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "build")

    def test_invalid_job_count_has_clear_error(self) -> None:
        with patch.object(sys, "argv", ["run_unit_tests.py", "--jobs", "0"]):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                runner.main()
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
