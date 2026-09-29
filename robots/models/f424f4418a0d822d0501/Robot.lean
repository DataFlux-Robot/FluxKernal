import FluxKernel.UrdfDocument
open FluxKernel.UrdfDocument
set_option maxRecDepth 16384
set_option maxHeartbeats 16000000
def robotDocument : Document := ⟨
.element "robot" [("name", "architrave")] [.text "\n\n  ",
.element "link" [("name", "base_link")] [.text " \n\n    ",
.element "inertial" [] [.text "\n      ",
.element "origin" [("rpy", "0 0 0"), ("xyz", "0 0 0")] [],
.text "\n      ",
.element "mass" [("value", "0.3")] [],
.text "\n      ",
.element "inertia" [("ixx", "0"), ("ixy", "0.0"), ("ixz", "0.0"), ("iyy", "0"), ("iyz", "0.0"), ("izz", "0")] [],
.text "\n    "],
.text "\n\n    ",
.element "visual" [] [.text "\n      ",
.element "origin" [("rpy", "0 0 0"), ("xyz", "0 0 0")] [],
.text "\n      ",
.element "geometry" [] [.text "\n        ",
.element "box" [("size", ".8 .05 .05")] [],
.text "\n      "],
.text " \n      ",
.element "material" [("name", "grey")] [.text "\n        ",
.element "color" [("rgba", ".5 .5 .5 1")] [],
.text "\n      "],
.text " \n    "],
.text "\n\n    ",
.element "collision" [] [.text "\n      ",
.element "origin" [("rpy", "0 0 0"), ("xyz", "0 0 0")] [],
.text "\n      ",
.element "geometry" [] [.text "\n        ",
.element "box" [("size", ".8 .05 .05")] [],
.text "\n      "],
.text "\n    "],
.text "  \n\n  "],
.text "\n\n"],
[],
[],
"b8e2651fa15fbebd14da9928f7b844cf1e1200c61842359585a1d9e30c8aa447"
⟩
def main : IO Unit := IO.print (render robotDocument.root)
