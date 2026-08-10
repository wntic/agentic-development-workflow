# S25-01 — четыре межфайловые ссылки называют правило словами

Тип агента: **`adw-builder`**
Слой: **шипящееся** (четыре скилла) — warden докладывает про версию; подъём готовит `/ship`.
Происхождение: решение человека 2026-08-10, `plan/findings/legacy.md`, секция «Решения человека,
2026-08-10 — одиннадцатая чистка (волна S25), последние девять записей F-серии», строка **F-197**.

**Что это за задача.** Диспозиция F-174 оставила ссылки на правило по ординалу, и её довод —
«перенумерация внутри файла есть видимая правка, значит ссылка чинится тем же диффом». Для
**межфайловых** ссылок довод не работает: перенумерация правил в `application`,
`test-application-handler`, `domain-model` или `infra-capability-adapter` в диффе ссылающегося файла
не видна вообще, и ссылка молча укажет на чужое правило.

Четыре адресата, перемерены на день решения и все живы:

| файл | строка | ссылка |
|---|---|---|
| `skills/test-application-handler/SKILL.md` | 171 | «mirrors `application` DTO **rule 2**» |
| `skills/test-fake-repository/SKILL.md` | 199 | «see `test-application-handler` **rule 10**» |
| `skills/restapi-schema/SKILL.md` | 99 | «`domain-model`, filter-record **rule 5**» |
| `skills/infra-store-repository/SKILL.md` | 226 | «`infra-capability-adapter` **rules 13–15**» |

Внутрифайловые ссылки (`infra-wiring:286`, четыре в `meta-skill-author`) **не трогаются** — там довод
F-174 работает.

Читать сначала:

- каждую из четырёх строк с окружением: `rtk proxy grep -n -B2 -A2 'DTO rule 2' plugins/adw/skills/test-application-handler/SKILL.md`
  и так по каждой — номер строки удобство, **предмет опознаётся по цитате** (`ORIENT` §4);
- **правило, на которое ссылаются, в файле-цели** — чтобы назвать его словами верно, а не по памяти:
  `application` DTO rule 2, `test-application-handler` rule 10, `domain-model` filter-record rule 5,
  `infra-capability-adapter` rules 13–15;
- тело записи грепом: `rtk proxy grep -n '^## F-197 ' plan/findings/legacy.md`, затем ~27 строк;
- строку решения по F-197 в секции решений 2026-08-10 (одиннадцатая чистка) в конце того же файла.

## Задача

1. В каждой из четырёх строк заменить ординал на **имя правила словами** — так, чтобы читатель нашёл
   его в файле-цели грепом по словам, а не счётом. Имя файла-цели сохраняется: ломается номер, не
   адресация.
2. Для `infra-store-repository` (диапазон «rules 13–15») назвать словами **то, на что ссылаются**, —
   это контракт тонкости адаптера; перечислять три правила по отдельности не требуется, если одна
   формулировка их покрывает.
3. Ничего больше: внутрифайловые ссылки не трогать, сами правила в файлах-целях не трогать,
   нумерацию правил нигде не менять.

Файлы шипятся — текст английский, в тоне соседей.

## Deliverables

Правки в четырёх файлах из таблицы выше. Больше ничего.

## Границы

- Файлы-цели (`application`, `domain-model`, `infra-capability-adapter`) — **не трогать**, только
  читать; в трёх из четырёх случаев цель и ссылающийся файл разные.
- Внутрифайловые ссылки по ординалу (`infra-wiring`, `meta-skill-author`) — не трогать.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- Никакого механизма. Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
rtk proxy grep -c 'application. DTO rule 2' plugins/adw/skills/test-application-handler/SKILL.md
rtk proxy grep -c 'test-application-handler. rule 10' plugins/adw/skills/test-fake-repository/SKILL.md
rtk proxy grep -c 'filter-record rule 5' plugins/adw/skills/restapi-schema/SKILL.md
rtk proxy grep -c 'infra-capability-adapter. rules 13–15' plugins/adw/skills/infra-store-repository/SKILL.md
# до: 1, 1, 1, 1. После: 0, 0, 0, 0 — ни одного ординала в межфайловой ссылке
rtk proxy grep -c '(rule 12)' plugins/adw/skills/infra-wiring/SKILL.md
# до: 1. После: 1 — внутрифайловая ссылка не тронута
git diff --stat -- plugins/adw/
# до: пусто. После: ровно четыре файла
git status --porcelain -- plugins/adw/skills/application/ plugins/adw/skills/domain-model/ plugins/adw/skills/infra-capability-adapter/ plugins/adw/.claude-plugin/
# до: пусто. После: пусто — файлы-цели и версия не тронуты
claude plugin validate plugins/adw 2>&1 | tail -1
# до: ✔ Validation passed. После: то же
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- дифф — ровно четыре файла, в каждом тронута одна ссылка;
- ни одна межфайловая ссылка больше не называет правило номером, и по новым словам правило находится
  грепом в файле-цели;
- файлы-цели и внутрифайловые ссылки не тронуты; нумерация правил нигде не сдвинута;
- валидатор зелёный; версия `plugins/adw` не тронута; механизма нет.
