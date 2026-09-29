# Checked design showcase

Download this whole folder and open `index.html` locally, or regenerate it with
`fk design demo --output design-demo`. It uses no server or model API.

The slider selects five recorded configurations. Each valid frame has a real Lean
certificate in `certificate-N/`; three invalid variants supply 15 rejection cases.
`design.json` is the declarative source and `evidence.json` records all checks.

This is a deterministic point/bar and implicit-geometry demonstration. It does not
claim continuous dynamics, mesh reconstruction, physical strength or manufacturing
certification. See [the definition semantics](../../DESIGN_DEFINITIONS.md).
