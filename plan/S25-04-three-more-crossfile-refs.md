# S25-04 — ещё три межфайловые ссылки, одна из них сломана по имени файла

Тип агента: **`adw-builder`**
Слой: **шипящееся** (три скилла) — warden докладывает про версию; подъём готовит `/ship`.
Происхождение: решение человека 2026-08-10, принятое **по ходу волны S25**, после исполнения S25-01;
записано отдельной строкой в секции решений `plan/findings/legacy.md` (одиннадцатая чистка).
Основание — та же F-197, чей замер оказался неполным.

**Что это за задача.** Команда замера в теле F-197 — `grep -rn 'rule [0-9]\|rules [0-9]'` —
**регистрозависима**, а в каталоге преобладает форма `Rule N` с большой буквы. Из-за этого запись
насчитала четыре межфайловые ссылки, а их **семь**. Четыре исполнены задачей S25-01. Три остались:

| файл | строка | ссылка | цель |
|---|---|---|---|
| `skills/test-application-handler/SKILL.md` | 185 | «`test-fake-repository` **Rule 9**» | цель есть: `test-fake-repository:180`, «Never alias the caller's entity — store and return COPIES» |
| `skills/test-discovery-invariants/SKILL.md` | 144 | «mirrors **test-restapi-endpoint Rule 9**» | цель есть: `test-restapi-endpoint:204`, «Error responses are asserted by `code`, not by message» |
| `skills/restapi-schema/SKILL.md` | 51 | «**domain-filter Rule 5**» | **скилла `domain-filter` не существует**; предмет — правило про одну форму пагинации, и живёт оно в `domain-model` («One pagination shape, explicitly», `:287`) |

Третья сломана **дважды** — и по номеру, и по имени: `ls plugins/adw/skills/domain-filter` → нет
такого каталога. Это не риск дрейфа, а ссылка, которая не открывается сегодня.

**Тот же довод, что у S25-01:** ссылка по словам не ломается от перенумерации в чужом файле вообще,
а довод диспозиции F-174 («перенумерация внутри файла — видимая правка») межфайловый случай не
покрывает.

Читать сначала:

- каждую из трёх строк с окружением (номер строки — удобство, предмет опознаётся по цитате);
- **правило в файле-цели** по каждой, чтобы назвать его словами верно, а не по памяти;
- как это сделано в S25-01 — четыре уже исправленные ссылки в
  `test-application-handler`, `test-fake-repository`, `restapi-schema`, `infra-store-repository`:
  `rtk proxy grep -rn "'s .*rule\|s rule that" plugins/adw/skills/` — форма именования уже задана,
  и новые три ей следуют;
- тело записи грепом: `rtk proxy grep -n '^## F-197 ' plan/findings/legacy.md`, затем ~27 строк;
- строку решения по F-197 и **строку про эти три** в секции решений 2026-08-10 (одиннадцатая чистка).

## Задача

1. Три ссылки называют правило **словами**, с сохранением имени файла-цели.
2. У третьей чинится **и имя**: цель — `domain-model`, а не `domain-filter`. Скилла с последним
   именем в каталоге нет; проверить это самому (`ls plugins/adw/skills/`), а не поверить задаче.
3. **Внутрифайловые ссылки по ординалу не трогать** — их в каталоге много (`Rule 2`, `Rule 5`,
   `Rule 8`, `Rule 9`, `Rule 11`, `Rule 12` внутри своих файлов), и довод F-174 на них работает.
   Контроль: `(Rule 7)` в `restapi-schema` и `(rule 12)` в `infra-wiring` должны остаться.
4. Ничего больше: правила в файлах-целях не трогать, нумерацию нигде не менять.

Файлы шипятся — текст английский, в тоне соседей.

## Deliverables

Правки в трёх файлах: `plugins/adw/skills/test-application-handler/SKILL.md`,
`plugins/adw/skills/test-discovery-invariants/SKILL.md`,
`plugins/adw/skills/restapi-schema/SKILL.md`. Больше ничего.

## Границы

- Файлы-цели (`test-fake-repository`, `test-restapi-endpoint`, `domain-model`) — **не трогать**,
  только читать.
- Внутрифайловые ссылки по ординалу — не трогать.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- Никакого механизма. Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
rtk proxy grep -c 'test-fake-repository. Rule 9' plugins/adw/skills/test-application-handler/SKILL.md
rtk proxy grep -c 'mirrors test-restapi-endpoint Rule 9' plugins/adw/skills/test-discovery-invariants/SKILL.md
rtk proxy grep -c 'domain-filter Rule 5' plugins/adw/skills/restapi-schema/SKILL.md
# до: 1, 1, 1. После: 0, 0, 0 — ни одного ординала в этих трёх межфайловых ссылках
rtk proxy grep -c 'domain-filter' plugins/adw/skills/restapi-schema/SKILL.md
# до: 2. После: 0 — имени несуществующего скилла в файле не осталось вовсе
rtk proxy grep -c '(Rule 7)' plugins/adw/skills/restapi-schema/SKILL.md
rtk proxy grep -c '(rule 12)' plugins/adw/skills/infra-wiring/SKILL.md
# до: 1 и 1. После: 1 и 1 — внутрифайловые ссылки не тронуты
git status --porcelain -- plugins/adw/skills/test-fake-repository/ plugins/adw/skills/test-restapi-endpoint/ plugins/adw/skills/domain-model/ plugins/adw/.claude-plugin/
# до: пусто. После: пусто — файлы-цели и версия не тронуты
git diff --stat -- plugins/adw/
# до: пусто. После: ровно три файла
claude plugin validate plugins/adw 2>&1 | tail -1
# до: ✔ Validation passed. После: то же
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

Второе вхождение `domain-filter` в `restapi-schema` — соседняя строка того же комментария («A
resource whose domain-filter chose cursor paging»), и она тоже называет несуществующий скилл. Обе
приводятся к `domain-model`; поэтому «после: 0», а не «после: 1».

## Что скажет warden

- дифф — ровно три файла, в каждом тронута ссылка (в `restapi-schema` — обе строки одного
  комментария);
- ни одна из трёх больше не называет правило номером, и по новым словам правило находится грепом в
  файле-цели;
- имени `domain-filter` в каталоге не осталось: цель названа существующим скиллом;
- внутрифайловые ссылки и файлы-цели не тронуты; нумерация нигде не сдвинута;
- валидатор зелёный; версия `plugins/adw` не тронута; механизма нет.
