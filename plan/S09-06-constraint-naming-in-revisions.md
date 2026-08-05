# S09-06 — в ревизии действует то же правило именования, что и в объявлении таблицы

Тип агента: **`adw-builder`**
Слой: **ядро** (`plugins/adw/skills/infra-persistence/SKILL.md` — единственный файл)
Происхождение: решение человека 2026-08-05, `plan/FINDINGS.md`, секция «Решения человека, 2026-08-05 —
по находкам исполнения S09», строка **F-171**.

Читать сначала:
- в `plan/FINDINGS.md` — тело **F-171** заголовочным грепом и строку решения по нему: она несёт замер
  **шире**, чем тело находки, и объём починки задаёт именно она;
- `plugins/adw/skills/infra-persistence/SKILL.md`, строки ~57–80 — конвенция именования и правило
  «**For a `CheckConstraint`, `name=` is the suffix**» (`:75`);
- тот же файл, строки ~144–152 — четыре пункта про `name=`, из которых правится один;
- тот же файл, шаблон ревизии ~455–490 — там стоит неверная форма, и там же стоят две верные
  (`op.create_index` с позиционным именем);
- тот же файл, ~405–415 — `_map_integrity_error`, который матчит на конвенциональное имя. Он верен и
  объясняет, **почему** удвоение не косметическое;
- `plugins/adw/skills/conventions/SKILL.md`, шаблон baseline-ревизии (~230–266) — он правлен задачей
  S09-02 и уже несёт правильную форму с комментарием про суффикс. Два скилла должны сойтись.

## Основание

`infra-persistence:149–151` сегодня говорит: «**In an Alembic revision, write the full conventional name
yourself** — `name="fk_foos_bar_id_bars"`, `name="uq_foos_name"`, `name="ck_foos_name_non_empty"`.
Alembic does not read the `Table`'s metadata convention; it serializes what you write», и шаблон на
`:479–480` пишет полные имена.

Замерено главной сессией на alembic 1.18.5 / SQLAlchemy 2.0.51, `MigrationContext` с `target_metadata`,
несущей конвенцию — то есть ровно то, что делает `env.py` из `conventions`:

```
# с полным именем
CheckConstraint   name="ck_foos_name_non_empty"  -> ck_foos_ck_foos_name_non_empty
UniqueConstraint  name="uq_foos_name"            -> uq_foos_name

# без явного name вовсе
CheckConstraint   name="name_non_empty"          -> ck_foos_name_non_empty
ForeignKeyConstraint (без name)                  -> fk_foos_bar_id_bars
PrimaryKeyConstraint (без name)                  -> pk_foos
UniqueConstraint     (без name)                  -> uq_foos_name
```

Читается это так: alembic конвенцию **читает**, для всех четырёх видов. У `ck` конвенция
`ck_%(table_name)s_%(constraint_name)s` подставляет переданное имя как `constraint_name`, поэтому полное
имя удваивает префикс. У `uq`, `pk` и `fk` конвенция интерполирует колонки, поэтому явное полное имя
проходит как написано — безвредно, но и не нужно.

Отсюда починка — **вычёркивание, а не новое правило**: правило ревизии совпадает с правилом объявления
`Table`, которое тот же файл уже даёт тремя пунктами выше.

## Задача

**1. Пункт `:149–151` переписывается.** Его существо сегодня — «в ревизии всё иначе». После правки:
в ревизии действует то же правило, что и в `Table` (пункты выше — не передавать `name=` для pk / fk /
uq / индекса внутри `op.create_table`, передавать **суффикс** для `CheckConstraint`), потому что
`op.create_table` строит таблицу на metadata, несущей конвенцию из `target_metadata`, которую отдаёт
`env.py`.

Пункт обязан назвать **почему у `ck` иначе**, иначе правка не защищена от отката: конвенция `ck`
интерполирует переданное имя, и полное имя даёт `ck_foos_ck_foos_…`. Утверждение
«Alembic does not read the `Table`'s metadata convention; it serializes what you write» **уходит** — оно
ложно.

