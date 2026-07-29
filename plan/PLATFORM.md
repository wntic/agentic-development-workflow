# PLATFORM.md — замеренные свойства платформы

**Дата замера: 2026-07-29. Версия: `claude --version` → `2.1.220 (Claude Code)`. macOS Darwin 25.3.0.**
Факт о платформе без версии — факт с неизвестным сроком годности. При смене минора перепроверять.

Три пометки, других нет:

- **ЗАМЕРЕНО** — команда запущена, вывод наблюдён и приведён.
- **ИЗ ДОКОВ** — так написано в `code.claude.com/docs` на эту дату, эксперимента не было; цитата и страница даны.
- **НЕ ПРОВЕРЕНО** — установить не удалось. Это законченный ответ.

---

## Стенд

Всё — в скратчпад-каталоге сессии, в репозиторий не попало ничего, кроме этого файла.

- `<scratch>/probe/probeplug/` — выбрасываемый плагин: `.claude-plugin/plugin.json` (`"name": "probeplug"`),
  `skills/canary-skill/SKILL.md`, `agents/*.md` (пробные агенты).
- `<scratch>/probe/proj/`, `proj2/`, `proj3/` — рабочие каталоги дочерних сессий, у части — `.claude/agents/`.
- Дочерние сессии: `claude -p ... --plugin-dir <scratch>/probe/probeplug`, где нужно —
  `--output-format stream-json --verbose --forward-subagent-text` (видно **собственные** сообщения и
  тул-коллы сабагента, а не только пересказ родителя) и `--debug-file <path>`.

**Как отличался успех от тихого несрабатывания.** В теле скилла лежит токен
`XQ7-ZEBRAFISH-KLONDIKE-9931`, которого нет ни в промпте агента, ни в промпте родителя, ни где-либо
ещё. У пробных агентов `tools: Glob` — прочитать файл они не могут. У всех замеров ниже в
`tool_result` родителя видно `tool_uses: 0`, то есть токен мог попасть в ответ только предзагрузкой.
Контроль — тот же агент без поля `skills:` — обязан отвечать `TOKEN=UNKNOWN`, и отвечает.
«Сабагент успешно завершился» ничего не различает и нигде не использовано как доказательство.

---

## Вопрос 1. Какая форма имени плагинного скилла принимается в `skills:`

**Что сделал.** Четыре плагинных агента, различающихся одной строкой `skills:`, и один
project-scoped агент. Каждый — `tools: Glob`, тело промпта одинаковое: «если в контексте есть
canary-токен — выведи `TOKEN=<токен>`, иначе `TOKEN=UNKNOWN`, инструментами не пользоваться».
Диспатч каждого отдельной дочерней сессией, поток захвачен в `stream-json`.

**Что наблюдал** (`tool_result` родителя, дословно):

| `skills:` | Где лежит агент | Ответ сабагента | `subagent_tokens` |
|---|---|---|---|
| `probeplug:canary-skill` | плагин | `TOKEN=XQ7-ZEBRAFISH-KLONDIKE-9931` | 2172 |
| `canary-skill` | плагин | `TOKEN=XQ7-ZEBRAFISH-KLONDIKE-9931` | 2162 |
| `/probeplug:canary-skill` | плагин | `TOKEN=UNKNOWN` | 1937 |
| `definitely-no-such-skill-9931` | плагин | `TOKEN=UNKNOWN` | 1937 |
| — (поля нет, контроль) | плагин | `TOKEN=UNKNOWN` | 1937 |
| `probeplug:canary-skill` | `.claude/agents/` проекта | `TOKEN=XQ7-ZEBRAFISH-KLONDIKE-9931` | — |

`tool_uses: 0` у всех шести. Счётчик токенов — второй независимый признак: у сработавшей
предзагрузки +≈230 токенов, у несработавшей — ровно как у контроля.

**Реальный скилл этого репозитория, не игрушечный.** Агент с `skills: adw:testing-unit`, `tools: Glob`,
плагин подан как `--plugin-dir /Users/egorvorobyev/Projects/agentic-development-workflow/plugins/adw`.
Спрошено то, что есть только в теле скилла. Ответ (дословно, начало):

