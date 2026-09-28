import Lean

/-! Native robot structure and controller binding. Exact decimal rationals are
represented by integer numerator / positive natural denominator. This checker
proves finite model obligations, not physical stability or numerical simulation. -/
namespace FluxKernel.Robot
structure Q where
  n : Int
  d : Nat
  deriving DecidableEq, Repr

def Q.Valid (q : Q) : Prop := q.d > 0
instance (q : Q) : Decidable q.Valid := inferInstanceAs (Decidable (q.d > 0))
def Q.le (a b : Q) : Prop := a.n * (b.d : Int) ≤ b.n * (a.d : Int)
instance (a b : Q) : Decidable (a.le b) := inferInstanceAs (Decidable (_ ≤ _))
structure Body where
  name : String
  parent : Nat
  mass : Q
  deriving DecidableEq, Repr
structure Joint where
  name : String
  body : Nat
  limited : Bool
  lower : Q
  upper : Q
  driven : Bool
  deriving DecidableEq, Repr
structure Model where
  plant : String
  controllerPlant : String
  bodies : List Body
  joints : List Joint
  actionJoints : List Nat
  deriving DecidableEq, Repr

def BodyValid (i : Nat) (b : Body) : Prop :=
  b.name ≠ "" ∧ b.parent < i + 1 ∧ b.mass.Valid ∧ b.mass.n ≥ 0
instance (i : Nat) (b : Body) : Decidable (BodyValid i b) := by unfold BodyValid; infer_instance

def JointValid (n : Nat) (j : Joint) : Prop :=
  j.name ≠ "" ∧ 0 < j.body ∧ j.body ≤ n ∧ j.lower.Valid ∧ j.upper.Valid ∧
  (j.limited = true → j.lower.le j.upper)
instance (n : Nat) (j : Joint) : Decidable (JointValid n j) := by unfold JointValid; infer_instance

def Topology (r : Model) : Prop :=
  r.bodies ≠ [] ∧ (r.bodies.map Body.name).Nodup ∧ (r.joints.map Joint.name).Nodup ∧
  (∀ p ∈ r.bodies.zipIdx, BodyValid p.2 p.1) ∧
  (∀ j ∈ r.joints, JointValid r.bodies.length j)
instance (r : Model) : Decidable (Topology r) := by unfold Topology; infer_instance

def Binding (r : Model) : Prop :=
  r.plant ≠ "" ∧ r.controllerPlant = r.plant ∧ r.actionJoints.Nodup ∧
  (∀ i ∈ r.actionJoints, i < r.joints.length ∧ (r.joints[i]?).any Joint.driven = true) ∧
  (∀ p ∈ r.joints.zipIdx, p.1.driven = true → p.2 ∈ r.actionJoints)
instance (r : Model) : Decidable (Binding r) := by unfold Binding; infer_instance

def Valid (r : Model) : Prop := Topology r ∧ Binding r
instance (r : Model) : Decidable (Valid r) := by unfold Valid; infer_instance

def check (r : Model) : Bool := decide (Valid r)
theorem check_sound (r : Model) (h : check r = true) : Valid r := of_decide_eq_true h

theorem parent_precedes (i : Nat) (b : Body) (h : BodyValid i b) : b.parent < i + 1 := h.2.1

theorem controller_bound (r : Model) (h : Valid r) : r.controllerPlant = r.plant := h.2.2.1

#print axioms check_sound
#print axioms parent_precedes
#print axioms controller_bound
end FluxKernel.Robot
