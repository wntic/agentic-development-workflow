# S24-04 — довод правила про `422` переписывается на тот, который остаётся верным

Тип агента: **`adw-builder`**
Слой: **шипящееся** (`plugins/adw/skills/restapi-route-contracts/SKILL.md`) — warden докладывает про
версию; подъём готовит `/ship`, здесь версия не двигается.
Происхождение: решение человека 2026-08-10, `plan/findings/legacy.md`, секция «Решения человека,
2026-08-10 — десятая чистка (волна S24), проза разошлась с деревом», строка **F-252**.

**Что это за задача.** Правило «объявляй `422` на каждом роуте с валидируемым входом» **верно и
остаётся**. Ложным стало его единственное записанное основание: «the `test_openapi_advertises_error_codes`
invariant requires the decorator to match the spec **exactly**, so a route that omits `422` while
carrying a param fails with an *extra* `422` in the spec».

Замер: тот же шаблон против приложения, чьи роуты `422` не объявляют, — **до** правки `FAILED` с
`extra=[422]`, **после** `PASSED`. И волна S22 сделала расхождение прямым: Rule 4
`test-discovery-invariants` теперь называет изъятие открытым текстом — сравнение точное **кроме**
кода валидации, который фреймворк вставляет сам, шаблон держит его в `_FRAMEWORK_VALIDATION_CODE` и
вычитает. То есть соседний скилл документирует ровно то, что этот довод отрицает.

Что сломается без правки: реализатор, проверивший довод, увидит `PASSED` без `422` и снимет `422` с
декораторов — а таблица «Operation → error_responses» того же скилла разъедется с практикой.

Решение — развилка (а): довод переписывается на тот, который остаётся верным — **опубликованный
документ честнее, когда декоратор объявляет то, что фреймворк и так вставит**.

Читать сначала:

- `plugins/adw/skills/restapi-route-contracts/SKILL.md`, абзац «Advertise `422` on every route…»
  целиком и таблицу «Operation → error_responses» над ним:
  `rtk proxy grep -n -B12 -A6 'requires the decorator to match the spec' plugins/adw/skills/restapi-route-contracts/SKILL.md`;
- `plugins/adw/skills/test-discovery-invariants/SKILL.md`, Rule 4 — новая формулировка изъятия:
  `rtk proxy grep -n '^4\. \*\*OpenAPI cross-check' plugins/adw/skills/test-discovery-invariants/SKILL.md`;
  **читать, не править**;
- тело записи грепом: `rtk proxy grep -n '^## F-252 ' plan/findings/legacy.md`, затем ~23 строки;
- строку решения по F-252 в секции решений 2026-08-10 (десятая чистка) в конце того же файла.

## Задача

1. Заменить обоснование: не «инвариант покраснеет», а — опубликованный документ честнее, когда
   декоратор объявляет то, что FastAPI и так вставит; читатель схемы видит одно и то же независимо от
   того, смотрит он на код или на документ.
2. Заодно снять из абзаца утверждение, что инвариант требует точного совпадения: оно неверно и
   **противоречит** тому, что теперь написано у соседа. Если удобнее — сказать прямо, что инвариант
   этот код изымает, поэтому красным он не будет; тогда читатель не станет искать несуществующего
   провала.
3. Всё остальное в абзаце сохранить: перечень входов (path param, query, filter, pagination, body),
   пример «Read-by-id и Delete несут `422` из-за `{id}`», исключение «parameterless, body-less route»
   и ловушку «`422` — это *any-input*, а не body validation». Таблицу выше не трогать.
4. Ничего больше.

Файл шипится — текст английский, в тоне файла.

## Deliverables

Правка в одном файле `plugins/adw/skills/restapi-route-contracts/SKILL.md`. Больше ничего.

## Границы

- `plugins/adw/skills/test-discovery-invariants/SKILL.md` — **не трогать**, только читать.
- Остальные файлы `plugins/adw/**`, `plan/**` (кроме чтения), `.claude/**` — не трогать.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- **Правило не ослабляется**: `422` по-прежнему объявляется на каждом роуте с валидируемым входом.
- Никакого механизма. Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
rtk proxy grep -c 'requires the decorator to match the spec' plugins/adw/skills/restapi-route-contracts/SKILL.md
# до: 1. После: 0 — опровергнутый довод снят
rtk proxy grep -ci 'honest\|honestly' plugins/adw/skills/restapi-route-contracts/SKILL.md
# до: 0. После: ≥1 — новый довод на месте
rtk proxy grep -c 'Advertise `422` on every route carrying ANY validated input' plugins/adw/skills/restapi-route-contracts/SKILL.md
# до: 1. После: 1 — само правило не тронуто
rtk proxy grep -c 'any-input' plugins/adw/skills/restapi-route-contracts/SKILL.md
# до: 1. После: 1 — ловушка сохранена
git status --porcelain -- plugins/adw/skills/test-discovery-invariants/
# до: пусто. После: пусто — соседний скилл не тронут
git diff --stat -- plugins/adw/
# до: пусто. После: ровно один файл
claude plugin validate plugins/adw 2>&1 | tail -1
# до: ✔ Validation passed. После: то же
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- дифф — один файл; правило «объявляй `422`» не ослаблено и стоит дословно;
- опровергнутый довод снят, новый не опирается на поведение инварианта;
- перечень входов, пример с `{id}`, исключение и ловушка «any-input» сохранены;
- `test-discovery-invariants` не тронут, и текст двух файлов больше друг другу не противоречит;
- валидатор зелёный; версия `plugins/adw` не тронута;
- механизма нет.
