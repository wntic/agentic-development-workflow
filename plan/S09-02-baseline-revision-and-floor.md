# S09-02 — baseline-ревизия становится снимком, а не зеркалом; `testcontainers` получает флор

Тип агента: **`adw-builder`**
Слой: **ядро** (`plugins/adw/skills/conventions/SKILL.md` — единственный файл)
Происхождение: решения человека 2026-08-05, `plan/FINDINGS.md`, секция «Решения человека, 2026-08-05 —
три замечания по коду второй пробы», строки **F-168** и **F-167** (хвост про флор).

Читать сначала:
- в `plan/FINDINGS.md` — тела **F-168** и **F-167** заголовочным грепом;
- `plugins/adw/skills/conventions/SKILL.md`, раздел про Alembic-бутстрап, строки ~223–255 — шаблон
  `migrations/versions/0001_initial.py` и абзац после него;
- тот же файл, раздел **D. Stack substrate**, строки ~257–298 — список dev-зависимостей и правило
  «Floors on an SDK — the lone, disciplined exception» с его примерами;
- **`~/Projects/adw-rooms/migrations/versions/0001_initial.py` целиком** — это образец правильной формы,
  написанный имплементером второй пробы, и переписывать его заново не нужно: он читается и переносится.

## Задача

**1. F-168 — шаблон baseline-ревизии перестаёт вызывать `metadata.create_all`.**

Сегодня `conventions:242–247` даёт `upgrade()` как `metadata.create_all(op.get_bind())` и
`downgrade()` как `metadata.drop_all(op.get_bind())`, а строка 250 называет результат «a derived
snapshot of the tables **as they stand**». Снимком он не является: `metadata` импортирована живой,
и `create_all` читает её **в момент прогона ревизии**, а не в момент её написания. После второго
изменения проекта реплей цепочки с нуля построит таблицу такой, какой она стала, — и следующая
автогенерированная ревизия попытается добавить то, что уже создано.

Новая форма — **колонки, типы и констрейнты выписаны в самой ревизии**:

- `upgrade()` — `op.create_table("<table>", sa.Column(...), …, sa.PrimaryKeyConstraint(...), sa.CheckConstraint(...))`;
- `downgrade()` — `op.drop_table("<table>")`;
- импорт-регистратор `import myapp.infrastructure.postgres.tables  # noqa: F401` **уходит**: ревизия
  больше ничего не берёт из общей metadata, и импорт становится ложным следом. Импорт
  `from myapp.infrastructure.postgres.metadata import metadata` уходит по той же причине.

Причина живёт **в докстринге самой ревизии**, а не только в прозе скилла: шаблон обязан нести её, иначе
следующий имплементер вернёт `create_all` как более короткую форму. Формулировка — та, что уже написана
в пробе (`adw-rooms/migrations/versions/0001_initial.py:1–7`), и её можно взять почти дословно.

Из образца пробы переносится и **вторая вещь, которую шаблон сегодня не говорит**: у `CheckConstraint`
имя — это **суффикс**, потому что `env.py` отдаёт Alembic общую metadata с naming convention, которая
сама допишет `ck_<table>_`. Полное имя в шаблоне даёт его дважды. Это замерено пробой, и строка-комментарий
про это стоит в образце.

Прозу после шаблона (сегодня строки ~250–255) привести в соответствие: «derived snapshot … as they
stand» — ровно то утверждение, которое правка опровергает. Что остаётся верным и должно уцелеть:
baseline **write-once** (создаётся только когда в `migrations/versions/` нет ни одного `*.py`);
каждая последующая миграция — настоящая ревизия через `alembic revision --autogenerate`; `migrations/`
лежит вне линт- и тайпчек-поверхности, а проверяется прогоном `alembic upgrade head` в интеграционном
ярусе.

**2. F-167, хвост — `testcontainers` получает флор `>=4.15`.**

Замерено бисекцией, что `testcontainers.community` появился ровно в 4.15.0: на 4.14.0, 4.13.0 и 4.12.0
импорт даёт `ModuleNotFoundError: No module named 'testcontainers.community'`. Это «известная ломающая
граница» в смысле правила §D, и форма у флора та же, что у примера `redis>=4.2`: минорная точность,
причина рядом. В списке **Dev** строка `testcontainers` становится `testcontainers>=4.15` с причиной —
пространство имён `community` появилось там, а плоское устарело.

Правило §D переписывать **не надо**: оно уже разрешает ровно этот случай. Появляется один пример его
применения, а не новая оговорка.

## Deliverables

Один файл — `plugins/adw/skills/conventions/SKILL.md`. Три места: шаблон baseline-ревизии, абзац после
него, строка `testcontainers` в списке Dev.

## Границы

- **Только `conventions/SKILL.md`.** Импорты в двух тестовых скиллах — задача S09-01,
  `restapi-app` — S09-03, `test-principles` — S09-04, проба — S09-05. Не заходи ни в один.
- **`conventions:328` не трогать** — `testcontainers.*` там глоб `[tool.mypy] module`, он покрывает
  `community` без правки.
- **`migrations/env.py` и `script.py.mako` не трогать** — они верны, правка про содержимое ревизии.
- **Никакой новой оговорки в правило про флоры.** Оно уже разрешает этот случай; появляется
  применение, а не исключение.
- **Имя приложения в шаблоне — `myapp`**, как во всём файле. Не подставляй `rooms`: образец пробы
  читается ради формы, а не ради имён.
- **Потолок фронтматтера** `description` + `when_to_use` — 1536 символов. Трогать его незачем.
- Не чинить найденное по дороге.

## Проверка

```bash
git diff --stat -- plugins/adw/skills/                             # ровно один файл
rtk proxy grep -rn 'create_all\|drop_all' plugins/adw/             # пусто
rtk proxy grep -n 'op.create_table\|op.drop_table' plugins/adw/skills/conventions/SKILL.md
rtk proxy grep -n 'testcontainers' plugins/adw/skills/conventions/SKILL.md
# две строки: dev-деп с флором >=4.15 и глоб mypy без изменений
rtk proxy grep -n 'snapshot' plugins/adw/skills/conventions/SKILL.md
# утверждения «derived snapshot … as they stand» больше нет либо оно переформулировано
rtk proxy grep -n 'write-once\|autogenerate\|upgrade head' plugins/adw/skills/conventions/SKILL.md
# три уцелевших утверждения на местах
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json'   # пусто
```

Плюс чтением: докстринг шаблона называет **причину**, а не пересказывает, что делает код; комментарий
про суффикс имени `CheckConstraint` на месте.

## Что скажет warden

- **основание измерено дважды** — диагноз написан имплементером пробы в докстринге, и та же болезнь
  была в первой пробе; бисекция версии приведена;
- **механизмов ноль** — правка шаблона и одна строка зависимости;
- **флор законен по правилу самого скилла** (§D, «known breaking-version boundary»), форма как у
  `redis>=4.2`, причина рядом;
- **правило про флоры не переписано** — добавлено применение, не исключение.
