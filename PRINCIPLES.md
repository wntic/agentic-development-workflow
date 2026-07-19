# Design principles — the decision checklist

The cross-cutting rules that decide *how this workflow is built and extended*. This file is the
**single home** for those rules; it is `@`-included by `CLAUDE.md`, so it loads into every session.

How the documents divide labour — keep them in their lanes, never duplicate:

- **`workflow_v3_spec.md`** is the **why** (rationale, source of truth for v3). Every rule here cites
  it as `v3 §N`; read the section when you need the argument, not the verdict.
  (`codegen_workflow_spec.md` is the archived v2 rationale; `notes/15_v3_design_review.md` is the
  adversarial-review register behind the S8/S9 inversions.)
- **This file** is the **decision verdict** — *when X is tempting → apply this litmus → do Y*. No prose
  rationale beyond one line; that lives in the spec.
- **Skills** (`.claude/skills/`) are the **how-to-write-a-component** knowledge. House-style for a given
  artifact lives in its skill, not here.

This file follows its own canon: it does not restate the spec, it points to it. If a rule grows a
paragraph of justification, that paragraph belongs in the spec with a `§` back-reference.

Each rule: **Trigger → Litmus / do → why (`§`)**.

---

## A. The three layers never mix (the spine)

**A1 · Layer separation.** *Trigger:* deciding where a fact belongs. *Do:* sort it into exactly one of
*knowledge* (how to write an artifact → **skills**), *specification* (what to do and how to verify it →
**`specs/` Markdown**), *enforcement + orchestration* (who does what, what is forbidden, when it is
"done" → **agents/commands + `gate.py`/`accept.py` + hooks**). *Why:* most bugs are one layer leaking
into another; the enforcement layer is first of all two scripts, and only then hook ergonomics. `v3 §1`

**A2 · Spec files are canonical for intent, code for implementation, the verdict for conformance.**
*Trigger:* asking "what should the system do?", "how does it do it?", or "is it done?" *Do:* answer
each from its own canon — intent from `overview.md` + capability files + the change's `change.md`;
implementation from the code itself (Design notes are non-binding; on divergence the code wins);
conformance from `verdict.md` backed by a `gate.py --criteria` run pinned to a git SHA. Never let one
document answer another's question. *Why:* v2 kept one canonical graph the code was derived from; v3
splits canonicity by question, so no document pretends to govern a lane it cannot verify. `v3 §2, §3.1`

**A3 · Determinism lives in verification, not authoring.** *Trigger:* tempted to make some step
"correct by construction" via a code-rendering generator or a rigid spec schema. *Do:* don't — agents
write the code and the spec stays free Markdown; correctness is held by deterministic *verifiers*
(`gate.py`: toolchain type-check/lint/tests + grep-gates + construct-smoke + criteria cross-check).
And the verification verifies the integrity of its own inputs (baseline diff, test inventory,
self-hash) — v3's completion of the rule. *Why:* a render-generator has partial coverage by
construction and breaks on the unforeseen app; verification catches drift even inside an
already-written body. `v3 §0, §5`

**A4 · The gate must exercise the real failure mode.** *Trigger:* relying on the toolchain to catch a
class of defect. *Litmus:* does the gate actually *construct / run* the artifact, or only type-check and
lint it? A defect that surfaces only at construct/run time (a missing framework dependency FastAPI
imports at `create_app()`, broken middleware wiring, an unbuildable route schema) passes green until
something exercises it — add that exercise (the app-construction smoke test). Corollary: no silent
no-op — an under-specified body fails loud, it does not pass quietly. *Why:* mypy, ruff, and the unit
tests all stayed green while `create_app()` raised. `v3 §0, §3.1, §5.1`

---

## S. The spec, the criteria, the gates (replaces the v2 B-series)

Copied **verbatim** from `workflow_v3_spec.md §11` (the spec is Russian; the wording survived a
5-probe adversarial review and is kept word-for-word — do not paraphrase it here).

