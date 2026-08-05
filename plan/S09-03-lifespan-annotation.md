# S09-03 — аннотация под `@asynccontextmanager` становится `AsyncGenerator`

Тип агента: **`adw-builder`**
Слой: **ядро** (`plugins/adw/skills/restapi-app/SKILL.md` — единственный файл)
Происхождение: решение человека 2026-08-05, `plan/FINDINGS.md`, секция «Решения человека, 2026-08-05 —
три замечания по коду второй пробы», строка **F-169**.

Читать сначала:
- в `plan/FINDINGS.md` — тело **F-169** заголовочным грепом;
- `plugins/adw/skills/restapi-app/SKILL.md`, шаблон `restapi/main.py` — строки ~41 (импорт) и ~53–54
  (декоратор и сигнатура `_lifespan`);
- `plugins/adw/skills/python-style/SKILL.md`, таблица форм импорта (~строка 133) — там стоит правило
  «`collections.abc.AsyncIterator`, не `typing.AsyncIterator`», и оно объясняет, откуда берётся
  `AsyncGenerator`.

Основание замерено:

```bash
cd ~/Projects/adw-rooms
uv run mypy --enable-error-code deprecated src/rooms/restapi/main.py   # Success: no issues found
uvx pyright   # (reportDeprecated=error) The function "asynccontextmanager" is deprecated:
#   Annotating the return type as `-> AsyncIterator[Foo]` with `@asynccontextmanager` is deprecated.
#   Use `-> AsyncGenerator[Foo]` instead.
```

Расхождение объяснено: `@deprecated`-перегрузка есть в typeshed у pyright и ещё нет во вендоренной
копии у mypy 2.3.0. Сигнал существует только в редакторе, гейт зелёный — и покраснеет разом, когда mypy
подтянет typeshed.

Форма замерена отдельно, потому что она неочевидна на 3.12:

```python
# оба варианта: mypy --strict → Success; pyright с reportDeprecated=error → 0 ошибок
async def one() -> AsyncGenerator[None]: ...
async def two() -> AsyncGenerator[None, None]: ...
```

Однопараметрическая форма исполняется в рантайме на 3.12.13 — проверено `eval`. Это не формальность:
`python-style` запрещает `from __future__ import annotations`, поэтому аннотация вычисляется.

## Задача

Две строки в шаблоне `restapi/main.py`:

- строка ~41: `from collections.abc import AsyncIterator` → `from collections.abc import AsyncGenerator`;
- строка ~54: `async def _lifespan(app: FastAPI) -> AsyncIterator[None]:` →
  `... -> AsyncGenerator[None]:`.

Берётся однопараметрическая форма — ровно та, которую называет диагностика.

## Границы

- **Только `restapi-app/SKILL.md`.** Прочие файлы каталога — другие задачи (S09-01, S09-02, S09-04),
  проба — S09-05.
- **Фикстуры pytest не трогать нигде.** Устаревание висит на `@asynccontextmanager`, а под фикстурой
  его нет. Три правила про `-> AsyncIterator[T]` у фикстур — `conventions:307`,
  `testing-contract:340`, `testing-integration-setup:452` — **верны как написаны**, и шаблоны фикстур
  в `testing-integration-setup` и `testing-contract` тоже. Тронешь — это выход за Deliverables.
- **Таблицу форм импорта в `python-style` не трогать** — она читается ради понимания, а не правится:
  `AsyncGenerator` берётся из `collections.abc` по тому же правилу, что и `AsyncIterator`, и строка
  про это уже есть.
- **Тело `_lifespan` не трогать** — комментарий про teardown и то, что контейнер достаётся из
  `app.state`, к правке отношения не имеют.
- Не чинить найденное по дороге.

## Deliverables

Один файл, две изменённые строки.

## Проверка

```bash
git diff --stat -- plugins/adw/skills/                     # ровно один файл, две строки
rtk proxy grep -n 'AsyncIterator\|AsyncGenerator' plugins/adw/skills/restapi-app/SKILL.md
# AsyncIterator в этом файле не остаётся ни разу; AsyncGenerator — импорт и сигнатура
rtk proxy grep -rn 'asynccontextmanager' plugins/adw/
# два вхождения, оба в restapi-app: импорт и декоратор — их количество не изменилось
rtk proxy grep -cn 'AsyncIterator' plugins/adw/skills/testing-integration-setup/SKILL.md
rtk proxy grep -cn 'AsyncIterator' plugins/adw/skills/testing-contract/SKILL.md
# оба числа не изменились: фикстуры не тронуты (было 6 и 3 — пересчитай на своём дереве до правки)
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json'   # пусто
```

## Что скажет warden

- **основание измерено** — расхождение mypy/pyright показано командами, а не пересказано;
- **механизмов ноль** — две строки шаблона;
- **правка узкая по замеру, а не по осторожности**: фикстуры не задеты, потому что декоратора под ними
  нет, и три правила о них остались как были;
- **форма проверена в рантайме** — важно, потому что `from __future__ import annotations` запрещён.