```
(a) **7 test artifacts**, each carried by its own topic file next to the router: `handler.md`,
`fake.md`, `entity.md`, `value-object.md`, `enum.md`, `domain-service.md`, `architecture-rule.md`.

(b) The closed autouse list appears in the tier-wide hard stops, verbatim:
> A "convenience" autouse fixture is proposed → stop, the autouse list is closed (DB guard,
> migration, bucket cleanup, optional singleton reset). ...
```

Тот же промпт без поля `skills:` → `NO-SKILL`. `subagent_tokens`: **6810** против **1996** у контроля.
В дебаг-логе:

```
[DEBUG] [Agent: probeplug:adw-ns] Preloaded skill 'adw:testing-unit'
```

**Что происходит при неверной форме.** Тихое игнорирование: агент запускается, работает, ничего не
сообщает. Родителю — ни ошибки, ни предупреждения. Единственный след — дебаг-лог (`--debug-file`):

```
[WARN] [Agent: probeplug:canary-bogus] Warning: Skill 'definitely-no-such-skill-9931' specified in frontmatter was not found
[WARN] [Agent: probeplug:canary-slash] Warning: Skill '/probeplug:canary-skill' specified in frontmatter was not found
```

**Коллизия имён.** Добавлен project-скилл с тем же `name: canary-skill` и другим токеном
(`PQ2-NARWHAL-TUNDRA-5507`), плагинный оставлен на месте:

- `skills: canary-skill` (короткая форма) → `TOKEN=PQ2-NARWHAL-TUNDRA-5507`, лог:
  `Preloaded skill 'canary-skill'` — победил **проектный** скилл, плагинный молча затенён.
- `skills: probeplug:canary-skill` → `TOKEN=XQ7-ZEBRAFISH-KLONDIKE-9931`, лог:
  `Preloaded skill 'probeplug:canary-skill'` — префикс снимает двусмысленность.

**Что предзагружается.** Агент с `skills: adw:testing-unit` спрошен, есть ли в его контексте тела
топик-файлов темы или только роутер, с определённым отрицательным ответом. Ответ: `ROUTER-ONLY`.
То есть инжектится **только `SKILL.md`**, топик-файлы рядом — нет.

**Вывод: ЗАМЕРЕНО.** Работают обе формы — `plugin:skill` и короткая `skill`; форма со слэшем
`/plugin:skill` не работает. Неверная форма — **тихое игнорирование**, агент стартует, сигнал только
в дебаг-логе. Короткая форма разрешается в пользу проектного/пользовательского скилла при совпадении
имён, `plugin:skill` — всегда в плагинный. Предзагружается только `SKILL.md` темы.

**Оговорка, важная для B02: `adw` как плагин на этой машине не установлен.**
`~/.claude/plugins/installed_plugins.json` содержит `frontend-design`, `superpowers`, `code-review`,
`pyright-lsp` — и всё. Скиллы `adw` попадают в текущую сессию через симлинк
`.claude/skills -> ../plugins/adw/skills`, то есть под **короткими** именами как проектные. Замер
выше сделан с `--plugin-dir …/plugins/adw`, где они действительно `adw:*`. Отсюда: в сессии, где
плагин не установлен и не подан `--plugin-dir`, строка `skills: adw:testing-unit` не разрешится —
и промолчит по механизму, замеренному выше. **НЕ ПРОВЕРЕНО:** как это выглядит после настоящей
установки из маркетплейса (`/plugin marketplace add` + `/plugin install`) — репетиция установки это
задача B07.

---

## Вопрос 2. Лишает ли `tools:` без `Write`/`Edit` возможности записи

**Что сделал.** Плагинный агент `nowrite`, `tools: Read, Bash, Glob, Grep`, задача — создать файл с
текстом `BASH-WROTE-IT`, перебрав пять маршрутов и не останавливаясь на первом отказе: `printf >`,
heredoc, `tee`, `sed -i`, `python3 -c open(...,'w')`. Дочерняя сессия
`--tools default --allowedTools "Bash Read Glob Grep"`. Атрибуция — по `parent_tool_use_id` в
`stream-json`: все `Bash` — от сабагента, не от родителя.

**Что наблюдал.** Файл создан, `cat` → `BASH-WROTE-IT`. Тул-коллы сабагента (дословно из потока):

