---
description: Interview over open findings in plan/FINDINGS.md — present each entry, 2–4 options with their costs, a recommendation; only the human chooses. Decisions go into the register before the first task file; execution follows the chain protocol.
argument-hint: "[F-NNN F-MMM … | empty — all open]"
---

# /interview — walking the open findings with the human

You are the main session of this repository. Your work here is to present, weigh and record;
**the human always chooses**. At no fork does this command decide on its own: a recommendation is
an argument, not an action. The standing prompt of this interview used to be typed from memory
every time; the class of silently diverging copies is measured (F-132, F-71) — this file is now
its home, and it has no second copy.

## Steps

1. **The set of entries.** From `$ARGUMENTS` — a list of `F-NNN` numbers. With no arguments — all
   open entries: they come from the counting command in `plan/ORIENT.md` §5 («Чего не читать»),
   **copied from there at run time**. There is deliberately no standing copy of that command here —
   a copy in a standing file diverges silently (F-132). Show the resulting list to the human and
   ask which batch to take this round; the batch size is theirs to set.

2. **One entry at a time, pointwise.** Find the header by grepping `^## F-NNN`, read **only that
   body** — the register is never read whole (`ORIENT` §5). Present to the human:
   - the substance in two or three sentences, the class (`ИЗМЕРЕНО` / `ПРЕДСТАВИМО`) and what
     breaks;
   - **2–4 options, each with its cost**: an edit and its size, "did not happen" with the signal
     that would reopen it, a measurement, a mechanism;
   - a recommendation with its argument.

   Name the canonical preference aloud with every recommendation, in the canon's own words
   (`CLAUDE.md`, the two habits): "the outcome to prefer is a finding that closes **without a
   guard of its own**" — removing the cause beats posting a sentry. "Did not happen" is a
   legitimate fork when named together with the signal that reopens it. A mechanism comes only
   under `ИЗМЕРЕНО` and only by the human's decision; `ПРЕДСТАВИМО` grants no right to a mechanism.

   Ask via `AskUserQuestion` when it is available; an answer of the human's own, outside the
   offered list, is always legitimate — and it is what gets recorded, not the nearest of yours.

3. **Decisions go into the register before the first task file** (F-113: a task that cites a
   decision absent from the register leaves the executor nothing to open but the task itself).
   A dated section «Решения человека, <дата> — <тема>» at the end of `plan/FINDINGS.md`, one
   disposition line per entry; the line form and the rule that no number is written without its
   command live in the register's header and are not restated here. The decisions commit is
   **its own, before any tasks**.

4. **Execution.** Turning decisions into task files and the chain of dispatches follows the
   «Протокол цепочки» section of `plan/INDEX.md`; it is not restated, it is executed. Name the
   red-line-3 score **before execution starts** — by the command from that same section, not from
   memory.

5. **Stopping is a normal outcome.** An entry that needs a measurement goes to a prober task by
   the human's decision, not into the interview's guess. A batch may also end without a single
   edit — fifteen entries of one pass closed exactly that way.

## Boundaries

- The command never chooses for the human — not one fork resolved without their answer.
- Entry bodies are read pointwise; `plan/FINDINGS.md` is never read whole.
- Earlier disposition forms in the register are never rewritten retroactively — their closedness
  is what holds the waterline.
- The open-entries counting command is not copied here — its home is `plan/ORIENT.md` §5.
