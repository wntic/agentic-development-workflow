# Criteria — <context>/NNN-<slug>

<!-- The machine-checkable inventory of acceptance criteria (spec §3.3): agents may flip
     states here, never rephrase or delete an item. One line per criterion, flat list:

       - [ ] AC-n: <observable behaviour — name an HTTP code, a response field, or a
                    state assertion about the system after a run>

     States:
       [ ]  not proven
       [x]  machine-proven — flipped ONLY by the evaluator, in both directions; every [x]
            must be backed by a PASSED test marked @pytest.mark.ac("AC-n") in the junit
            report of the current gate.py run
       [m]  accepted manually — set ONLY by the human, for criteria neither a test nor a
            live run can cover; the reason is recorded in verdict.md

     Item text is immutable once the red-test baseline is committed; adding or changing an
     item is a human /spec action that resets the cycle. Vague wording does not enter work:
     .claude/tools/criteria_lint.py rejects vagueness markers and items that name no
     observable artifact. -->

- [ ] AC-1: <...>
- [ ] AC-2: <...>