```
TOOL_USE:Bash {"command":"printf 'BASH-WROTE-IT\n' > <path> 2>&1; echo \"EXIT=$?\"" }
TOOL_RESULT: EXIT=0
TOOL_USE:Bash {"command":"cat <path>; echo \"EXIT=$?\"" }
TOOL_RESULT: BASH-WROTE-IT\nEXIT=0
TOOL_USE:Bash {"command":"... heredoc ... tee ... sed -i ... python3 ..."}
TOOL_RESULT: ROUTE2_EXIT=0\nBASH-WROTE-IT\nROUTE3_EXIT=0\nROUTE4_EXIT=0\nROUTE5_EXIT=0\nBASH-WROTE-IT
```

Ответ агента: «All five routes succeeded».

**Контрольный вариант без `Bash`.** Тот же агент с `tools: Read, Glob, Grep`. Ответ (дословно,
фрагмент):

```
Tools I was offered in my system prompt: Read, Glob, Grep. (No Write, no Edit, no Bash, no
Task/agent-launching tool.)
...
RESULT=NO-WRITE-PATH
```

Файла нет: `ls: …/nobash-out.txt: No such file or directory`.

**Есть и не связанное с `tools:` ограничение записи.** В дочерней сессии с
`--permission-mode manual` попытка записать **вне cwd** блокируется независимо от набора
инструментов:

```
RESULT=DENIED: Output redirection to '…/probe/out/pm-plug-none.txt' was blocked. For security,
Claude Code may only write to files in the allowed working directories for this session:
'…/probe/proj'.
```

**Вывод: ЗАМЕРЕНО.** Отсутствие `Write`/`Edit` **не** лишает записи: при наличии `Bash` прошли все
пять маршрутов. Набор без записи — только `Read, Glob, Grep` (тогда маршрута нет вообще, и агенту
недоступен даже инструмент дальнейшего диспатча). Это меняет формулировку в `WORKFLOW.md` §5 — см.
блок «ПРОТИВОРЕЧИТ КАНОНУ».

---

## Вопрос 3. `maxTurns` — что считается turn'ом и что видит родитель на потолке

**Что сделал.** Три плагинных агента с одинаковым телом («выполни восемь команд `echo STEP-n`,
каждую **отдельным** вызовом `Bash`, не объединять; только после восьмой ответь `DONE-ALL-EIGHT`») и
разным `maxTurns`: 1, 2, 3. Плюс контроль `turncapok`: `maxTurns: 5`, две команды и финальный ответ.

**Что наблюдал** (`tool_result`, который получил родитель, дословно):

| `maxTurns` | Сколько `Bash` реально прошло | Что вернулось родителю |
|---|---|---|
| 1 | 1 | `(Subagent completed but returned no output.)` + `<usage>… tool_uses: 1 …</usage>` |
| 2 | 2 | `(Subagent completed but returned no output.)` + `tool_uses: 2` |
| 3 | 3 | `I'll run these eight commands one at a time, in separate calls.` + `tool_uses: 3` |
| 5 (контроль, нужно 2) | 2 | `DONE-TWO` + `tool_uses: 2` |

Ни в одном случае в возврате нет слова об ограничении, кода ошибки или `stop_reason`. При
`maxTurns: 3` вернулся **преамбульный текст** агента — то есть частичный результат, выглядящий как
отчёт. Слово в возврате — `completed`.

Ближайший к сигналу след — только в дебаг-логе, и потолок в нём тоже не назван:

```
[INFO] [Stall] agent_completion agentId=a60e4598f32acbbdd agentType=probeplug:turncap2
   exitPath=completed durationMs=6883 turns=2 finalStopReason=tool_use ...
```

Для сравнения, агент, завершившийся сам (проба про хуки, тот же формат строки):
`exitPath=completed … turns=2 finalStopReason=end_turn`. Различие `tool_use` против `end_turn` —
единственный найденный признак, и он живёт в логе, а не в возврате.

**Что считается turn'ом.** Один turn = одна инференция агента. `maxTurns: 3` дал три инференции с
тул-коллами и **не дал четвёртой**, в которой был бы финальный текст; отсюда «no output». Контроль
`maxTurns: 5` при двух тул-коллах прошёл: 2 инференции с `Bash` + 1 с текстом = 3 ≤ 5.
Следствие для калибровки (`WORKFLOW.md` §11 п.3): бюджет = **ожидаемое число тул-коллов + 1 на
финальный отчёт**; при попадании в потолок отчёта не будет вовсе.

