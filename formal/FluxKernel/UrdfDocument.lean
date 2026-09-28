/- Complete URDF XML information model. Decimal strings are intentionally not
   converted through floating point. This is an executable representation, not
   a proof of the external XML parser or of physical correctness. -/
namespace FluxKernel.UrdfDocument

inductive Node where
  | text : String → Node
  | element : String → List (String × String) → List Node → Node
  deriving Repr

structure Resource where
  path : String
  sha256 : String
  deriving Repr

structure Document where
  root : Node
  assets : List Resource
  nativeFiles : List Resource
  lexicalSha256 : String
  deriving Repr

def escape (s : String) : String :=
  s.replace "&" "&amp;" |>.replace "<" "&lt;" |>.replace ">" "&gt;"
    |>.replace "\"" "&quot;" |>.replace "\t" "&#9;"
    |>.replace "\n" "&#10;" |>.replace "\r" "&#13;"

def render : Node → String
  | .text value => escape value
  | .element name attrs children =>
    "<" ++ name ++ String.join (attrs.map fun (key, value) =>
      " " ++ key ++ "=\"" ++ escape value ++ "\"") ++ ">" ++
      String.join (children.map render) ++ "</" ++ name ++ ">"

end FluxKernel.UrdfDocument
