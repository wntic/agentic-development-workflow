# S25-05 — `when_to_use` у `python-style` называет третий предмет

Тип агента: **`adw-builder`**
Слой: **шипящееся** (`plugins/adw/skills/python-style/SKILL.md`) — warden докладывает про версию;
подъём готовит `/ship`.
Происхождение: решение человека 2026-08-10, принятое **по ходу волны S25**, после исполнения S25-02;
записано в секции решений `plan/findings/legacy.md` (одиннадцатая чистка) под заголовком «Второе
дополнение по ходу волны S25». Основание — та же **F-202**, чья диспозиция назвала только
`description`.

**Что это за задача.** Задача S25-02 привела к трём предметам вводную строку и `description`. Но
авто-вызов идёт по **сумме `description` + `when_to_use`** (`plan/PLATFORM.md`, вопрос 7), и оба
попадают в контекст **без тела**. `when_to_use` по-прежнему говорит:

```
when_to_use: Deciding an annotation form, a collection type, or how and where to log. Consulted
alongside the skill that owns the artifact, not instead of it.
```

— то есть половина триггерной поверхности продолжает описывать скилл как двухпредметный, и запрос
вида «нужен ли здесь комментарий» может его не поднять, хотя предмет в нём есть.

Запас потолка велик: сегодня `description` 490 + `when_to_use` 145 = **635 из 1536**.

Читать сначала:

- `plugins/adw/skills/python-style/SKILL.md` — фронтматтер целиком (оба поля) и вводную строку, чтобы
  третий предмет был назван теми же словами, что уже стоят в `description` после S25-02;
- правило про комментарии в `Hard stops` того же файла — предмет, который называется;
- `plugins/adw/skills/meta-skill-author/SKILL.md` — что этот каталог считает хорошим `when_to_use`
  (форма «когда применять», а не «что внутри»);
- тело записи грепом: `rtk proxy grep -n '^## F-202 ' plan/findings/legacy.md`, затем ~14 строк;
- обе строки решения — по F-202 и «Второе дополнение по ходу волны S25» — в секции решений
  2026-08-10 (одиннадцатая чистка) в конце того же файла.

## Задача

1. Дописать в `when_to_use` третий триггер — **решение о комментарии**: когда комментарий уместен,
   какой формы он бывает. Форма поля — «когда применять», а не пересказ правила: `when_to_use`
   отвечает на «в какой момент открыть этот скилл», а не «что он говорит».
2. Вторую половину поля («Consulted alongside the skill that owns the artifact, not instead of it»)
   сохранить — она про соседство и к предметам отношения не имеет.
3. Ничего больше: `description`, вводная строка и тело правила уже приведены S25-02 и не трогаются.

Файл шипится — текст английский, в тоне соседей.

## Deliverables

Правка в одном файле `plugins/adw/skills/python-style/SKILL.md`, поле `when_to_use`. Больше ничего.

## Границы

- Остальные файлы `plugins/adw/**`, `plan/**` (кроме чтения), `.claude/**` — не трогать.
- `description`, вводная строка и правило про комментарии — **не трогать**: они исполнены S25-02.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- Никакого механизма. Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
rtk proxy grep -c '^when_to_use: Deciding an annotation form, a collection type, or how and where to log\.' plugins/adw/skills/python-style/SKILL.md
# до: 1. После: 0 — поле больше не перечисляет ровно два предмета
rtk proxy grep -c 'Consulted alongside the skill that owns the artifact' plugins/adw/skills/python-style/SKILL.md
# до: 1. После: 1 — вторая половина поля сохранена
git diff --numstat -- plugins/adw/skills/python-style/SKILL.md
# до: пусто. После: 1 1 — ровно одна строка изменена, description и вводная не тронуты
git diff --stat -- plugins/adw/
# до: пусто. После: ровно один файл
claude plugin validate plugins/adw 2>&1 | tail -1
# до: ✔ Validation passed. После: то же
uv run --with pyyaml python -c "
import yaml,pathlib
fm=yaml.safe_load(pathlib.Path('plugins/adw/skills/python-style/SKILL.md').read_text().split('---')[1])
n=len(fm['description'])+len(fm['when_to_use'])
print(n, 'из 1536', 'OVER' if n>1536 else 'ok')"
# до: 635 из 1536 ok. После: больше 635 и по-прежнему ok
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- дифф — один файл, **одна строка**: тронуто только `when_to_use`;
- поле называет три триггера, и третий сформулирован как повод открыть скилл, а не как пересказ
  правила;
- «Consulted alongside…» сохранено; `description` и вводная строка байт-в-байт;
- потолок 1536 не пробит, валидатор зелёный; версия `plugins/adw` не тронута; механизма нет.