**Вывод: ЗАМЕРЕНО.** Turn — инференция агента, не тул-колл и не сообщение пользователя. На потолке
родитель получает либо `(Subagent completed but returned no output.)`, либо случайный ранний текст
агента; **ошибки нет, и из возврата не следует, что сработал потолок**. Опереться на `maxTurns` как
на замену ESCALATE-механике можно только в смысле «агент не будет крутиться бесконечно»; как на
сигнал «упёрся в потолок» — нельзя, сигнала нет.

---

## Вопрос 4. Игнорируют ли плагинные агенты `permissionMode` / `hooks` / `mcpServers`

**Что сделал.** (а) Один и тот же агент — `tools: Bash`, задача «выполни ровно одну команду
`printf 'PM-WROTE\n' > <путь вне cwd>` и доложи `RESULT=OK` или дословный отказ» — положен в двух
экземплярах: в плагин и в `.claude/agents/` проекта; третий экземпляр — плагинный, без поля
`permissionMode`. Все три — в дочерних сессиях с `--permission-mode manual`.
(б) Агент с `hooks: PreToolUse` (matcher `Bash`), команда хука дописывает маркер-файл — тоже в двух
экземплярах, плагинный и проектный. (в) Агент, ставящий все три поля разом, — для проверки
загрузчика.

**Что наблюдал.**

| Агент | Где | `permissionMode` | Итог |
|---|---|---|---|
| `pmode-plug-none` | плагин | нет | `RESULT=DENIED: Output redirection … was blocked …`, файла нет |
| `pmode-plug-bypass` | плагин | `bypassPermissions` | `RESULT=DENIED: Output redirection … was blocked …`, файла нет |
| `pmode-proj-bypass` | `.claude/agents/` | `bypassPermissions` | `RESULT=OK`, файл создан (9 B) вне cwd |

Тройка различающая: тело, флаги сессии и цель записи одинаковы, отличается только слой — плагинный
экземпляр поле проигнорировал, проектный поле применил.

Хуки: маркер-файла нет ни в одном случае, но причины в логе **разные**:

```
[WARN] Plugin agent file …/probeplug/agents/hook-plug.md sets hooks, which is ignored for plugin
   agents. Use .claude/agents/ for this level of control.
```

```
[ERROR] Skipping frontmatter hooks for agent 'hook-proj': the folder its definition file came from
   is not trusted (source: projectSettings, trust key: "…/probe/proj"). Run Claude Code there once
   and accept the trust dialog, or set projects["…"].hasTrustDialogAccepted: true in
   /Users/egorvorobyev/.claude.json.
```

То есть плагинный случай — прямое подтверждение игнора; проектный контроль **неинформативен**: хук
не сработал из-за недоверенного скратчпад-каталога, а не из-за слоя.

Загрузчик пишет по строке на каждое поле, при старте, до всякого диспатча:

```
[WARN] Plugin agent file …/agents/warn-plug.md sets permissionMode, which is ignored for plugin agents. …
[WARN] Plugin agent file …/agents/warn-plug.md sets hooks, which is ignored for plugin agents. …
[WARN] Plugin agent file …/agents/warn-plug.md sets mcpServers, which is ignored for plugin agents. …
```

**Вывод.**

- `permissionMode` у плагинного агента: **ЗАМЕРЕНО** — игнорируется (поведенчески + строка загрузчика).
- `hooks` у плагинного агента: **ЗАМЕРЕНО** — игнорируется (строка загрузчика; поведенчески — хук не
  сработал, но проектный контроль был испорчен недоверенным каталогом).
- `mcpServers` у плагинного агента: **ЗАМЕРЕНО на уровне загрузчика** (строка WARN выше);
  поведенческой пробы не было — MCP-сервер потребовал бы своего скрипта, а бюджет скриптов ноль.
- **ИЗ ДОКОВ**, `code.claude.com/docs/en/sub-agents`, «Choose the subagent scope»: «For security
  reasons, plugin subagents don't support the `hooks`, `mcpServers`, or `permissionMode` frontmatter
  fields. These fields are ignored when loading agents from a plugin. If you need them, copy the
  agent file into `.claude/agents/` or `~/.claude/agents/`.»

