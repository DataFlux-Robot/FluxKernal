import FluxKernel.UrdfDocument
open FluxKernel.UrdfDocument
set_option maxRecDepth 16384
set_option maxHeartbeats 16000000
def robotDocument : Document := ⟨
.element "robot" [("xmlns:ns2", "http://www.ros.org"), ("xmlns:xi", "http://www.w3.org/2003/XInclude"), ("name", "eve_r3_robotiq_2f_85")] [.text "\n\n\t",
.element "xi:include" [("href", "eve_r3_leg.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "eve_r3_right_arm.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "robotiq_2f_85.right.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "eve_r3_left_arm.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "robotiq_2f_85.left.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n\t",
.element "xi:include" [("href", "eve_r3_head.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    \n"],
[],
[],
"ff9dd755528f6f02715094eba7348e81b9a6a10a395e848e9bf82a78d24b95ac"
⟩
def main : IO Unit := IO.print (render robotDocument.root)
