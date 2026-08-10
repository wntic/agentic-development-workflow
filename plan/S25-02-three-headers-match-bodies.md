# S25-02 — три объявления приводятся к тому, что под ними стоит

Тип агента: **`adw-builder`**
Слой: **шипящееся** (три файла) — warden докладывает про версию; подъём готовит `/ship`.
Происхождение: решение человека 2026-08-10, `plan/findings/legacy.md`, секция «Решения человека,
2026-08-10 — одиннадцатая чистка (волна S25), последние девять записей F-серии», строки **F-201**,
**F-202**, **F-211**.

**Что это за задача.** Три места, где объявление уже не описывает своё тело. Все три — правки
шипящихся файлов, каждая в один файл.

**F-201.** `conventions` описывает поверхности линта дважды: §C говорит «всё дерево, `migrations/`
включительно», §E на строке с «Lint and type-check cover both trees at parity» — «два дерева».
Формально противоречия нет (§E про **паритет** `src`↔`tests`), но читатель ищет поверхности в §E,
где стоит конфиг тулчейна, и про третий каталог не узнаёт. Правится §E — место, куда ходят.

**F-202.** `python-style` объявляет «Two subjects, each with a per-layer edge», и `description` в
фронтматтере называет ровно эти два: типы и логирование. Правило про комментарии — третий предмет
того же файла. **Важно именно `description`**: при авто-вызове он попадает в контекст **без тела**,
поэтому предмет, которого в нём нет, для вызывающего не существует.

**F-211.** Заголовок раздела `implementer.md` — «On the project's first change, the `Makefile` is
part of the substrate» — называет один артефакт, а раздел перечисляет пять классов: оболочка,
wiring, `Makefile`, конфигурация тулчейна, бутстрап Alembic. Решение: **заголовок приводится к
содержанию**, а не содержание к заголовку.

Читать сначала:

- `plugins/adw/skills/conventions/SKILL.md` — §C (поверхности, `migrations/`) и §E целиком:
  `rtk proxy grep -n -B4 -A4 'Lint and type-check cover both trees' plugins/adw/skills/conventions/SKILL.md`;
- `plugins/adw/skills/python-style/SKILL.md` — фронтматтер (`description`) и вводная строка «Two
  subjects…», плюс раздел `Hard stops`, где живёт правило про комментарии;
- `plugins/adw/agents/implementer.md` — раздел с заголовком про `Makefile` целиком, чтобы новый
  заголовок покрывал все пять классов;
- тела трёх записей грепом: `rtk proxy grep -n '^## F-201 \|^## F-202 \|^## F-211 ' plan/findings/legacy.md`;
- строки решений по трём в секции решений 2026-08-10 (одиннадцатая чистка) в конце того же файла.

## Задача

1. **`conventions` §E** — строка про поверхности называет третий каталог: линт и типы видят
   `src`, `tests` **и** `migrations/`. Утверждение о **паритете** `src`↔`tests` сохраняется — оно про
   другое (одинаковая строгость), и его не заменять.
2. **`python-style`** — и вводная строка, и `description` во фронтматтере называют **три** предмета:
   типы, логирование, комментарии. `description` — обязательная часть правки, а не факультативная:
   он и есть то, что грузится без тела.
3. **`implementer.md`** — заголовок раздела называет **субстрат** как класс, а не `Makefile` как
   пример. Содержание раздела не трогать.
4. Ничего больше.

Файлы шипятся — текст английский, в тоне соседей. Потолок `description` + `when_to_use` у `python-style` сегодня **479 из 1536** — запас велик,
но команда в «Проверке» его перемеряет.

## Deliverables

Правки в трёх файлах: `plugins/adw/skills/conventions/SKILL.md`,
`plugins/adw/skills/python-style/SKILL.md`, `plugins/adw/agents/implementer.md`. Больше ничего.

## Границы

- Остальные файлы `plugins/adw/**`, `plan/**` (кроме чтения), `.claude/**` — не трогать.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- §C `conventions`, тело раздела `implementer.md` и правило про комментарии в `python-style` — не
  переформулировать; правятся объявления, а не то, что они объявляют.
- Никакого механизма. Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
rtk proxy grep -c 'Lint and type-check cover both trees' plugins/adw/skills/conventions/SKILL.md
# до: 1. После: 0 — §E больше не говорит «два дерева»
rtk proxy grep -c 'migrations' plugins/adw/skills/conventions/SKILL.md
# до: 12. После: ≥13 — третий каталог назван в §E
rtk proxy grep -c 'Two subjects' plugins/adw/skills/python-style/SKILL.md
# до: 1. После: 0 — объявление называет три предмета
rtk proxy grep -ci 'comment' plugins/adw/skills/python-style/SKILL.md
# до: 6. После: ≥7 — предмет назван и в description
rtk proxy grep -c "the .Makefile. is part of the" plugins/adw/agents/implementer.md
# до: 1. После: 0 — заголовок называет класс, а не пример
git diff --stat -- plugins/adw/
# до: пусто. После: ровно три файла
claude plugin validate plugins/adw 2>&1 | tail -1
# до: ✔ Validation passed. После: то же
uv run --with pyyaml python -c "
import pathlib, yaml
for p in pathlib.Path('plugins/adw').rglob('*.md'):
    t = p.read_text()
    if not t.startswith('---'): continue
    try: fm = yaml.safe_load(t.split('---')[1])
    except Exception: print('PARSE-FAIL', p); continue
    if not isinstance(fm, dict): continue
    n = len(fm.get('description','') or '') + len(fm.get('when_to_use','') or '')
    if n > 1536: print('OVER', p, n)
"
# до: пусто целиком. После: пусто целиком — потолок 1536 не пробит
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- дифф — ровно три файла, в каждом тронуто объявление, а не то, что оно объявляет;
- `python-style` изменён **и** во вводной строке, **и** в `description` — иначе правка не достигает
  цели, потому что грузится без тела именно `description`;
- паритет `src`↔`tests` в §E сохранён как отдельное утверждение;
- заголовок `implementer.md` покрывает все пять классов субстрата;
- валидатор зелёный, потолок 1536 не пробит; версия `plugins/adw` не тронута; механизма нет.
