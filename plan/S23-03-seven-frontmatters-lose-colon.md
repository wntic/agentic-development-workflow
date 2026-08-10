# S23-03 — семь фронтматтеров теряют `: ` внутри значения

Тип агента: **`adw-builder`**
Слой: **шипящееся** (семь файлов `plugins/adw/`) — warden докладывает про версию; подъём готовит
`/ship` при публикации, здесь версия не двигается.
Происхождение: решение человека 2026-08-10, `plan/findings/legacy.md`, секция «Решения человека,
2026-08-10 — девятая чистка (волна S23), платформа и плагин», строка **F-263**.

**Что это за задача.** `claude plugin validate plugins/adw` даёт **семь** ошибок, все одинаковые:
«YAML frontmatter failed to parse: YAML Parse error: Unexpected token. At runtime this skill loads
with empty metadata (all frontmatter fields silently dropped)». Причина — `: ` (двоеточие с
пробелом) внутри незакавыченного скаляра: строгий YAML на этом ломает **весь блок**, а не одно поле.

Утверждение валидатора о рантайме **опровергнуто** и это замерено: always-on стоимость всех семи
ненулевая, а `patterns` стоит в списке скиллов живой сессии со своими полями целиком. То есть парсер
рантайма мягче валидаторского. Сегодня не ломается ничего — правка нужна не поэтому, а потому что
`validate` остаётся нечитаемым, пока эти семь красные, и риск несимметричен: перейдёт рантайм на
строгий YAML — метаданные семи файлов исчезнут молча.

Решение — развилка (б): **убрать `: ` из формулировок**, а не закавычивать. Дешевле и не трогает
YAML вовсе.

Семь файлов и место двоеточия в каждом (проверено грепом до отправки задачи):

| файл | поле | фрагмент |
|---|---|---|
| `agents/implementer.md` | `description` | «…one exception inside the skeleton**:** when the change widens…» |
| `agents/test-author.md` | `description` | «Never writes the implementation**:** the change's skeleton…» |
| `skills/domain-exception/SKILL.md` | `description` | «…carrying `code**:** str` + `http_status**:** int`…» — **два** вхождения |
| `skills/domain-service/SKILL.md` | `description` | «…an entity cannot see**:** uniqueness across…» |
| `skills/infra-capability-adapter/SKILL.md` | `when_to_use` | «…a domain capability protocol**:** object storage…» |
| `skills/patterns/SKILL.md` | `description` | «They nest**:** compensation outside…» |
| `skills/restapi-endpoint/SKILL.md` | `description` | «…`restapi/routers/<resource>.py` — thin**:** parse input…» |

Читать сначала:

- фронтматтер каждого из семи файлов (строки 1–12) — целиком, чтобы переформулировка легла в тон;
- `plugins/adw/skills/meta-skill-author/SKILL.md`, правило про потолок `description` + `when_to_use`
  в 1536 символов — переформулировка не должна его пробить;
- тело записи грепом: `rtk proxy grep -n '^## F-263 ' plan/findings/legacy.md`, затем ~28 строк;
- строку решения по F-263 в секции решений 2026-08-10 (девятая чистка) в конце того же файла.

## Задача

1. В каждом из семи убрать `: ` **внутри значения** поля, сохранив смысл. Двоеточие как разделитель
   ключа (`description: `, `when_to_use: `) — не трогать, оно законно.
2. **`domain-exception` — самый аккуратный случай:** двоеточия там внутри бэктиков и читаются как
   аннотации типа (`code: str`, `http_status: int`). YAML бэктиков не различает. Переформулировать
   так, чтобы типы остались названы, — например «a `str` code and an `int` http_status». Смысл не
   теряется, форма — на усмотрение по месту.
3. Тире, точка с запятой, перестройка фразы — всё годится; главное, чтобы `description` и
   `when_to_use` остались тем, чем они являются: текстом, по которому скилл авто-инвокируется.
   Смысл каждой формулировки сохраняется; сокращать содержание не требуется и не разрешается.
4. Ничего больше: тела скиллов и ролей, прочие поля фронтматтера (`name`, `paths`, `tools`,
   `skills`, `model`) — не трогать.

Файлы шипятся — текст английский, в тоне соседей.

## Deliverables

Правки в семи файлах, названных таблицей выше. Больше ничего.

## Границы

- Остальные файлы `plugins/adw/**`, `plan/**` (кроме чтения), `.claude/**` — не трогать.
- `plugin.json` не трогать: версия двигается командой `/ship` при публикации.
- Кавычек вокруг скаляров **не добавлять** — решение выбрало развилку (б) именно против них.
- Никакого механизма. Не чинить найденное по дороге: находка — в отчёт.

## Проверка

Прогнана на нетронутом дереве до отправки задачи **записанными строками**; ответ «до» назван у
каждой.

```bash
claude plugin validate plugins/adw 2>&1 | rtk proxy grep -c 'frontmatter: YAML frontmatter failed to parse'
# до: 7. После: 0 — главная проверка задачи
rtk proxy grep -c '^description:\|^when_to_use:' plugins/adw/skills/patterns/SKILL.md
# до: 2. После: 2 — поля на месте, не слиты и не потеряны
git diff --stat -- plugins/adw/
# до: пусто. После: ровно семь файлов
git status --porcelain -- plugins/adw/.claude-plugin/
# до: пусто. После: пусто — версия не тронута
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

Плюс проверка потолка — по каждому тронутому файлу, замером **значений**, а не байтов строк
(F-204 — форма `sed | wc -c` считает не ту величину):

```bash
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
# до: семь строк PARSE-FAIL — те же семь файлов, что называет валидатор, независимым парсером;
#     ни одной строки OVER.
# После: пусто целиком — ни PARSE-FAIL, ни OVER: строгий YAML читает все, потолок не пробит.
```

Форма с `try/except` — не украшение: без неё команда падает на первом же из семи и не доходит до
проверки потолка. Прогнана в обоих видах до отправки задачи.

## Что скажет warden

- `claude plugin validate plugins/adw` даёт **ноль** ошибок парса фронтматтера;
- дифф — ровно семь файлов, и в каждом тронуто только значение `description` или `when_to_use`;
- кавычек вокруг скаляров не добавлено; смысл каждой формулировки сохранён, не сокращён;
- потолок 1536 не пробит ни одним файлом, и проверен замером значений, а не байтов строк;
- версия `plugins/adw` не тронута — верно, подъём готовит `/ship`;
- механизма нет.