**2. Шаблон ревизии приводится.** `:479` — `sa.UniqueConstraint("name", name="uq_foos_name")` →
имя не передаётся вовсе. `:480` — `sa.CheckConstraint("char_length(name) > 0",
name="ck_foos_name_non_empty")` → суффикс `name="name_non_empty"`. Если в шаблоне есть ещё
`PrimaryKeyConstraint` или `ForeignKeyConstraint` с явным именем **внутри `op.create_table`** — они
идут туда же. Проверь чтением, а не по этому перечню: он снят с грепа, а не с полного чтения шаблона.

**3. Одна строка-комментарий в шаблоне**, как в `conventions` после S09-02: у `CheckConstraint` имя —
суффикс, конвенция припишет `ck_<table>_`. Форма комментария у соседнего скилла уже есть; сделай
такую же по существу, не копируй дословно чужой пример таблицы.

## Deliverables

Один файл — `plugins/adw/skills/infra-persistence/SKILL.md`. Пункт правила и шаблон ревизии.

## Границы

- **Только `infra-persistence/SKILL.md`.** `conventions` правлен задачей S09-02 и уже сошёлся — не
  трогай его.
- **`op.create_index("ix_foos_bar_id", "foos", ["bar_id"])` (`:482–483`) не трогать** — там имя
  позиционный аргумент отдельной операции, а не констрейнт внутри `op.create_table`; полное имя
  обязательно и верно. Замерено, что это другой случай.
- **`_map_integrity_error` (`:410`) не трогать** — он несёт полное конвенциональное имя в payload
  ошибки, и это верно: в БД имя полное, суффикс — только то, что пишет автор.
- **Три пункта про `name=` выше правимого (`:145–148`) не трогать** — они верны, и правка как раз
  распространяет их на ревизию.
- **Конвенцию (`:57–80`) не трогать.**
- **Никакого нового правила и никакого hard stop.** Существо правки — что одного правила достаточно
  там, где стояло два противоположных.
- Не чинить найденное по дороге.

## Проверка

```bash
git diff --stat -- plugins/adw/skills/infra-persistence/SKILL.md     # ровно один файл
rtk proxy grep -rn 'does not read the' plugins/adw/                  # пусто
rtk proxy grep -n 'ck_foos_name_non_empty' plugins/adw/skills/infra-persistence/SKILL.md
# ни одного вхождения как значения name=; допустимо в тексте про _map_integrity_error, если оно там есть
rtk proxy grep -n 'name_non_empty\|uq_foos_name' plugins/adw/skills/infra-persistence/SKILL.md
rtk proxy grep -n 'op.create_index' plugins/adw/skills/infra-persistence/SKILL.md   # две строки, не тронуты
rtk proxy find plugins/adw -name '*.py'      # пусто
rtk proxy find plugins/adw -name '*.sh'      # пусто
rtk proxy find plugins/adw -name 'hooks.json'  # пусто
```

Проверка красной линии 2 разбита на три вызова сознательно: составные предикаты `find` хук переписывает
в `rtk find`, который их не умеет, и команда падает ненулевым кодом там, где обязан быть пустой вывод
(F-71, и это подтвердил исполнитель S09-01 в этой же волне).

Плюс **прогоном**, потому что шаблон — исполняемый код и утверждение о нём проверяемо. Собери из
правленого шаблона `op.create_table` в `MigrationContext` с `target_metadata`, несущей конвенцию
скилла, и напечатай имена констрейнтов. Ожидание: `pk_foos`, `uq_foos_name`, `ck_foos_name_non_empty`,
и ни одного удвоенного префикса. Интерпретатор с alembic и SQLAlchemy — `~/Projects/adw-rooms/.venv`
(`cd ~/Projects/adw-rooms && uv run python …`); **ничего в том дереве не создавай и не правь**, оно
чужое и его правит другая задача.

## Что скажет warden

- **основание измерено дважды** — с полным именем и без имени вовсе, обе таблицы в файле задачи;
- **механизмов ноль** — переписан один пункт и приведён шаблон; правил стало **меньше**, не больше;
- **два скилла сошлись** — `conventions` после S09-02 и `infra-persistence` после этой задачи говорят
  про одно место одно и то же;
- **три верных соседних утверждения не тронуты** — `op.create_index`, `_map_integrity_error` и три
  пункта про `name=` в объявлении `Table`.