**S1 · Спека описывает поведение, не устройство.** *Trigger:* тянет записать в спеку имя
класса, путь, тип колонки. *Litmus:* это проверяемо снаружи работающей системы? Нет →
это Design notes (non-binding) или решение implementer'а. *Исключение с владельцем:*
Interface sketch — binding-контракт цикла, меняемый только протоколом §6. *Why:* устройство —
производная; но у имён, которые разделяют test-author и implementer, обязан быть один хозяин.

**S2 · Один формат, три глубины; ceremony по размеру diff'а.** *Trigger:* хочется сделать
секцию обязательной. *Litmus:* нужна ли она S-спеке из одного предложения? Нет → опциональна.
*Why:* обязательные секции — это обязательные поля v2 в новой одежде.

**S3 · Критерий — наблюдаемое поведение; чеклист append-only для агентов.** *Trigger:*
критерий формулируется про код («используется паттерн X») или агент хочет уточнить пункт.
*Do:* переформулировать через запуск системы; правка текста — только человеком; flip только
с junit-обеспечением. *Узаконенные исключения:* класс invisible (AC = «поведение не
изменилось», доказательство — gate + OpenAPI-diff) и `[m]` (принято человеком, с причиной).
*Why:* A4 + «ни один сценарий не выпадает молча» — то, ради чего жил манифест.

**S4 · Must-hold правило живёт в гейте, не в прозе.** *Trigger:* в скилл/спеку/команду
пишется «никогда не делай X» или «Y делает только Z». *Litmus:* что физически произойдёт,
когда агент всё-таки сделает X? Если ответ «ничего» — правило не существует; добавь
grep-гейт/integrity-сверку/disallowedTools или сознательно понизь до совета. *Why:* провал 2
обоих прошлых поколений; на дизайн-ревью этот литмус завалил четыре правила самого v3.

