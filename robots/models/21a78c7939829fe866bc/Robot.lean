import FluxKernel.UrdfDocument
open FluxKernel.UrdfDocument
set_option maxRecDepth 16384
set_option maxHeartbeats 16000000
def robotDocument : Document := ⟨
.element "robot" [("xmlns:ns2", "http://www.ros.org"), ("xmlns:xi", "http://www.w3.org/2003/XInclude"), ("name", "eve_r3")] [.text "\n\n\t",
.element "xi:include" [("href", "eve_r3_leg.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "eve_r3_right_arm.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "qbhand.right.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "eve_r3_left_arm.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "qbhand.left.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n\t",
.element "xi:include" [("href", "eve_r3_head.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    \n"],
[],
[],
"70b924b9935480d5dca72249acaf4b263924db5778929b5670e26498f17076e1"
⟩
def main : IO Unit := IO.print (render robotDocument.root)
