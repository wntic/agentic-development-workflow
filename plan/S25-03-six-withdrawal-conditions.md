# S25-03 — шесть механизмов прохода S10 получают условие снятия

Тип агента: **`adw-builder`**
Слой: **шипящееся** (пять файлов) — warden докладывает про версию; подъём готовит `/ship`.
Происхождение: решение человека 2026-08-10, `plan/findings/legacy.md`, секция «Решения человека,
2026-08-10 — одиннадцатая чистка (волна S25), последние девять записей F-серии», строка **F-259**.

**Что это за задача.** Красная линия 5: каждый компонент харнеса — гипотеза об ограничении модели, и
он несёт дату ревизии, чтобы компенсация исчезнувшего ограничения не носилась бессрочно. Проход S10
добавил шесть обязанностей и не дал условия снятия ни одной; при этом **в том же проходе** стандарт
применялся — два прозаических правила получили условие снятия в собственном диффе. То есть он был и
применён к дешёвому, а к дорогому нет.

Условий снятия в дереве сегодня два (перемерено):
`plugins/adw/skills/python-style/SKILL.md`, `plugins/adw/skills/application/SKILL.md`.

**Форма уже задана деревом** — вот она, дословно, из `python-style`:

> *This allowance rests on banners having held so far, not on a test of failure, so it carries its
> withdrawal condition next to it: if a banner is ever found lying or silently out of date, the
> allowance goes and `tests/` falls under the `src/` form.*

То есть: **на чём стоит → что его снимет**, курсивом, рядом с самим правилом. Новые шесть пишутся в
этой форме.

Шесть адресатов, найдены грепом на день подготовки задачи (номера строк — удобство, предмет
опознаётся по цитате):

| # | механизм | файл | якорь |
|---|---|---|---|
| 1 | мутация с откатом | `agents/evaluator.md` | «A mutation with a revert is not fixing code» (~:98) |
| 2 | субстрат на диспатче скелета | `agents/implementer.md` | раздел про `Makefile`/субстрат (~:133) |
| 3 | `BLOCKED` вместо укладки субстрата | `agents/test-author.md` | «Report it as `BLOCKED`» (~:54) |
| 4 | кросс-сквозной ярус в красной фазе | `agents/test-author.md` | «the red phase carries the cross-cutting tests» (~:90) |
| 5 | форма замеренного разрыва | `commands/accept.md` | «gap measured at change» (~:65) |
| 6 | `uv run alembic check` | `skills/infra-persistence/SKILL.md` | «runs `uv run alembic check` itself» (~:460) |

Читать сначала:

- **обе существующие формы** — `rtk proxy grep -n -B2 -A3 'withdrawal condition' plugins/adw/skills/python-style/SKILL.md plugins/adw/skills/application/SKILL.md`
  — это канон формы, и новые шесть ей следуют;
- каждый из шести адресатов с окружением — довод механизма нужен, чтобы назвать, **на чём он стоит**;
- тело записи грепом: `rtk proxy grep -n '^## F-259 ' plan/findings/legacy.md`, затем ~14 строк;
- строку решения по F-259 в секции решений 2026-08-10 (одиннадцатая чистка) в конце того же файла;
- `WORKFLOW.md` §9, красная линия 5 — формулировка обязанности.

## Задача

1. Каждому из шести механизмов дописать условие снятия в форме дерева: **что он компенсирует** и
   **какой признак его снимет**. Признак должен быть наблюдаемым — прогон, вердикт, замер, — а не
   «когда станет не нужно».
2. Условие ставится **рядом с самим механизмом**, а не отдельным разделом и не списком в конце файла.
3. Дата ревизии — по образцу дерева: если существующие формы дату не несут, а несут признак, новые
   несут признак. Смотри обе существующие и следуй им, а не этому файлу.
4. Ничего больше: сами механизмы не переформулируются и не ослабляются — условие снятия описывает,
   когда правило уйдёт, а не разрешает его не исполнять.

Файлы шипятся — текст английский, в тоне соседей.

## Deliverables

Правки в пяти файлах: `plugins/adw/agents/evaluator.md`, `plugins/adw/agents/implementer.md`,
`plugins/adw/agents/test-author.md` (два места), `plugins/adw/commands/accept.md`,
`plugins/adw/skills/infra-persistence/SKILL.md`. Больше ничего.

## Границы

- Остальные файлы `plugins/adw/**`, `plan/**` (кроме чтения), `.claude/**` — не трогать.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- Существующие два условия снятия (`python-style`, `application`) — **не трогать**, только читать как
  образец формы.
- Ни один механизм не ослабляется. Условие снятия — не оговорка «можно не делать».
- Никакого механизма **нового**: шесть условий — проза рядом с существующими правилами.
- Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
rtk proxy grep -rc 'withdrawal condition' plugins/adw/ | rtk proxy grep -v ':0'
# до: две строки — python-style:1, application:1.
# После: семь строк — те же две плюс evaluator, implementer, test-author (2), accept,
# infra-persistence; у test-author счёт 2.
rtk proxy grep -c 'A mutation with a revert is not fixing code' plugins/adw/agents/evaluator.md
rtk proxy grep -c 'Report it as `BLOCKED`' plugins/adw/agents/test-author.md
rtk proxy grep -c 'gap measured at change' plugins/adw/commands/accept.md
rtk proxy grep -c 'runs `uv run alembic check` itself' plugins/adw/skills/infra-persistence/SKILL.md
# до: 1, 1, 2, 1. После: те же — ни один механизм не переформулирован
git status --porcelain -- plugins/adw/skills/python-style/ plugins/adw/skills/application/ plugins/adw/.claude-plugin/
# до: пусто. После: пусто — образцы формы и версия не тронуты
git diff --stat -- plugins/adw/
# до: пусто. После: ровно пять файлов
claude plugin validate plugins/adw 2>&1 | tail -1
# до: ✔ Validation passed. После: то же
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- дифф — ровно пять файлов, шесть условий снятия (в `test-author.md` два);
- каждое стоит рядом со своим механизмом и следует форме двух существующих, а не заводит новую;
- каждое называет **наблюдаемый признак** снятия, а не «когда станет не нужно»;
- ни один механизм не ослаблен: якорные формулировки на месте, счёт совпадает с «до»;
- образцы формы (`python-style`, `application`) не тронуты;
- валидатор зелёный; версия `plugins/adw` не тронута; нового механизма нет.
