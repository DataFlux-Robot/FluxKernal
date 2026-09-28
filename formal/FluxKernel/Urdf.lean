import FluxKernel.Robot

/-! A finite, exact certificate for the mechanism subset crossing the URDF boundary.
XML parsing and native record extraction are outside Lean's trusted theorem scope.
Frames, mesh geometry, trigonometry and physical behavior are not proved here. -/
namespace FluxKernel.Robot.Urdf

structure Link where
  name : String
  mass : Q
  deriving DecidableEq, Repr

structure Joint where
  name : String
  parent : String
  child : String
  kind : Nat -- fixed=0, revolute=1, continuous=2, prismatic=3
  axis : List Q
  lower : Q
  upper : Q
  reference : Q
  effort : Q
  velocity : Q
  deriving DecidableEq, Repr

structure Mechanism where
  links : List Link
  joints : List Joint
  deriving DecidableEq, Repr

def EqualQ (a b : Q) : Prop :=
  a.Valid ∧ b.Valid ∧ a.n * (b.d : Int) = b.n * (a.d : Int)
instance (a b : Q) : Decidable (EqualQ a b) := by unfold EqualQ; infer_instance

def Shifted (native exported reference : Q) : Prop :=
  native.Valid ∧ exported.Valid ∧ reference.Valid ∧
  exported.n * (native.d : Int) * (reference.d : Int) =
    (native.n * (reference.d : Int) - reference.n * (native.d : Int)) * (exported.d : Int)
instance (a b c : Q) : Decidable (Shifted a b c) := by unfold Shifted; infer_instance

def LinkMatches (a b : Link) : Prop := a.name = b.name ∧ EqualQ a.mass b.mass
instance (a b : Link) : Decidable (LinkMatches a b) := by unfold LinkMatches; infer_instance

def JointMatches (a b : Joint) : Prop :=
  a.name = b.name ∧ a.parent = b.parent ∧ a.child = b.child ∧ a.kind = b.kind ∧
  a.kind ≤ 3 ∧ EqualQ b.reference ⟨0, 1⟩ ∧
  (a.kind ≠ 0 → a.axis.length = 3 ∧ b.axis.length = 3 ∧
    (∀ pair ∈ a.axis.zip b.axis, EqualQ pair.1 pair.2) ∧
    (∃ q ∈ a.axis, q.n ≠ 0) ∧
    EqualQ a.effort b.effort ∧ a.effort.n ≥ 0 ∧
    EqualQ a.velocity b.velocity ∧ a.velocity.n ≥ 0) ∧
  (a.kind = 1 ∨ a.kind = 3 → a.lower.le a.upper ∧ b.lower.le b.upper ∧
    Shifted a.lower b.lower a.reference ∧ Shifted a.upper b.upper a.reference)
instance (a b : Joint) : Decidable (JointMatches a b) := by unfold JointMatches; infer_instance

def Preserved (native exported : Mechanism) : Prop :=
  native.links ≠ [] ∧ (native.links.map Link.name).Nodup ∧
  (native.joints.map Joint.name).Nodup ∧
  native.links.length = exported.links.length ∧
  native.joints.length = exported.joints.length ∧
  (∀ pair ∈ native.links.zip exported.links, LinkMatches pair.1 pair.2) ∧
  (∀ pair ∈ native.joints.zip exported.joints, JointMatches pair.1 pair.2)
instance (a b : Mechanism) : Decidable (Preserved a b) := by unfold Preserved; infer_instance

def check (a b : Mechanism) : Bool := decide (Preserved a b)
theorem check_sound (a b : Mechanism) (h : check a b = true) : Preserved a b :=
  of_decide_eq_true h

theorem joint_type_preserved (a b : Joint) (h : JointMatches a b) : a.kind = b.kind :=
  h.2.2.2.1

#print axioms check_sound
#print axioms joint_type_preserved
end FluxKernel.Robot.Urdf