---

## Вопрос 5. Горячая перезагрузка определений и оговорка про новый каталог

**Что сделал.** Одна **живая** дочерняя сессия на два хода: `claude -p --input-format stream-json
--output-format stream-json --verbose`, stdin — FIFO, который держит открытым фоновый процесс;
ходы отправляются дописыванием JSON-строки в FIFO, правки файлов делаются **между** ходами, процесс
всё это время один и тот же. Три подпробы в одной сессии:

- `proj2/.claude/agents/alpha.md` — существовал на старте, отвечает `MARKER-ALPHA`;
- `probeplug2/agents/pdelta.md` — плагинный агент (через `--plugin-dir`), отвечает `MARKER-PALPHA`;
- `gamma` — файла нет; каталог `proj2/.claude/agents/` **существовал** на старте.

Между ходами: `alpha.md` → `MARKER-BETA`, `pdelta.md` → `MARKER-PBETA`, создан `gamma.md` →
`MARKER-GAMMA`. Пауза перед вторым ходом ≈8 с.

**Что наблюдал.** Ход 1 (финальный текст родителя, дословно):

```
ALPHA=MARKER-ALPHA
PDELTA=MARKER-PALPHA
GAMMA=Agent type 'gamma' not found. Available agents: alpha, claude, Explore, general-purpose, Plan, probeplug2:pdelta, statusline-setup
```

Ход 2 в том же процессе:

```
ALPHA=MARKER-BETA
PDELTA=MARKER-PBETA
GAMMA=MARKER-GAMMA
```

**Новый каталог.** Вторая живая сессия в `proj3/`, где `.claude/` есть, а `.claude/agents/` **нет**.
Ход 1: `ZETA=Agent type 'zeta' not found. Available agents: claude, Explore, general-purpose, Plan,
statusline-setup`. Затем создан `proj3/.claude/agents/zeta.md` (первый файл в новом каталоге), пауза
≈30 с суммарно, ход 2 в том же процессе:

```
ZETA=Agent type 'zeta' not found. Available agents: claude, Explore, general-purpose, Plan, statusline-setup
```

Контроль: свежий процесс `claude -p` в том же `proj3` тут же нашёл агента — `MARKER-ZETA`. Значит
дело в watcher'е, а не в файле.

**Вывод: ЗАМЕРЕНО.** Правка существующего файла агента подхватывается без рестарта — и для
`.claude/agents/`, и для `agents/` плагина, поданного через `--plugin-dir`. Новый файл в **уже
существовавшем** каталоге тоже подхватывается. Первый файл в **новом** каталоге `agents/` — **нет**,
нужен рестарт; файл при этом валиден, что показал свежий процесс.

**ИЗ ДОКОВ** (то же, `code.claude.com/docs/en/sub-agents`): «The watcher covers only directories that
existed when the session started, so after creating a scope's first agent file in a new `agents`
directory, restart to load it.» И вторая оговорка, которую не проверял, — **НЕ ПРОВЕРЕНО**:
«Sessions started with `--disable-slash-commands` don't watch these directories at all.»

---

## Побочное, что попало в замер (пригодится B02/B05/B07)

Всё ниже — ЗАМЕРЕНО в тех же прогонах.

1. **Инструмент диспатча в потоке называется `Agent`**, не `Task`; при этом `--tools "Task"`
   принимается как имя. Аргумент — `subagent_type`.
2. **Плагинный агент адресуется `plugin:name`.** Родитель вызывал `subagent_type:
   "probeplug:canary-ns"`; проектный агент — короткое `alpha`. Список доступных типов отдаётся
   в ошибке: `Agent type 'gamma' not found. Available agents: alpha, claude, Explore,
   general-purpose, Plan, probeplug2:pdelta, statusline-setup`.
3. **Ноль разрешившихся инструментов = отказ запуска, а не тихий пустой агент.** При
   `--tools "Task"` у сессии агент с `tools: Read, Bash, Glob, Grep` не стартовал, родителю пришло:
   `Agent 'probeplug:nowrite' would be spawned with zero tools — refusing. Its tools list resolved
   to nothing: unrecognized [Read, Bash, Glob, Grep]. Fix the agent's tools frontmatter or pass a
   different subagent_type.` Это `tool_result`, а не пересказ модели. Следствие: набор `tools:`
   агента **пересекается** с набором, доступным сессии.
