# S24-02 — `domain-model` сам говорит, как достаётся модуль с публичной функцией

Тип агента: **`adw-builder`**
Слой: **шипящееся** (`plugins/adw/skills/domain-model/SKILL.md`) — warden докладывает про версию;
подъём готовит `/ship`, здесь версия не двигается.
Происхождение: решение человека 2026-08-10, `plan/findings/legacy.md`, секция «Решения человека,
2026-08-10 — десятая чистка (волна S24), проза разошлась с деревом», строка **F-205**.

**Что это за задача.** Решение F-144 назвало домом предиката **модульную функцию** в домене — формы,
которой в каталоге до того не было. От этого два указания на одном шаге стали исключать друг друга:

- `domain-model` говорит «After writing the module, follow `architecture` to add the subpackage
  `__init__.py` re-export line and append to its `__all__`»;
- `architecture` карве-аут 3 говорит, что модуль, чьё публичное имя — голый объект, а не класс,
  **не** вайлдкардится в `__init__` пакета и достаётся явным относительным импортом; плюс
  «One class per module file» и «These are the **only** exceptions, and the carve-out is by exact
  file path».

Автор, исполнивший новый случай, выберет сам — и в двух проектах выйдет разное.

Решение — развилка (б): чинится **`domain-model`**, `architecture` не трогается вовсе. Развилка (а)
(четвёртое named-исключение) отклонена человеком: она растит перечень исключений в файле, которого
решение F-144 не касалось, ради случая с одним экземпляром.

Читать сначала:

- `plugins/adw/skills/domain-model/SKILL.md` — правило, введённое F-144 (случай модульной функции как
  дома предиката), и раздел `Package wiring` целиком: `rtk proxy grep -n -B6 -A4 'follow .architecture. to add the subpackage' plugins/adw/skills/domain-model/SKILL.md`;
- `plugins/adw/skills/architecture/SKILL.md` — карве-аут 3 и перечень исключений
  (`rtk proxy grep -n -B2 -A8 'wildcard only class-modules' plugins/adw/skills/architecture/SKILL.md`)
  — **читать, не править**: это та форма, которой `domain-model` обязан соответствовать;
- тело записи грепом: `rtk proxy grep -n '^## F-205 ' plan/findings/legacy.md`, затем ~27 строк;
- строку решения по F-205 в секции решений 2026-08-10 (десятая чистка) в конце того же файла.

## Задача

1. В `domain-model`, в том месте, где новый случай велит «follow `architecture` …», сказать прямо:
   модуль, чьё публичное имя — **функция**, а не класс, попадает под карве-аут `architecture` —
   он **не** вайлдкардится в `__init__` пакета, `__all__` не растит, и достаётся **явным
   относительным импортом**. То есть общее указание про re-export этого случая не касается.
2. Формулировка должна оставлять общий случай (модуль-класс) как есть: там re-export и `__all__`
   по-прежнему обязательны.
3. `architecture` **не трогать** — ни карве-аут, ни перечень исключений, ни «One class per module
   file». Это условие решения, а не пожелание.
4. Ничего больше.

Файл шипится — текст английский, в тоне файла; имени карве-аута по номеру не цитировать, если файл
так не ссылается (межфайловая ссылка по ординалу — записанный класс F-174); ссылаться словами.

## Deliverables

Правка в одном файле `plugins/adw/skills/domain-model/SKILL.md`. Больше ничего.

## Границы

- `plugins/adw/skills/architecture/SKILL.md` — **не трогать**, только читать.
- Остальные файлы `plugins/adw/**`, `plan/**` (кроме чтения), `.claude/**` — не трогать.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- Никакого механизма. Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
rtk proxy grep -c 'follow .architecture. to add the subpackage' plugins/adw/skills/domain-model/SKILL.md
# до: 1. После: ≥1 — общее указание для модуля-класса на месте, не удалено
rtk proxy grep -ci 'relative import' plugins/adw/skills/domain-model/SKILL.md
# до: 0. После: ≥1 — сказано, как достаётся модуль с публичной функцией
git status --porcelain -- plugins/adw/skills/architecture/
# до: пусто. После: пусто — соседний файл не тронут
rtk proxy grep -c 'wildcard only class-modules' plugins/adw/skills/architecture/SKILL.md
# до: 1. После: 1 — карве-аут не переписан
git diff --stat -- plugins/adw/
# до: пусто. После: ровно один файл
claude plugin validate plugins/adw 2>&1 | tail -1
# до: ✔ Validation passed. После: то же
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- дифф — один файл `domain-model/SKILL.md`; `architecture` не тронут ни строкой;
- новый случай теперь сам говорит, как модуль достаётся, и общее указание для модуля-класса цело;
- ссылка на карве-аут — словами, не по номеру;
- валидатор зелёный; версия `plugins/adw` не тронута;
- механизма нет.
