# Reporting security issues

Please do not place credentials or sensitive product inputs in issues. While this
repository is private, report a vulnerability through a private issue to its
maintainers or the existing collaborator channel. When the repository becomes
public, a dedicated private reporting route must be enabled before launch.

Include the affected commit, the smallest reproduction, the expected trust boundary,
and whether the problem exposes data, executes code or falsely accepts evidence.

## Current trust boundaries

- Studio is a local development service, bound to loopback by default. It has no
  multi-user authentication or request quota system.
- Model output is parsed as a bounded design schema; it is not executed as Python.
- The manifest is an integrity snapshot, not a cryptographic signature of authorship.
- A Lean proof concerns a formal plan under stated assumptions. It does not attest
  to a supplier, real equipment capability or the truth of input observations.
- Independently verifying an untrusted bundle involves a compiler/toolchain; inspect
  its contents and use an isolated environment before executing supplied code.

API keys belong in private configuration or environment variables, never fixtures,
frontend code or exported documentation. Review live-run images, requirements and
model responses before sharing an evidence bundle.
