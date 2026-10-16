# RISC-V Processor & Peripherals Coding Standard

**Status:** Active · **Enforced by:** `make check`

> Rules with a **[auto]** tag are checked by `scripts/check_structure.py` or the linter and will
> fail CI. Rules without it are review items. A rule nobody can check is advice, not a standard —
> so when you propose a new rule, propose the check with it.

Run before every push:

```bash
make check      # structure
make lint       # lint
make test-unit  # your testbench
```

## 1. Purpose and Scope

This document establishes consistent coding, verification, and collaboration practices for the RISC-V processor and peripherals project, including the five-stage pipeline, branch prediction, VGA and joystick interfaces, and RISC-V assembly software.

Consistency allows team members to integrate hardware and software components, debug issues efficiently, and review changes safely.

Two rules receive particular attention:

- **R-C3:** Assign default values before combinational branching to prevent unintended latch inference.
- **R-V2:** Derive test expectations from design parameters rather than hard-coded values to keep tests valid when configurations change.

## 2. Naming — R-N

| ID | Rule | Enforcement |
|---|---|---|
| **R&#8209;N1** | Source file names may be chosen freely, but the corresponding testbench must follow the `tb_<filename>.sv` convention, using the source filename without its extension. | [auto] |
| **R&#8209;N2** | Ports use direction suffixes: `_i` for inputs, `_o` for outputs, and `_io` for bidirectional signals. | [auto] |
| **R&#8209;N3** | Active-low signals place `_n` before the direction suffix. For example, `rst_ni` is an active-low reset input. | [auto] |
| **R&#8209;N4** | Use `UPPER_SNAKE_CASE` for parameters and enumerated values, `lower_snake_case` for signals and variables, `lower_snake_case_t` for type names, and `lower_snake_case_e` for enumeration types. | |
| **R&#8209;N5** | Use `clk_i` for the clock and `rst_ni` for the active-low reset. Each module must have one clock and one reset. | [auto] |

Example:

```systemverilog
module processor_regfile
#(
  parameter int unsigned N_READ = 2
) (
  input  logic                  clk_i,
  input  logic                  rst_ni,
  input  logic [REG_ADDR_W-1:0] raddr_i [N_READ],
  output logic [XLEN-1:0]       rdata_o [N_READ]
);
```

Apply these conventions consistently across RTL modules, testbenches, and supporting code. Exceptions must be documented and agreed upon by the team.

## 3. RTL Coding — R-C

### R-C1 — Use explicit procedural block types [auto]

Use `always_ff` for sequential logic, `always_comb` for combinational logic, and `always_latch` only when a latch is intentional.

Do not use bare `always` or `always @(...)` blocks. Explicit block types communicate design intent and help tools detect incorrect coding patterns.

### R-C2 — Use `logic` instead of `reg` or `wire` [auto]

Use SystemVerilog `logic` for signals and variables instead of legacy `reg` and `wire` declarations.

### R-C3 — Assign defaults before combinational branching [auto]

Assign default values to combinational outputs and intermediate signals before conditional logic or `case` statements. Ensure every output has a defined value on every execution path.

This prevents unintended latch inference.

```systemverilog
// GOOD
always_comb begin
  result_o = '0;  // Default assignment

  case (op_i)
    ALU_ADD: result_o = sum;
    ALU_AND: result_o = a_i & b_i;
    // Other operations
    default: result_o = '0;
  endcase
end
```

### R-C4 — Use appropriate assignment operators

- Use blocking assignments (`=`) in combinational procedural blocks.
- Use nonblocking assignments (`<=`) in sequential procedural blocks.
- Do not assign the same signal from both combinational and sequential blocks.
- Use explicit signal widths and signedness wherever appropriate to avoid unintended truncation, extension, or comparison behavior.

## 4. Lint — R-L

