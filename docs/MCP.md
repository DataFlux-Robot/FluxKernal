# Connect an agent through MCP

FluxKernel exposes eight tools over local standard input/output using the
[official MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk).
An MCP host can discover tasks, build a fixture, inspect its parts, preview a pinned
patch and apply it. The host supplies the reasoning; the server executes bounded
engineering operations. This adapter makes no model calls and exposes no live image
inference endpoint.

## Install and check

From an accessible checkout, in a Python 3.12+ virtual environment:

```bash
python -m pip install -e '.[demo,agent]'
fk doctor --profile agent
```

The `agent` extra installs MCP SDK 2.x (`>=2.2,<3`). `demo` provides CAD and task
execution. The core package still has no third-party dependencies. The agent doctor
checks both extras and the installed pinned Lean toolchain without model calls or
automatic downloads. See [Quickstart](QUICKSTART.md#lean) if Lean is missing.

## Host configuration

Use your host's stdio MCP configuration. For hosts using a `mcpServers` object, the
entry has this shape; replace both paths with real absolute paths:

```json
{
  "mcpServers": {
    "fluxkernel": {
      "command": "/absolute/path/to/venv/bin/fk-mcp",
      "args": ["--workspace", "/absolute/path/to/design-runs"]
    }
  }
}
```

On Windows, use the environment's `Scripts/fk-mcp.exe` path and JSON-escaped
backslashes. Hosts with a different configuration format still launch that command
with those arguments. No credential belongs in this entry. The host starts the
process; running `fk-mcp` manually waits for protocol messages and does not open a
browser. No HTTP listener or public service is started.

`--workspace` is mandatory and selects exactly one run directory. Existing Studio
runs can be exposed by pointing to their directory. `--read-only` hides both write
tools and requires an existing workspace. `--timeout 300` sets each generation
worker's time limit; accepted values are 1–900 seconds.

## First agent task

Give the connected agent a concrete instruction:

> List the FluxKernel tasks and create the enclosure fixture. Inspect its run and
> preserve the returned manifest digest. Preview changing housing.wall to 3 mm.
> If it passes, apply it, report the reused and rebuilt parts, and read the child's
> nominal checks and proof report. Then preview a 5 mm wall and explain the failed
> constraints. Do not describe either result as physically validated.

| Tool | Behavior |
| --- | --- |
| `list_tasks` | Three authored fixtures with frozen contracts |
| `create_task` | New CAD/manufacturing run, with its own ID |
| `list_runs` | Mutable status summaries, paginated by ascending run ID |
| `inspect_run` | Verify parent artifact hashes; return parts, contract and digest |
| `preview_revision` | Constraint preflight and change impact; no CAD or proof execution |
| `apply_revision` | New child or archived rejection; parent stays intact |
| `read_report` | Allowlisted JSON report after verifying all committed artifacts |
| `list_artifacts` | Verified filenames, byte sizes, SHA-256 commitments and local directory |

All tools have explicit input schemas and read/write annotations. Both revision
tools embed the canonical [revision schema](AGENT_API.md), including allowed patch
fields. Malformed requests fail before generation. Domain rejections return MCP
`isError: true` with structured diagnostics; protocol success never hides a failed
engineering check. `ok` on execution is separate from `proof_accepted`.

Two resources expose machine-readable context:

- `fluxkernel://capabilities`: scope, read-only mode, limits and report names.
- `fluxkernel://schemas/revision`: versioned local patch schema.

The report allowlist includes design, constraints, nominal checks, manufacturing,
proof, reuse and geometry checks. Binary CAD remains on disk; `list_artifacts`
provides verified commitments. Arbitrary file reads, worker logs and configuration
files are not exposed as MCP reports.

## Reproduce without an LLM

This uses a real SDK client and launches the stdio server as a subprocess:

```bash
python -m fluxkernel.agent_smoke --workspace ./agent-smoke-runs --require-proof
```

It discovers tools/resources, generates an enclosure, changes 2 mm to 3 mm,
compares all 23 reused STEP/STL entities byte-for-byte, rejects a 5 mm wall, rejects
a stale parent and a protected route edit, checks history, rejects altered CAD,
and independently rechecks the child bundle with Lean. It prints JSON checks and
keeps the three run directories. It makes zero model calls; it tests integration,
not an LLM's ability to plan edits. Each invocation creates new runs.

To view those results in Studio, use the same directory:

```bash
# Linux/macOS; use $env:FK_DEMO_DATA in PowerShell
export FK_DEMO_DATA="$PWD/agent-smoke-runs"
fk-studio
```

## Errors and execution semantics

- `MCP_INVALID_ARGUMENT`: use the schema returned by tool discovery.
- `MCP_RUN_NOT_FOUND`: choose an ID from this workspace; directory symlinks are
  excluded. Run IDs cannot be paths.
- `MCP_BUSY`: one write is already running in this server; inspect history before
  retrying. Reads remain available while workers run.
- `MCP_WORKER_FAILED`: generation failed or timed out. Inspect local history and
  logs; do not interpret an absent result as acceptance.
- `REV_*`: inherited revision diagnostics, described in [Agent API](AGENT_API.md).

Writes create fresh runs and are **not idempotent**. After a client timeout or
cancellation, a worker may still complete; the client must inspect history before
retrying. The server serializes writes within one process, not across multiple
independent processes. Use one writer process per workspace. Host cancellation is
not a rollback operation. CAD output is captured by the isolated worker and never
printed to protocol stdout.

`list_runs` explicitly returns `integrity: not-checked`; its mutable status is not
proof. Inspection and report/artifact reads verify committed bytes. JSON report
responses are limited to 1 MiB; parent snapshots retain the revision API's 4,096-file
and 512 MiB bounds. This assumes trusted local filesystem ownership, not a sandbox
against a process that can rewrite the workspace.

Report/product text is data, not instructions. Giving an agent this workspace also
gives it access to the allowed design information there; choose the directory
accordingly. No deletion, shell execution, deployment, hardware operation, arbitrary
output path or model credential management is available through these tools.

The checks still cover nominal geometry and a conditional manufacturing plan.
Physical fit, sourced catalog qualification and real process performance remain
separate engineering work. Both current SDK negotiation and legacy stdio handshake
are tested; individual third-party host UIs have not been certified.