**S5 · Вердикт выносит не автор.** *Trigger:* агент, писавший код, отчитывается «критерии
выполнены». *Do:* вердикт валиден только из свежего контекста evaluator'а + `gate.py
--criteria`; сила тестов для M/L проверяется адверсариальным проходом. *Why:*
self-evaluation bias — самый задокументированный провал агентских циклов.

**S6 · Дельта вливается, спека компаундится.** *Trigger:* change принят. *Do:* критерии →
инварианты capability-файлов (с provenance-пометкой), merge — немедленно, ревьюированно;
каталог change'а удаляется — история только в git. *Why:* одноразовые спеки — главное
архитектурное сожаление Spec Kit; вторая копия истории отравляет grep.

**S7 · Capability режется по cohesion-of-change.** *Trigger:* решается, где живёт кусок
спеки, или файл растёт (включая overview.md). *Litmus:* меняется вместе с этой способностью →
в её файл; видят ≥2 capability сейчас → в overview; файл >~300 строк → резать; каждая вторая
дельта трогает одну и ту же пару файлов → слить. *Why:* локальность merge — то, что делает
LLM-вливание дельты ревьюируемым; монолитная спека контекста его убивает. `§2.1`

**S8 · Хук — эргономика; доверие — post-hoc сверка с baseline.** *Trigger:* хочется
защитить инвариант prevention-хуком и успокоиться. *Litmus:* что увидит `gate.py`, если
агент обойдёт хук через Bash/Write/conftest/правку самого гейта? Если «ничего» — инвариант
не защищён: добавь его в integrity-инвентарь §5.1 (diff защищённых деревьев, инвентарь
тестов, junit-кросс-чек, self-hash). *Why:* prevention дыряв по построению; обесценивание
результата обхода — нет. `notes/15, тема 1`

**S9 · Один change = одна ветка; main всегда зелёный.** *Trigger:* красные тесты просятся
в общее дерево, или два change'а хотят работать одновременно. *Do:* красные тесты, код и
вердикт живут на ветке change'а; main получает только зелёные merge через accept.py;
брошенный change = удалённая ветка. *Why:* закоммиченные красные тесты одного change'а
дедлочат гейт всех остальных; поток изменений нуждается в детерминизме не меньше, чем
один change. `notes/15, тема 2`

---

## C. Skills — the knowledge layer

**C1 · A skill is knowledge, not an executor.** *Trigger:* writing or editing a `SKILL.md`. *Litmus:* the
skill must not know what invokes it — no mention of agents, the change cycle, criteria files, or
"report to the coordinator". *Why:* a skill is consumed by different readers (test-author/implementer
vs the `/spec` session); coupling it to one orchestration leaks a layer. `v3 §7`

**C2 · One theme per skill.** *Trigger:* a skill is being stretched to cover an adjacent artifact or
layer. *Litmus:* a skill covers one coherent theme an agent can pick by its `description` /
`when_to_use` (post-merge granularity: `domain-model`, `restapi`, `testing-unit`, …); if its hard
stops fire, the task asked for the wrong artifact — switch to the right skill, don't stretch this one.
*Why:* narrow, non-overlapping scope is what makes auto-invocation load the right knowledge. `v3 §7`

**C3 · The human-onboarding purity test.** *Trigger:* any line in a skill. *Litmus:* would a new human
developer read this as onboarding docs? If they'd trip over it (it talks about the runner, a manifest,
what the skill returns), it's a leaked layer — cut it. *Why:* the purity test is what drove removing the
`Inputs the spec must supply` and `Report to the coordinator` sections from every skill. `v3 §7`

**C4 · Skills describe artifacts; agents describe processes.** *Trigger:* deciding whether new content is
a skill or an agent/command. *Do:* artifact-shaped → a skill in `.claude/skills/` (via
`meta-skill-author`), four-section body, no orchestration sections; process-shaped → an agent in
`.claude/agents/` or a command in `.claude/commands/`. The directories stay separate on purpose:
skills auto-invoke, commands run only on explicit human launch. *Why:* keeping the lanes apart is what
stops per-component prompt proliferation (see D1). `v3 §1, §7`

**C5 · Skill-gap is gated, never self-minted.** *Trigger:* a diff touches a layer
(`domain/`, `application/`, `infrastructure/<tech>/`, `restapi/`, `tests/`) with no matching skill
reported loaded, or a new `infrastructure/<tech>` subdirectory appears with no skill for it. *Do:*
enforced via the §7.5 coverage surrogate — an empty skill∩layer intersection is a loud warning in the
verdict; a new tech directory without a skill is a **STOP** → `meta-skill-author` drafts → **human
accepts**, then work resumes. A **coverage-gap** (skill exists but doesn't fit the case) → the agent
stops and escalates, never extends the skill silently. *Why:* a skill is canonical knowledge governing
all future generation; silent self-mint poisons the canon, breeds duplicates, and revives
per-component prompts. `v3 §7.5`

**C6 · No scope-overclaim (altitude).** *Trigger:* a skill template or rule bakes in a feature one app
happens to have — auth, a relational store, multipart, multi-tenancy / cross-org, a specific role
ladder, a `realm` / hostname / port literal. *Litmus:* is this feature universal to every app the pack
targets, or contingent on the app being built? Contingent → make the template conditional on the
feature's actual presence (the two-sub-template idiom), never freeze the source app's choice as
universal. *Why:* skills froze one source app's features as universal — the largest bug class in the
catalog (three audit rounds, 80+ findings); the knowledge layer's altitude is the language/stack, not
one application. `v3 §0, §7`

**C7 · Derivation has one home.** *Trigger:* stating a derived name, path, mapping, or toolchain
command in a skill, an agent, or the catalog index. *Litmus:* the `conventions` skill is the single
source for naming/paths/store-profiles/substrate — and toolchain commands live **in `gate.py`**,
which `conventions` cites, never restates. Every other document *cites* the home, never copies the
rule. *Why:* a restated derivation drifts out of sync; this is the no-two-sources-of-truth meta-rule
(this file's header) made enforceable. `v3 §5, §7`

---

## D. Agents and orchestration

**D1 · Few roles, differentiated by context.** *Trigger:* wanting a new agent for a new component or
task type. *Do:* don't — the roles are **spec-author** (human + main session), **test-author**,
**implementer**, **evaluator**, differentiated by context (which skills auto-load + which spec slice
is fed) and by `disallowedTools`, never by a forked per-component prompt. *Why:* proliferating
per-component personas was the chief mistake of the first prototype. `v3 §4`

**D3 · Anti-collusion on tests.** *Trigger:* authoring tests or judging done-ness. *Do:* the
test-author writes tests from the spec + Interface sketch, in a separate context and **before** the
code; the implementer cannot write `tests/**`; the verdict comes only from a **fresh-context
evaluator**; `criteria.md` owns the *list* of scenarios so none is silently dropped, and agents can
only flip its checkboxes with junit-backed proof. *Why:* test and code written from one understanding
would be equally wrong about intent; self-evaluation bias is the most documented failure of agent
loops. `v3 §3.3, §4`

**D4 · File ownership runs tests vs src.** *Trigger:* a cycle step touches files. *Litmus:*
`tests/**` belongs to the test-author (including deleting obsolete tests in a removal-class change);
`src/**` belongs to the implementer (including the Alembic revision); `verdict.md` + criteria flips
belong to the evaluator; canonical spec files are written only by `accept.py` and the `/spec` session.
The boundary is enforced (`disallowedTools` + gate integrity), not conventional. *Why:* v2's
declarative-vs-body line died with the scaffolder; the tests-vs-src line is what makes collusion and
self-grading structurally impossible. `v3 §4`

---

## E. Domain modeling (house style that shapes spec review)

These few target-app rules live here because they shape review of a change and its Interface sketch;
the full how-to is in the skills.

**E1 · Value object vs primitive vs entity `__post_init__`.** *Trigger:* deciding how to model a value.
*Litmus:* wrap it in a **value object** only when it carries its own invariant, behavior, or shared/
type-significant meaning (`Email`, `Money`) — *not* mechanically for every primitive (`description: str`
stays primitive). A **single-value** invariant may be a VO *or* an entity `__post_init__` check; a
**cross-field / whole-entity** invariant ("if X then Y") can *only* be an entity `__post_init__`. *Why:*
blanket "VO everywhere" is primitive-obsession inverted — ceremony plus `str ↔ VO` conversion at every
boundary. *(See the domain skills.)*

**E2 · Audit timestamps are not domain fields.** *Trigger:* an entity wants `created_at` / `updated_at`.
*Do:* don't put them on the entity — they're a DB-managed table convention (reserved column names,
never entity fields); a read that must display/filter them returns a **read-model DTO** projected from
the row. *Why:* write model = entity, read model = whatever the API needs.

**E3 · Polyglot storage; the table is written once.** *Trigger:* persistence shows up. *Do:* one app
may target several stores at once (store profiles live in the `conventions` skill); the relational
`Table` is written once (column types are the implementer's judgment) and **migrations are
Alembic-native, owned by the implementer** — the Docker tier runs `alembic upgrade head`. *(Full rules
in the persistence skills.)* `v3 §5.1, §9`

---

## F. Mode

**F1 · Brownfield is the primary mode.** *Trigger:* designing any workflow mechanism. *Do:* build it
for **deltas** — a change is a delta applied to the living spec of an existing system; greenfield is
the degenerate case: the first change of an empty context (skeleton `overview.md`), shaped as a
vertical slice with one end-to-end observable AC. *Why:* designing greenfield-first is exactly how the
old generator's glue broke (it added/overwrote but never removed orphans). `v3 §2, §9`
