# <capability>

<!-- The living spec of one capability: what the system does NOW. It stays for good — deltas are
     merged into it and then deleted, so this file is the only place that answers "what does the
     system do". Nothing renders it and nothing parses it: it is read by a human, and by an agent
     that would otherwise invent requirements for behaviour that already exists.

     Size is a real boundary, not cosmetics: past roughly 300 lines the file is CUT, because the
     threshold is what keeps a merge diff small enough that a human actually reads it. Cut along what
     changes together — the part that deltas keep touching on its own becomes its own capability
     file. The mirror rule points the other way: two files that nearly every delta touches as a pair
     are one capability and get merged.

     Fill the placeholders, delete these comments. -->

## Purpose

<!-- One to three sentences: what this capability lets someone do, in their vocabulary. Not the
     technology, not the layers. -->

## Operations

<!-- What the capability offers, one line each: the operation and what is observable when it runs —
     what it returns, what state it leaves behind, what it refuses. -->

- <operation> — <observable behaviour>

## Invariants

<!-- What always holds, whatever the caller does. Every invariant carries its provenance: the test
     that pins it, or the admission that nothing automatic does. An invariant with no provenance is a
     claim, and a claim quietly rots into a lie about the system. -->

- <rule that always holds> *(verified by: <test_id>)*
- <rule nothing can pin automatically> *(MANUAL)*