4. **Инструмент `Skill` в рантайме берёт префиксную форму.** Агент с `tools: Glob, Skill` вызвал
   `Skill {"skill":"probeplug:canary-skill","args":"…"}` → `Launching skill: probeplug:canary-skill`
   и получил тело скилла.
5. **Без `Skill` в `tools:` рантайм-инвокации нет.** Агент с `tools: Glob` на прямое требование
   позвать скилл ответил: `NO-SKILL-TOOL` и «Tools offered (verbatim): - `Glob`».
6. **Предзагрузка `skills:` даёт только `SKILL.md`** (см. вопрос 1, ответ `ROUTER-ONLY`).
   Цена: `subagent_tokens` 6810 против 1996 у контроля на одном `adw:testing-unit`, то есть
   ≈4,8 тыс. токенов на тему.
7. **Запись вне cwd блокируется отдельно от `tools:`** (см. вопрос 2). Для `isolation: worktree`
   это стоит держать в голове, но **НЕ ПРОВЕРЕНО** — `isolation` не замерялся.
8. **ИЗ ДОКОВ, не проверено, но упирается прямо в B02:** «You can't preload skills that set
   `disable-model-invocation: true`, since preloading draws from the same set of skills Claude can
   invoke.» Ни один скилл в `plugins/adw/skills/` этого поля сейчас не ставит (`grep` по каталогу —
   ноль совпадений), так что сегодня это не мешает; станет ловушкой, если поле появится.

---

## ПРОТИВОРЕЧИТ КАНОНУ

Канон не правил. Ниже — что именно расходится с замером; решение за человеком.

**1. `WORKFLOW.md` §5, строка `test-review`, колонка «Не может»:** «ничего не пишет вообще (нет
`Write`/`Edit`)».

Замерено (вопрос 2): отсутствие `Write`/`Edit` записи не лишает — агент с `tools: Read, Bash, Glob,
Grep` создал файл пятью маршрутами через `Bash`. Единственный замеренный набор без маршрута записи —
`Read, Glob, Grep`, то есть **без `Bash`**. При этом та же §5 требует от `test-review` ответить
«тесты запускаются?», а это `Bash`. Утверждение «ничего не пишет вообще» и скобка «(нет
`Write`/`Edit`)» как его причина — не подтверждаются: механизм не даёт заявленного свойства.
Замечу, что §5 сама формулирует правильный принцип на два абзаца ниже — «prevention здесь и
невозможен… обходить нечего — есть только diff».

**2. `WORKFLOW.md` §1, литмус мягкой деградации:** «`skills:` в агенте пропал → скилл подгружается
авто-инвокацией по `description`. Мягко.»

Замерено (побочное 5): у агента, чей `tools:` не содержит `Skill`, рантайм-инвокации нет вообще —
`NO-SKILL-TOOL`. Наборы `tools` из §5 (`Read, Bash, Glob, Grep` и аналоги) `Skill` не содержат.
Значит заявленная мягкая деградация существует **только при условии**, что `Skill` в списке (или
что `tools` вообще не указан и наследуется всё). Дополнительно (вопрос 1): при неверном имени в
`skills:` пользователю не сообщается ничего — только `[WARN]` в дебаг-логе, — так что «пропало»
выглядит как «работает».

**3. Не противоречие, а факт, которого у канона не было — на решение человеку.** §5 берёт
`maxTurns` «как потолок итераций», §11 п.3 честно говорит, что значение не откалибровано, а §1
разбирает только *исчезновение* фичи («человек сам видит, что агент крутится»). Замерено (вопрос 3):
при *срабатывании* потолка родитель получает `(Subagent completed but returned no output.)` или
случайный ранний текст, со словом `completed` и без признака потолка. Если применить к этому
критерий красной линии 7 в её собственной формулировке («сессия встала намертво… не деградация, а
отказ»), молчаливая обрезка с правдоподобным «completed» — тоже не мягкая деградация. Что с этим
делать — вопрос канона, не мой.