| ID | Rule | Enforcement |
|---|---|---|
| **R&#8209;L1** | `make lint` must complete without unapproved warnings or errors. | [auto] |
| **R&#8209;L2** | Every lint waiver must be recorded in `verif/verilator.vlt` and include a justification comment. | [auto] |
| **R&#8209;L3** | Never add inline suppressions solely to make CI pass. Fix the underlying issue or document an approved waiver centrally. | |

Lint warnings must be reviewed rather than ignored. Intentional exceptions must be justified and documented.

## 5. Documentation — R-D

| ID | Rule | Enforcement |
|---|---|---|
| **R&#8209;D1** | Every maintained source directory must contain a `README.md` explaining its contents and purpose. | [auto] |
| **R&#8209;D2** | Comments must explain why a design decision or operation is necessary, rather than merely restating what the code does. | |

## 6. Verification — R-V

| ID | Rule | Enforcement |
|---|---|---|
| **R&#8209;V1** | Unit testbenches must be located in `verif/unit/` and follow the `tb_<filename>.sv` naming convention. | [auto] |
| **R&#8209;V2** | Derive expected results from design parameters and configuration values instead of hard-coded constants wherever those values depend on the configuration. | |
| **R&#8209;V3** | Successful tests must print `=== PASS : <n> checks ===` and return a non-zero exit status on failure. | [auto] |
| **R&#8209;V4** | Use `$urandom` instead of `$random` for randomized stimulus. Seed random tests when reproducibility is required. | [auto] |
| **R&#8209;V5** | Test failure-prone behavior, including pipeline stalls, hazard forwarding, reset sequences, and other conditions that may cause incorrect operation or hangs. | |

### Verification requirements

- Provide unit tests for each major independently testable module.
- Verify normal operation, boundary conditions, reset behavior, and invalid inputs where applicable.
- Use self-checking testbenches that compare actual results with expected results.
- Test control signals as well as output data.
- Include integration tests for interactions between the processor, memory, and peripherals.
- Ensure failed checks produce an explicit failure message and a non-zero simulator exit status.
- Keep randomized tests reproducible when debugging or reproducing failures.

The verification suite should cover arithmetic and logical instructions, register-file behavior, memory accesses, branches, jumps, processor control, and any implemented hazard-handling mechanisms.

## 7. Git and Collaboration — R-G

| ID | Rule | Enforcement |
|---|---|---|
| **R&#8209;G1** | Never commit generated build output. Ensure `build/`, `*.vcd`, `obj_dir/`, and `fpga/synth/` are covered by `.gitignore`. | [auto] |

### Branching

Keep `main` in a working, reasonably stable state. Use descriptive branches for independent features, fixes, and documentation changes.

Examples:

```text
alu-implementation
control-unit
branch-prediction
vga-controller
hazard-forwarding
coding-standards
```

### Commit messages

Use concise, descriptive commit subjects.

Examples:

```text
Add ALU implementation
Implement processor controller
Add register file testbench
Correct branch target calculation
Update project documentation
```

Avoid vague messages such as `changes`, `update`, or `final code`.

### Code review

- Review changes before merging them into `main`.
- Keep each pull request focused on a related set of changes.
- Verify that affected modules compile and relevant tests pass.
- Review interfaces, signal widths, reset behavior, and possible latch inference.
- Resolve review feedback before merging.
- Coordinate changes to shared interfaces with other contributors.

## 8. Pull Request Template

Copy the following template into each pull request description.

```markdown
## What
Describe the hardware component, script, or software feature being added or modified.

## Why
Explain the reason for the change and the relevant architectural decisions.

> Closes #__

## Verification
Describe the tests performed and their results.

## Checklist
- [ ] Structural checks pass (`make check`).
- [ ] RTL lint passes (`make lint`).
- [ ] Unit testbenches pass (`make test-unit`).
- [ ] Unit testbenches were added or updated in `verif/unit/`.
- [ ] Synthesis warnings were reviewed; no unintended latches were introduced.
- [ ] Documentation was updated where necessary.
- [ ] Framebuffer, peripheral, and assembly behaviour was tested where affected.
```
