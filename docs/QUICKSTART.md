# Quickstart / 快速开始

Choose one entry point. No step needs a local GPU. The Python package is currently
distributed from this repository or a locally built wheel; no PyPI release is implied.

| Goal | Python installation | Lean | Model credentials |
| --- | --- | --- | --- |
| Content-addressed kernel | `python -m pip install -e .` | No | No |
| Curated CAD + plan | `python -m pip install -e '.[demo]'` | Optional; missing means open proof | No |
| Accepted plan / independent verification | Demo extra | Pinned toolchain required | No |
| New image planning in Studio | Demo extra | Required for an accepted proof | Configured vision backend |

Use Python 3.12+ and an activated virtual environment. Windows users can run the
same `python -m pip` and `fk` commands from PowerShell after activating
`.venv\Scripts\Activate.ps1`. Native CAD + Lean integration is exercised on Linux;
the core installation matrix also covers Windows and macOS.

## Diagnose first

```bash
fk --version
fk doctor --json
fk doctor --profile studio
fk doctor --profile proof
fk doctor --profile live
```

Profiles check only the selected requirements. Studio checks Python packages; proof
checks the installed pinned toolchain; live includes Studio, proof and local model
configuration. These commands do not call a model, download a toolchain or expose
credentials. Package discovery does not certify that every native CAD operation
will succeed; the reference run exercises the full path.

## Lean

Install [Lean / elan using the official instructions](https://lean-lang.org/install/).
The required version is recorded in `lean-toolchain`:

```bash
elan toolchain install leanprover/lean4:v4.34.1
fk doctor --profile proof
```

From a source checkout, `lake build` also builds the proof library. Installed-wheel
runs copy the canonical proof project into their own run directory and build there;
they do not write into `site-packages`. The first toolchain installation needs network
access. After installation, the curated reference workflow needs no model or CDN.

## First full reference run

```bash
fk demo --reference phone --output ./runs --require-proof --json
```

Choose `phone`, `car` or `aircraft`. Each call creates `./runs/<unique-id>/` and never
overwrites a prior run. The output is machine-readable JSON even when the native CAD
library emits logs. `worker.log` stores worker diagnostics and is deliberately outside
the immutable bundle manifest. The reference case counts differ from the live-model
cases on the website.

The command exits zero for a completed run. A completed run may have an open proof;
`--require-proof` makes that condition nonzero. `--equipment-depth 0` deliberately
leaves machining routes without built equipment, so their closure is rejected.

```bash
python runs/<id>/verify.py runs/<id>
```

The verifier checks manifest hashes, receipt binding, the actual JSON-to-Lean
translation and the proof. It requires Lean. The manifest detects changes relative
to its snapshot; it is not a signed statement about who created the bundle.

## Studio and run storage

```bash
fk-studio --port 8740
```

Open http://127.0.0.1:8740. Bind to the default loopback address for local use; this
preview does not include a multi-user authentication or quota service.

Run location precedence:

1. `FK_DEMO_DATA` if supplied.
2. `.demo/runs/` when running from a source checkout, preserving existing history.
3. `$XDG_DATA_HOME/fluxkernel/runs` (default `~/.local/share/fluxkernel/runs`) for an
   installed package; `%LOCALAPPDATA%/fluxkernel/runs` on Windows.

To view CLI runs in Studio, set the same directory before launching it:

```bash
export FK_DEMO_DATA="$PWD/runs"
fk-studio
```

PowerShell: `$env:FK_DEMO_DATA = "$PWD/runs"`.

## Live image planning

The demo supports the configured Anthropic-compatible endpoint (including Z.ai) and
an Ollama backend. A backend must actually support the image input; a configured
model name alone is not proof of vision capability. There is no silent fallback to a
curated reference when the API fails.

For the current GLM setup, create a private `~/.config/fluxkernel/model.json`:

```json
{
  "provider": "anthropic",
  "base_url": "https://api.z.ai/api/anthropic",
  "model": "glm-5.3-flash",
  "api_key": "YOUR_PRIVATE_KEY"
}
```

Use user-only permissions (`chmod 600` on POSIX). Alternatively use
`FK_MODEL_API_KEY`, `FK_MODEL_BASE_URL` and `FK_VISION_MODEL` with no configuration
file. `FK_MODEL_CONFIG` selects another private file. Existing file values currently
take precedence over corresponding environment defaults. Default requests ignore
system proxies; `trust_env: true` in the private JSON explicitly enables them.

Start Studio, select or upload an image, keep reference replay unchecked, then
submit. The backend retains its model request and response as run evidence. Do not
share a live run bundle without reviewing the product image and supplied requirements.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| `fk` not found | Activate the same environment in which you installed the package. |
| Missing OCP / FastAPI | Install `.[demo]` from the repository, or `path/to/fluxkernel.whl[demo]`. |
| Proof stays open | Run `fk doctor --profile proof`, inspect `lean-check.log`, and rerun the bundle verifier after installing Lean. |
| Missing model | Choose reference replay for local exploration, or configure a vision-capable backend. |
| Port already used | Choose `fk-studio --port 8741`. |
| Failed run | Keep `status.json` and `worker.log`; redact private inputs before reporting. |
| Native DLL loading failure | Use a compatible Python/CAD wheel or try WSL; do not disable operating-system protections as a setup step. |

An independently successful recheck does not rewrite the original run's recorded
proof status; that status describes the original execution.
