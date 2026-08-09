# S14-01 — снос исполненных файлов задач и два указателя

Тип агента: **`adw-builder`**
Слой: **дев-запись**
Происхождение: решение человека 2026-08-09, `plan/INDEX.md`, секция «Чистка исполненных артефактов —
S14» (реестрного журнала больше нет — решение волны живёт в её секции INDEX).

**Что это за задача и чего она не делает.** Все задачи волн B, R и S04…S13 исполнены и отмечены;
их файлы — журнал, а модель дома — дельта: исполнено → удалено, история в git. Задача удаляет
исполненные файлы и правит **два** указателя в живых доках. Она не трогает `INDEX.md` (его режет
главная сессия), не трогает записи-замеры (`PLATFORM.md`, `INSTALL-REHEARSAL.md`, `PROBE2-PROMPTS.md`
— их ссылки на удалённые файлы исторические и не переписываются) и не удаляет файлы волны S14.

Читать сначала:

- секция «Чистка исполненных артефактов — S14» в `plan/INDEX.md`;
- `CLAUDE.md`, абзац со ссылкой на `plan/R00-skills-restructuring.md`;
- `plan/ORIENT.md:144` — счётная строка по `plan/S10-*.md`.

## Задача

**1. Удалить 80 файлов** (число проверь счётом перед удалением):

```bash
/bin/ls plan/ | rtk proxy grep -c '^[BFS].*\.md\|^R00'   # должно дать 80, из них один — S14-01 (не трогать)
```

Удаляются: `plan/B0*.md`, `plan/F*.md`, `plan/R00-skills-restructuring.md`, `plan/S04-*.md` …
`plan/S13-*.md` (включая `S04-TRIAGE.md`). **`plan/S14-01-artifact-cleanup.md` — не удалять**: файл
активной волны, его удалит закрывающий коммит главной сессии.

**2. `CLAUDE.md`**: ссылка `[plan/R00-skills-restructuring.md](plan/R00-skills-restructuring.md)` →
форма git-истории (`git log --oneline -- plan/R00-skills-restructuring.md`, затем
`git show <sha>:plan/R00-skills-restructuring.md`) — тем же приёмом, что уже сделано там для
`HISTORY.md` и реестра. Предложение вокруг не перестраивать.

**3. `plan/ORIENT.md:144`**: счётная строка `rtk proxy grep -h '^#.*правило F-136' plan/S10-*.md |
wc -l` после сноса вернёт ноль на живом правиле. Пометь её исторической: замер прогнан 2026-08-05,
файлы волны с тех пор удалены по модели дельт (S14), команда воспроизводима из git-истории. Само
правило F-136 не трогать.

## Deliverables

79 удалённых файлов под `plan/`, правка одного места в `CLAUDE.md`, правка одной строки в
`plan/ORIENT.md`. Больше ничего.

## Границы

- `plan/INDEX.md`, `plan/findings/`, `plan/PLATFORM.md`, `plan/INSTALL-REHEARSAL.md`,
  `plan/PROBE2-PROMPTS.md`, `plan/ORCHESTRATE.md` (кроме ничего — он не в списке правок) — не трогать.
- `plan/S14-01-artifact-cleanup.md` не удалять.
- `plugins/`, `.claude/` — не трогать.
- Не чинить найденное по дороге: находка — в отчёт, пишет её главная сессия.

## Проверка

Прогнана на нетронутом дереве до отправки задачи; ответ «до» назван у каждой строки.

```bash
/bin/ls plan/
# до: 84 записи (80 задачных + INDEX, ORIENT, ORCHESTRATE, PLATFORM, INSTALL-REHEARSAL,
#     PROBE2-PROMPTS, findings). После: ровно 8 записей — INDEX.md, ORIENT.md, ORCHESTRATE.md,
#     PLATFORM.md, INSTALL-REHEARSAL.md, PROBE2-PROMPTS.md, S14-01-artifact-cleanup.md, findings
rtk proxy grep -c 'R00-skills-restructuring' CLAUDE.md
# до: 2 (ссылка и путь в ней). После: ≥1 — упоминание осталось, но формой git-истории, без живой ссылки
rtk proxy grep -n 'plan/S10-\*\.md' plan/ORIENT.md
# до: строка 144. После: строка есть и несёт пометку историчности (2026-08-05, S14)
git status --porcelain -- plugins/ .claude/ plan/findings/
# до: пусто. После: пусто
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- удалены ровно исполненные файлы: ни `findings/`, ни записи-замеры, ни файлы S14 не тронуты;
- обе правки — перестановка указателя в git-историю, ни одно правило не переформулировано;
- записи-замеры не «подчищены» заодно — их исторические ссылки на удалённые файлы целы;
- дифф задачи не выходит за `plan/` + одно место `CLAUDE.md`.
