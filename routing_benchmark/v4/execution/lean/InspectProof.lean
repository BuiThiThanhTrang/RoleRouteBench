import Lean

open Lean Lean.Elab

/- This trusted observer elaborates the exact submitted file. It neither inserts
   tactics nor creates proof/compilation certificates for the benchmark. -/

def positionJson (ctx : ContextInfo) (stx : Syntax) : Json :=
  let start := ctx.fileMap.toPosition (stx.getPos?.getD 0)
  let stop := ctx.fileMap.toPosition (stx.getTailPos?.getD (stx.getPos?.getD 0))
  Json.mkObj [("line", toJson start.line), ("column", toJson (start.column + 1)),
              ("end_line", toJson stop.line), ("end_column", toJson (stop.column + 1))]

partial def observeTree (tree : InfoTree) (outer : Option ContextInfo)
    (tactics terms : IO.Ref (Array Json)) : IO Unit := do
  match tree with
  | .hole _ => pure ()
  | .context part child => observeTree child (part.mergeIntoOuter? outer) tactics terms
  | .node info children =>
    if let some ctx := outer then
      match info with
      | .ofTacticInfo t =>
        if (← tactics.get).size < 512 then
          try
            let before ← ({ ctx with mctx := t.mctxBefore } : ContextInfo).ppGoals t.goalsBefore
            let after ← ({ ctx with mctx := t.mctxAfter } : ContextInfo).ppGoals t.goalsAfter
            tactics.modify (·.push (Json.mkObj [
              ("position", positionJson ctx t.stx),
              ("tactic_kind", toJson t.stx.getKind.toString),
              ("goals_before", toJson before.pretty), ("goals_after", toJson after.pretty),
              ("goal_count_before", toJson t.goalsBefore.length),
              ("goal_count_after", toJson t.goalsAfter.length)]))
          catch _ => pure ()
      | .ofTermInfo t =>
        if (← terms.get).size < 1024 then
          try
            let (actual, expected) ← t.runMetaM ctx do
              let actual ← Meta.ppExpr (← Meta.inferType t.expr)
              let expected ← t.expectedType?.mapM fun e => do
                pure (← Meta.ppExpr e).pretty
              pure (actual.pretty, expected.getD "")
            terms.modify (·.push (Json.mkObj [
              ("position", positionJson ctx t.stx),
              ("actual_type", toJson actual), ("expected_type", toJson expected)]))
          catch _ => pure ()
      | _ => pure ()
      for child in children do
        observeTree child (info.updateContext? outer) tactics terms

unsafe def main (args : List String) : IO UInt32 := do
  let some file := args.head? | throw (IO.userError "Expected a public Lean source path")
  initSearchPath (← findSysroot)
  -- A standalone frontend must execute imported Mathlib initializers, just as
  -- the standard Lean driver does. This is trusted observer setup, not a tactic.
  enableInitializersExecution
  let input ← IO.FS.readFile file
  let ictx := Parser.mkInputContext input file
  let opts := ({} : Options).setBool `Elab.async false
  let (header, parserState, messages) ← Parser.parseHeader ictx
  let (env, messages) ← processHeader (leakEnv := true) header opts messages ictx
  let initial := { (Command.mkState env messages opts) with infoState.enabled := true }
  let finished ← Lean.Elab.IO.processCommands ictx parserState initial
  let tactics ← IO.mkRef (#[] : Array Json)
  let terms ← IO.mkRef (#[] : Array Json)
  for tree in finished.commandState.infoState.trees.toArray do
    observeTree tree none tactics terms
  let mut diagnostics := #[]
  for message in finished.commandState.messages.toList do
    diagnostics := diagnostics.push (Json.mkObj [
      ("severity", toJson (match message.severity with
        | .error => "error" | .warning => "warning" | .information => "information")),
      ("line", toJson message.pos.line), ("column", toJson (message.pos.column + 1)),
      ("message", toJson (← message.data.toString))])
  let payload := Json.mkObj [
    ("has_errors", toJson finished.commandState.messages.hasErrors),
    ("diagnostics", toJson diagnostics), ("tactic_states", toJson (← tactics.get)),
    ("term_types", toJson (← terms.get)),
    ("tactics_capped", toJson ((← tactics.get).size == 512)),
    ("terms_capped", toJson ((← terms.get).size == 1024))]
  IO.println ("FORMAL_INSPECTION_JSON:" ++ payload.compress)
  return 0
