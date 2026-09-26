import Lean

/-!
Finite manufacturing-plan checker. It proves structural closure and bootstrap
ordering under declared external capabilities. It does NOT prove that a physical
printer, catalog item, material or numerical solver satisfies its declaration.
All indices name occurrences, not just content hashes: identical parts can have
different production histories. Dependency indices must be strictly earlier.
-/
namespace FluxKernel

inductive Route where
  | seed | catalog | print | machine | assemble | equipment
  deriving DecidableEq, Repr

structure Step where
  route : Route
  deps : List Nat
  depth : Nat
  /-- Reference to a checked, bound external receipt; not a physical theorem. -/
  receipt : String
  deriving DecidableEq, Repr

structure Policy where
  equipmentDepth : Nat
  deriving DecidableEq, Repr

def dependenciesEarlier (index : Nat) (step : Step) : Prop :=
  ∀ dep ∈ step.deps, dep < index

instance (i : Nat) (s : Step) : Decidable (dependenciesEarlier i s) :=
  inferInstanceAs (Decidable (∀ d ∈ s.deps, d < i))

def RouteValid (step : Step) : Prop :=
  step.receipt ≠ "" ∧
  match step.route with
  | .seed | .catalog => step.deps = []
  | .print | .machine | .assemble | .equipment => step.deps ≠ []

instance (s : Step) : Decidable (RouteValid s) := by
  unfold RouteValid
  cases s.route <;> infer_instance

def StepValid (policy : Policy) (index : Nat) (step : Step) : Prop :=
  dependenciesEarlier index step ∧ RouteValid step ∧
  step.depth ≤ policy.equipmentDepth

instance (p : Policy) (i : Nat) (s : Step) : Decidable (StepValid p i s) :=
  inferInstanceAs (Decidable (_ ∧ _ ∧ _))

/-- A construction derivation using only validated earlier production steps. -/
inductive Closed (policy : Policy) : List Step → Prop where
  | nil : Closed policy []
  | snoc {built : List Step} {step : Step} :
      Closed policy built → StepValid policy built.length step →
      Closed policy (built ++ [step])

def checkFrom (policy : Policy) : Nat → List Step → Bool
  | _, [] => true
  | index, step :: rest => decide (StepValid policy index step) &&
      checkFrom policy (index + 1) rest

def hasRoute (steps : List Step) (step : Step) (route : Route) : Bool :=
  step.deps.any fun dep => (steps[dep]?).any fun prior => prior.route == route

/-- Machines need a previously constructed equipment instance and a printed
workpiece; printing needs the externally declared seed printer. Equipment itself
must be constructed from catalog and printed parts. -/
def typedRoutes (steps : List Step) : Bool := steps.all fun step =>
  match step.route with
  | .seed => step.depth == 0
  | .catalog => true
  | .print => hasRoute steps step .seed
  | .machine => hasRoute steps step .equipment && hasRoute steps step .print && step.depth == 0
  | .equipment => hasRoute steps step .catalog && hasRoute steps step .print && step.depth == 1
  | .assemble => true

def reachable (steps : List Step) : Nat → Nat → Nat → Bool
  | 0, _, _ => false
  | fuel + 1, origin, target => origin == target ||
      (steps[origin]?).any fun step => step.deps.any fun dep => reachable steps fuel dep target

/-- The last step is the product assembly and every occurrence contributes to
its construction. Unused equipment cannot be counted as recursive manufacture. -/
def rootCovered (steps : List Step) : Bool :=
  !steps.isEmpty && (steps.getLast?).any (fun s => s.route == .assemble) &&
  (List.range steps.length).all (fun i => reachable steps steps.length (steps.length - 1) i)

def check (policy : Policy) (steps : List Step) : Bool :=
  checkFrom policy 0 steps && typedRoutes steps && rootCovered steps

structure VerifiedPlan (policy : Policy) (steps : List Step) : Prop where
  closure : Closed policy steps
  routeTypes : typedRoutes steps = true
  rootCoverage : rootCovered steps = true

private theorem append_checked (policy : Policy) (rest : List Step)
    (built : List Step) (hp : Closed policy built)
    (h : checkFrom policy built.length rest = true) :
    Closed policy (built ++ rest) := by
  induction rest generalizing built with
  | nil => simpa using hp
  | cons step rest ih =>
      have split := Bool.and_eq_true_iff.mp h
      have hs : StepValid policy built.length step := of_decide_eq_true split.1
      have hp' := Closed.snoc hp hs
      have hr : checkFrom policy (built ++ [step]).length rest = true := by
        simpa using split.2
      have result := ih (built ++ [step]) hp' hr
      simpa [List.append_assoc] using result

/-- Main soundness result: acceptance constructs a finite closure derivation. -/
theorem check_sound (policy : Policy) (steps : List Step)
    (h : check policy steps = true) : VerifiedPlan policy steps := by
  have split := Bool.and_eq_true_iff.mp h
  have earlier := Bool.and_eq_true_iff.mp split.1
  have result := append_checked policy steps [] (.nil) earlier.1
  exact ⟨by simpa using result, earlier.2, split.2⟩

/-- No accepted step can use its own not-yet-produced occurrence. -/
theorem no_self_bootstrap (policy : Policy) (i : Nat) (step : Step)
    (h : StepValid policy i step) : i ∉ step.deps := by
  intro member
  exact (Nat.lt_irrefl i) (h.1 i member)

/-- Equipment expansion remains within the explicitly supplied budget. -/
theorem depth_bounded (policy : Policy) (i : Nat) (step : Step)
    (h : StepValid policy i step) : step.depth ≤ policy.equipmentDepth := h.2.2

example : check ⟨1⟩ [⟨.seed, [], 0, "printer"⟩,
    ⟨.catalog, [], 1, "motor"⟩,
    ⟨.print, [0], 1, "frame-evidence"⟩,
    ⟨.equipment, [1,2], 1, "assembly-evidence"⟩,
    ⟨.print, [0], 0, "workpiece"⟩,
    ⟨.machine, [3,4], 0, "process-evidence"⟩,
    ⟨.assemble, [5], 0, "product"⟩] = true := by decide

example : check ⟨1⟩ [⟨.equipment, [0], 1, "circular"⟩] = false := by decide

#print axioms check_sound
#print axioms no_self_bootstrap
#print axioms depth_bounded
end FluxKernel
