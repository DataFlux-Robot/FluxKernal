import FluxKernel.UrdfDocument
open FluxKernel.UrdfDocument
set_option maxRecDepth 16384
set_option maxHeartbeats 16000000
def robotDocument : Document := ⟨
.element "robot" [("name", "dummy")] [.text "\n"],
[],
[],
"d4f9908353dfc9d3ba6bc94256331c4ff95c44e4faff39c6cb2ca2e41c78a6a6"
⟩
def main : IO Unit := IO.print (render robotDocument.root)
