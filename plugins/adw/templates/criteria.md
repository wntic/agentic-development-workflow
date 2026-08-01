# Criteria — <NNN-slug>

<!-- The checklist for one change. Three states, and nothing else:
       [ ]  not proven yet
       [x]  proven by a marked test that ran and passed
       [m]  accepted by hand, with the reason written in the verdict
     A state moves in both directions: a criterion that was ticked and no longer holds goes back
     to [ ].
     Fill the placeholders below, delete these comments. -->

- [ ] AC-1 · <criterion-slug>: <observable behaviour of the running system>
- [ ] AC-2 · <criterion-slug>: <observable behaviour of the running system>

<!-- What the form cannot check, and a reader must:

     - A criterion is behaviour observable from outside, not a property of the code. "<request with
       a body over the limit> → 413" is a criterion; "the middleware is configured correctly" is
       not. If the line contains "correctly", "properly", "works" or "as expected" — or the same
       words in the language you are writing in — the criterion has not been written yet: the
       observable part is still missing. These four words are where an unwritten criterion hides
       most often.

     - Every criterion is pinned by at least one test carrying `@pytest.mark.ac("<criterion-slug>")`
       with its own slug — the slug, never the number. One criterion may have several marked tests;
       a marked test that passes is what lets the box become [x].

     - The slug is lowercase and hyphen-separated, and it names the observable behaviour rather than
       the implementation: `refund-exceeds-paid-amount`, not `amount-check-in-service`. It is unique
       within this change, and it carries no change number — which change a criterion came from is
       process state, and it lives in the branch and the tag. The number stays on the checklist line
       because a human referring to a criterion in conversation or in the verdict needs something
       short to point at; the marker takes the slug, because marker values are shared by the whole
       tree and a bare number there is answered by whichever change numbered it that way.

     - AT LEAST ONE criterion of the change is proven through a really running application — the
       real process against real backing services — and not only by a unit test with in-memory
       fakes. A suite of fakes can be entirely green while the assembled thing does not start.

     - A criterion that no test can physically pin (something leaves the system, money is spent, a
       human looks at a screen) goes to [m] with its reason. It never stays silently unticked.

     - One to three criteria for a small change. If a bugfix has grown sixteen, the ceremony is
       being filled in rather than the behaviour named.

     - The text of a criterion is frozen once the tests are committed. Changing the wording after
       that is a human decision, taken by returning to the spec — not an edit made in passing while
       trying to make something pass. -->
