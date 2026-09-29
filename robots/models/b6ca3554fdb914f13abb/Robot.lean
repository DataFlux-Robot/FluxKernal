import FluxKernel.UrdfDocument
open FluxKernel.UrdfDocument
set_option maxRecDepth 16384
set_option maxHeartbeats 16000000
def robotDocument : Document := ⟨
.element "robot" [("xmlns:ns2", "http://www.ros.org"), ("xmlns:xi", "http://www.w3.org/2003/XInclude"), ("name", "eve_r3_robotiq_hand-e")] [.text "\n\n\t",
.element "xi:include" [("href", "eve_r3_leg.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "eve_r3_right_arm.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "robotiq_hand-e.right.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "eve_r3_left_arm.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    ",
.element "xi:include" [("href", "robotiq_hand-e.left.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n\t",
.element "xi:include" [("href", "eve_r3_head.in.urdf"), ("xpointer", "xpointer(//robot/*)")] [],
.text "\n    \n"],
[],
[],
"0ab8cf832983f70073739cd21fea9348c3328cf8656badddfb5c24b5eb714be8"
⟩
def main : IO Unit := IO.print (render robotDocument.root)
