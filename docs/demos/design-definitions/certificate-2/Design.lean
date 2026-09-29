import Lean

/- Exact, dimensioned design expressions. This checks declared finite instances;
   it does not prove continuum dynamics, collision freedom or manufacturability. -/
namespace FluxKernel.Design

structure Dim where
  length : Int
  mass : Int
  time : Int
  deriving DecidableEq, Repr

def Dim.add (a b : Dim) : Dim :=
  ⟨a.length + b.length, a.mass + b.mass, a.time + b.time⟩
def Dim.sub (a b : Dim) : Dim :=
  ⟨a.length - b.length, a.mass - b.mass, a.time - b.time⟩

structure Quantity where
  value : Rat
  dim : Dim
  deriving Repr

inductive Expr where
  | literal : Rat → Dim → Expr
  | parameter : Nat → Expr
  | add : Expr → Expr → Expr
  | sub : Expr → Expr → Expr
  | mul : Expr → Expr → Expr
  | div : Expr → Expr → Expr
  deriving Repr

def eval (env : List Quantity) : Expr → Option Quantity
  | .literal v d => some ⟨v, d⟩
  | .parameter i => env[i]?
  | .add a b => do
    let a ← eval env a; let b ← eval env b
    if a.dim = b.dim then some ⟨a.value + b.value, a.dim⟩ else none
  | .sub a b => do
    let a ← eval env a; let b ← eval env b
    if a.dim = b.dim then some ⟨a.value - b.value, a.dim⟩ else none
  | .mul a b => do
    let a ← eval env a; let b ← eval env b
    some ⟨a.value * b.value, a.dim.add b.dim⟩
  | .div a b => do
    let a ← eval env a; let b ← eval env b
    if b.value = 0 then none else some ⟨a.value / b.value, a.dim.sub b.dim⟩

inductive Relation where
  | eq | le | lt
  deriving Repr

def Relation.Holds : Relation → Rat → Rat → Prop
  | .eq, a, b => a = b
  | .le, a, b => a ≤ b
  | .lt, a, b => a < b
instance (r : Relation) (a b : Rat) : Decidable (r.Holds a b) := by
  cases r <;> unfold Relation.Holds <;> infer_instance

structure Clause where
  lhs : Expr
  rhs : Expr
  relation : Relation
  deriving Repr

def Clause.Valid (env : List Quantity) (c : Clause) : Prop :=
  match eval env c.lhs, eval env c.rhs with
  | some a, some b => a.dim = b.dim ∧ c.relation.Holds a.value b.value
  | _, _ => False
instance (env : List Quantity) (c : Clause) : Decidable (c.Valid env) := by
  unfold Clause.Valid; split <;> infer_instance

inductive Predicate where
  | atom : Clause → Predicate
  | and : Predicate → Predicate → Predicate
  | or : Predicate → Predicate → Predicate
  | not : Predicate → Predicate
  deriving Repr

def Predicate.eval (env : List Quantity) : Predicate → Option Bool
  | .atom c => do
    let a ← FluxKernel.Design.eval env c.lhs
    let b ← FluxKernel.Design.eval env c.rhs
    if a.dim = b.dim then some (decide (c.relation.Holds a.value b.value)) else none
  | .and a b => do
    let a ← a.eval env; let b ← b.eval env
    some (a && b)
  | .or a b => do
    let a ← a.eval env; let b ← b.eval env
    some (a || b)
  | .not a => do
    let a ← a.eval env
    some (!a)

structure Parameter where
  value : Quantity
  lower : Rat
  upper : Rat
  deriving Repr

def Parameter.Valid (p : Parameter) : Prop :=
  p.lower ≤ p.value.value ∧ p.value.value ≤ p.upper
instance (p : Parameter) : Decidable p.Valid := by unfold Parameter.Valid; infer_instance

structure Model where
  parameters : List Parameter
  clauses : List Clause
  predicates : List Predicate
  deriving Repr

def Valid (m : Model) : Prop :=
  m.clauses ≠ [] ∧ (∀ p ∈ m.parameters, p.Valid) ∧
  (∀ c ∈ m.clauses, c.Valid (m.parameters.map Parameter.value)) ∧
  (∀ p ∈ m.predicates, p.eval (m.parameters.map Parameter.value) = some true)
instance (m : Model) : Decidable (Valid m) := by unfold Valid; infer_instance

def check (m : Model) : Bool := decide (Valid m)
theorem check_sound (m : Model) (h : check m = true) : Valid m := of_decide_eq_true h

/- A genuine universally quantified family theorem, separate from finite checks.
   Under the unit-circle assumption these four points have the required bar
   lengths for all rational a,b,u,v. No nonsingularity/dynamics claim is made. -/
def distanceSq (p q : Rat × Rat) : Rat :=
  (p.1-q.1)*(p.1-q.1) + (p.2-q.2)*(p.2-q.2)

theorem parallelogram_family (a b u v : Rat) (circle : u*u + v*v = 1) :
    distanceSq (0, 0) (a, 0) = a*a ∧
    distanceSq (a, 0) (a+b*u, b*v) = b*b ∧
    distanceSq (a+b*u, b*v) (b*u, b*v) = a*a ∧
    distanceSq (b*u, b*v) (0, 0) = b*b := by
  dsimp [distanceSq]
  grind

#print axioms check_sound
#print axioms parallelogram_family
end FluxKernel.Design
