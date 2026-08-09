# PLATFORM.md — замеренные свойства платформы

**Версия: `claude --version` → `2.1.220 (Claude Code)`. macOS Darwin 25.3.0.**
Факт о платформе без версии — факт с неизвестным сроком годности. При смене минора перепроверять.
Даты у файла нет: её несёт каждый раздел отдельно.

Три пометки, других нет:

- **ЗАМЕРЕНО** — команда запущена, вывод наблюдён и приведён; сюда же — наблюдение на настоящей
  работе с приведённым выводом, а не только запущенная команда. Вывод — дословный; агрегат вместо
  дословного вывода допустим, но **помечается как агрегат**.
- **ИЗ ДОКОВ** — так написано в `code.claude.com/docs` на дату, которую называет сам раздел,
  эксперимента не было; цитата и страница даны.
- **НЕ ПРОВЕРЕНО** — установить не удалось. Это законченный ответ.

---

## Стенд

**Дата: 2026-07-29.**

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

**Дата: 2026-07-29.**

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

**Дата: 2026-07-29.**

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

**Дата: 2026-07-29.**

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

**Дата: 2026-07-29.**

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

**Дата: 2026-07-29.**

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

## Вопрос 6. Принимается ли `skills:` YAML-блок-списком, и предзагружаются ли **все** элементы

Доп-замер по отказу warden'а на B02. **Дата: 2026-07-29. Версия: `2.1.220 (Claude Code)`.**

**Стенд — отдельный, новый.** `<scratch>/probe2/blockplug/` — выбрасываемый плагин
(`"name": "blockplug"`) с **девятью** скиллами `s1`…`s9`. У каждого в теле свой маркер, которого нет
нигде больше: `A1-QUOKKA-MARLIN-4417`, `B2-PANGOLIN-BASALT-8062`, `C3-NARWHAL-CINDER-1539`,
`D4-OCELOT-GRANITE-7284`, `E5-TAPIR-ZEPHYR-3956`, `F6-CARIBOU-OBSIDIAN-6103`,
`G7-MEERKAT-SALTWORT-2870`, `H8-AXOLOTL-FLINTLOCK-9425`, `I9-CAPYBARA-TUNDRA-5731`.
Шесть пробных агентов различаются **только** формой строки `skills:`; тело промпта у всех дословно
одно: «выведи по строке `MARKER=<маркер дословно>` на **каждый** маркер, который есть в контексте,
затем `COUNT=<сколько строк напечатал>`; если маркеров нет — `MARKER=NONE`, `COUNT=0`; инструментами
не пользоваться, маркер не угадывать». У всех `tools: Glob` — прочитать файлы нечем.
Диспатч каждого — отдельной дочерней сессией:
`claude -p "…" --plugin-dir <probe2>/blockplug --output-format stream-json --verbose
--forward-subagent-text --debug-file <out>/<name>.log --allowedTools "Task"`.

**Почему проба различает «загрузился только первый» и «загрузились все».** Дискриминатор — свой
маркер на каждый элемент, и агент обязан перечислить все, что видит. «Загрузился первый» дало бы
одну строку `MARKER=`, «загрузились все» — девять; снаружи это разные наблюдения, а не одно.
Плюс два независимых признака: счётчик `subagent_tokens` и строки `Preloaded skill` в дебаг-логе.

**Что наблюдал** (`tool_result` родителя, дословно):

| `skills:` | Форма | Ответ сабагента | `COUNT` | `subagent_tokens` | `Preloaded skill` в логе |
|---|---|---|---|---|---|
| — (поля нет, контроль) | — | `MARKER=NONE` | 0 | 2004 | нет ни одной |
| блок-список, 1 элемент (`- blockplug:s1`) | блок | `MARKER=A1-QUOKKA-MARLIN-4417` | 1 | 2197 | 1 |
| блок-список, 3 элемента (`s1 s2 s3`) | блок | все три маркера, по строке | 3 | 2599 | 3 |
| блок-список, **9** элементов (`s1`…`s9`) | блок | **все девять маркеров, по строке, в порядке списка** | 9 | 3834 | 9 |
| `skills: blockplug:s1, blockplug:s2` | инлайн через запятую | оба маркера | 2 | 2399 | 2 |
| `skills: [blockplug:s1, blockplug:s2]` | flow-последовательность | оба маркера | 2 | 2399 | 2 |

`tool_uses: 0` у всех шести. Счётчик монотонен и линеен: контроль 2004, далее +≈195…205 токенов на
скилл (9 скиллов → 3834, то есть +1830 ≈ 203 × 9) — второй признак, что загрузились все девять,
а не первый.

Дебаг-лог девятиэлементного случая, дословно (даты и уровни срезаны, порядок сохранён):

```
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s1'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s2'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s3'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s4'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s5'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s6'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s7'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s8'
[Agent: blockplug:blk9] Preloaded skill 'blockplug:s9'
```

**Тот же замер на настоящем списке из `implementer.md`, а не на игрушечном.** Пробный агент в
`blockplug`, `tools: Glob`, `skills:` — **дословно скопированный** девятиэлементный блок-список
`implementer.md` (`adw:architecture`, `adw:python-style`, `adw:conventions`, `adw:domain-model`,
`adw:domain-ports`, `adw:application`, `adw:infra-persistence`, `adw:infra-integration`,
`adw:restapi`). Обе плагин-директории поданы разом:
`--plugin-dir <probe2>/blockplug --plugin-dir …/agentic-development-workflow/plugins/adw`.
Спрошен H1-заголовок **каждого** тела в контексте. Ответ (дословно):

```
BODY=Architecture — layers, packages, imports
BODY=Python style — typing & logging
BODY=Conventions (Python / FastAPI house style)
BODY=Domain model — entities, value objects, enums, filters, exceptions
BODY=Domain ports — protocols & services
BODY=Application — CQRS handlers & sanctioned try/except
BODY=Infrastructure — persistence
BODY=Infrastructure — integration (adapters, settings, DI)
BODY=REST API
COUNT=9
```

Девять из девяти, в порядке списка, и все девять совпадают дословно с выводом
`awk '/^# /{print;exit}'` по соответствующим `SKILL.md`. Контроль — тот же агент и тот же промпт без
поля `skills:` — ответил `BODY=NONE`, `COUNT=0`. `subagent_tokens`: **43749** против **2027** у
контроля; `tool_uses: 0` у обоих; в логе девять строк `Preloaded skill 'adw:…'`, у контроля ни одной.

**Методическая оговорка, из-за которой первая попытка была неинформативной.** Первый вариант промпта
просил на каждое тело первый пункт его раздела *Hard stops*. Агент выдал 13 строк — по **артефактам**
пяти первых тем — и ничего по `application`, `infra-persistence`, `infra-integration`, `restapi`.
Причина не в загрузке: у роутеров этих четырёх тем раздела `## Hard stops` в `SKILL.md` попросту нет
(`grep -n '^#'` даёт только H1, `## When to use vs. neighbours` и по одному тематическому разделу).
То есть проба, различающая «загрузилось» и «нет» по признаку, которого в части тел нет, даёт ложное
«нет». Заменено на H1, который есть у всех, — и только тогда результат стал различающим.

**Поправка к записи вопроса 1 выше.** Таблица вопроса 1 записана в компактной инлайн-нотации
(`probeplug:canary-skill`), но **на диске все агенты того стенда были ровно блок-списком из одного
элемента**: `grep -A1 '^skills:'` по `probe/probeplug/agents/` даёт `skills:` + `  - <имя>` у
`canary-ns`, `canary-bare`, `canary-slash`, `canary-bogus`, `adw-ns`. Mtime файла (`14:13:59`)
раньше mtime вывода прогона (`14:20:41`), то есть после запуска файлы не правились. Значит вопрос 1
уже был замерен блок-формой, а не скаляром; расхождение было в оформлении записи, не в замере.

**Вывод: ЗАМЕРЕНО.** `skills:` принимает блок-список — и из одного элемента, и из трёх, и из девяти;
предзагружаются **все** элементы, а не первый, что подтверждено тремя независимыми признаками
(перечисление маркеров агентом, счётчик токенов, `Preloaded skill` по строке на элемент). Инлайн
через запятую (`skills: a, b`) и flow-форма (`skills: [a, b]`) тоже работают и дают тот же результат
(2399 токенов и две строки лога у обеих). Потолка на девяти нет: настоящий девятиэлементный список
`implementer.md` загрузился целиком. **НЕ ПРОВЕРЕНО:** есть ли потолок **выше** девяти — больше
девяти элементов не пробовал; максимум в `plugins/adw/agents/` сегодня девять.

**Цена, попутно из того же прогона:** девятиэлементный `skills:` у `implementer.md` — это
**≈41,7 тыс. токенов** контекста на старте (43749 против 2027 у контроля), то есть ≈4,6 тыс. на тему,
что согласуется с ≈4,8 тыс. на одном `adw:testing-unit` из вопроса 1.

---

## Побочное, что попало в замер (пригодится B02/B05/B07)

**Дата: 2026-07-29.**

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
9. **Не из прогонов выше — наблюдение 2026-08-05, класс ЗАМЕРЕНО** (кладётся по решению человека
   2026-08-05, «раунд 6: платформа и установка» → F-195; версии в записи нет). В auto-режиме разрешений
   доступность инструмента у субагента зависит ещё и от доступности **отдельной модели-классификатора**,
   и её падение приходит агенту как **отказ в разрешении**, а не как сбой платформы. Дословно, из
   отчёта диспатча `adw:evaluator a3087ea7`:

   ```
   DENIED Bash — kind `automode-unavailable` @ 2026-08-05T14:51:29.666Z
   reason: claude-sonnet-5[1m] is temporarily unavailable, so auto mode cannot determine the safety of
   Bash right now. Wait briefly and then try this action again.
   ```

   Читателю отчёта такой отказ выглядит как заблокированный инструмент, то есть как сигнал о правах или
   о цикле, — а он ни о том, ни о другом, и повторная попытка спустя время его снимает. Агент в том
   прогоне работу продолжил и вердикт вынес: отказ пришёлся на последний шаг.

---

## ПРОТИВОРЕЧИТ КАНОНУ

**Дата: 2026-07-29.**

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

---

## §13. `claude plugin update` — замер главной сессии, 2026-07-30

B07 помечал обновление плагина как **НЕ ПРОВЕРЕНО**. Замерено при обновлении установки в `adw-probe`
с ревизии `6289827b402e` на `dfba3c4a8354`. Версия `2.1.220`.

**Вопрос: работает ли `claude plugin update`, и какое имя он принимает?**

Что сделал: три вызова подряд из каталога проекта, где плагин установлен со `scope: project`.

Что наблюдал, дословно:

```
$ claude plugin update adw
Checking for updates for plugin "adw" at user scope…
✘ Failed to update plugin "adw": Plugin "adw" not found

$ claude plugin update adw --scope project
Checking for updates for plugin "adw" at project scope…
✘ Failed to update plugin "adw": Plugin "adw" not found

$ claude plugin update adw@wntic-adw --scope project
Checking for updates for plugin "adw@wntic-adw" at project scope…
✔ Plugin "adw" updated from 6289827b402e to dfba3c4a8354 for scope project. Restart to apply changes.
```

**Вывод: ЗАМЕРЕНО.** Два факта, и оба ловушки.

1. **Без скоупа `update` идёт в user scope**, даже если cwd — проект с project-установкой. Ошибка при
   этом говорит «Plugin not found», а не «не найден в этом скоупе».
2. **`update` требует квалифицированное имя `<plugin>@<marketplace>`**, тогда как `uninstall` и
   `list` принимают короткое `adw`. То есть три подкоманды принимают имя по-разному, и неверная форма
   даёт то же «Plugin not found», что и настоящее отсутствие.

**Третий факт, подтверждающий F-25: `update` не убирает старую ревизию из кэша.** После обновления
`~/.claude/plugins/cache/wntic-adw/adw/` содержал оба каталога — `6289827b402e` и `dfba3c4a8354`. То
же делает `install` после `uninstall`. Значит накопление ревизий — поведение и обновления тоже, и
устаревшая копия несёт **непочиненные** файлы: сразу после обновления в кэше лежала версия
`test-review.md` с белым списком путей, снятым коммитом `8694762`.

**Четвёртый факт, замеренный позже: источник маркетплейса меняет смысл слова «обновить».** Кладётся по
решению человека 2026-08-05 (`plan/FINDINGS.md`, «раунд 6: платформа и установка» → F-159), источник —
F-159. **Класс: ЗАМЕРЕНО. Дата наблюдения: 2026-08-04.** Версии в записи наблюдения нет; файл в целом
пришпилен к `2.1.220`. Замер сделан не на `adw`, а на соседнем плагине
`agent-report@wntic-agent-report`, чей маркетплейс — **`source: github`** (`wntic/claude-agent-report`),
тогда как `wntic-adw` поставлен из директории. Дословно:

```bash
cd ~/Projects/claude-agent-report && git status -sb | head -1
# * main...origin/main [ahead 2]     ← 1.1.1 и 1.1.2 лежали только локально
git log --oneline @{u}..HEAD
# c1d2dee (1.1.2)   fb97db4 (1.1.1)
/usr/bin/python3 -c "…installed_plugins.json…"
# scope: user | version: 1.1.0 | sha: c5292440…  ← ровно то, на чём стоял origin/main
```

Третья команда в записи приведена сокращённо — это чтение полей `installed_plugins.json`; её вывод
дословен.

У плагина, поставленного из `github`, дерево и установка связаны **через remote**, а не напрямую:
установленный sha совпадал с `origin/main` до символа, поэтому `claude plugin update` не нашёл бы
ничего нового, сколько бы его ни звали. Лечение — `git push`, и только потом `update`. То есть «правка
в дереве» не значит «правка доступна», даже локально. Это уже стоило одного неверного диагноза: F-141
записала причину как «не установлено», а причина была «не запушено».

Два побочных факта того же замера:

- **Версия `1.1.1` не была установлена никогда.** Обновление прошло `1.1.0 → 1.1.2` одним шагом:
  в кэше версии выбираются по тому, что на remote, а не по тому, что лежало в дереве между пушами.
- **Устаревшие копии `update` не убирает — то же самое третий раз.** После обновления в кэше лежали все
  три каталога: `1.0.0`, `1.1.0` и `1.1.2`. Это ровно третий факт выше, воспроизведённый на плагине из
  другого маркетплейса и другого источника.

---

## Вопрос 7. Срабатывает ли авто-вызов скилла **внутри сабагента**, без поля `skills:`

Замер под решение о форме каталога скиллов. **Дата: 2026-07-30. Версия: `2.1.220 (Claude Code)`** —
та же, что у вопросов 1–6, значит результаты сравнимы.

**Стенд — отдельный, новый.** `<scratch>/probe7/probeplug/` — выбрасываемый плагин
(`"name": "probeplug"`) с одним скиллом `pelican-invoice-parser`. Его `description` описывает разбор
вымышленного формата: «Apply when parsing or describing a legacy fixed-width PELICAN invoice file —
the .pel format with 80-column records… Use whenever a task mentions a .pel file, a PELICAN invoice,
or fixed-width invoice records». В теле — токен `VT4-PELICAN-MERIDIAN-7742`, которого нет ни в одном
промпте. Три агента различаются **только** frontmatter'ом:

| Агент | `skills:` | `tools:` |
|---|---|---|
| `auto-skilltool` | нет | `Skill` |
| `auto-noskilltool` | нет | `Glob` |
| `preloaded` | `probeplug:pelican-invoice-parser` | `Glob` |

Промпт тела у всех трёх дословно один: ответить на задачу и закончить строкой
`TOKEN=<токен или UNKNOWN>`. Диспатч — дочерней сессией из пустого рабочего каталога:

```bash
claude -p "Dispatch the \`probeplug:<agent>\` subagent with exactly this task and nothing else:
\"<task>\" Do not attempt the task yourself. Do not invoke any skill yourself. Then report the
subagent's final line verbatim." --plugin-dir <probe7>/probeplug --permission-mode bypassPermissions
--output-format stream-json --verbose --forward-subagent-text --debug-file <out>/<tag>.debug
```

Задача — `Explain the record layout of a legacy PELICAN .pel fixed-width invoice file.`, и отдельным
прогоном не относящаяся к скиллу: `Explain in two sentences what a CSV file is.`

| # | Агент | Задача | Что сделал сабагент | Токен |
|---|---|---|---|---|
| 1 | `preloaded` | про PELICAN | `Glob` ×2 | **есть** |
| 2 | `auto-noskilltool` | про PELICAN | `Glob` ×6, нашёл файл, прочитать нечем | нет |
| 3 | `auto-skilltool` | про PELICAN | **сам вызвал `Skill(probeplug:pelican-invoice-parser)`** | **есть** |
| 4 | `auto-skilltool` | про CSV | ничего не вызвал | нет |

Собственный текст сабагента в прогоне 3, до вызова инструмента: «I'll use the skill built for this
format.» — затем `tool_use Skill skill=probeplug:pelican-invoice-parser`.

В прогоне 4 сабагент **сам сообщил**, что скилл ему доступен, и что он его не вызвал, посчитав
вопрос про CSV вне его области. То есть листинг скиллов в контексте сабагента **есть** и без поля
`skills:`.

**Контроль контаминации.** Родитель не вызывал `Skill` ни в одном из четырёх прогонов (0 вызовов,
посчитано по `stream-json`). Промпт диспатча токена не содержит:
`{"subagent_type": "probeplug:auto-skilltool", … "prompt": "Explain the record layout of a legacy
PELICAN .pel fixed-width invoice file."}`. Строка `Preloaded skill 'probeplug:pelican-invoice-parser'`
есть в дебаг-логе **только** прогона 1 — в прогоне 3 предзагрузки не было.

**Вывод: ЗАМЕРЕНО.** Авто-вызов по `description` внутри сабагента работает и без поля `skills:` —
сабагент видит листинг скиллов и вызывает нужный сам. Два условия:

1. **`Skill` обязан быть в `tools:`.** Без него пути к скиллу нет вообще (прогон 2): агент
   обнаружил файл `Glob`'ом и не смог его прочитать. Это же и есть точная форма F-04: мягкая
   деградация `skills:` держится только при `Skill` в `tools:`.
2. **Ложного срабатывания на неподходящей задаче нет** (прогон 4), то есть точность авто-вызова
   определяется качеством `description`, а не наличием поля.

**Следствие для дизайна.** Предзагрузка `skills:` — не единственный путь знания в роль, и её можно
менять на узкий `description` плюс `Skill` в `tools:`. Цена предзагрузки известна (вопрос 1: 6810
против 1996 токенов на `adw:testing-unit`) и платится на старте всегда; авто-вызов платит только за
те скиллы, которые роль реально применила, но переносит решение на модель.

---

## Вопрос 8. Душит ли `paths` авто-вызов, когда файла по совпадающему пути ещё нет

Замер под R01: поле `paths` предлагалось поставить 45 скиллам, а документация говорит, что оно
активирует скилл «only when working with files matching the patterns». Скиллы этого каталога
существуют, чтобы **создавать** новые файлы, — если поле требует существующего файла, оно задушит
ровно основной сценарий. **Дата: 2026-07-30. Версия: `2.1.220 (Claude Code)`.**

**Стенд.** `<scratch>/probe8/pathplug/` — выбрасываемый плагин с одним скиллом
`domain-entity-canary`, у которого `paths: src/**/domain/**` и маркер `ZR9-IGUANA-SALTFLAT-3308` в
теле. Агент `pathprobe`: **без** поля `skills:`, `tools: Skill, Glob`. Два рабочих каталога:
`proj-empty/` — в нём есть `src/myapp/`, но **ни одного** файла под `src/**/domain/**`;
`proj-has/` — в нём лежит `src/myapp/domain/bars/bar.py`.

| # | Каталог | Задача | Вызвал скилл | Маркер |
|---|---|---|---|---|
| 1 | `proj-empty` | создать **новый** `src/myapp/domain/foos/foo.py` | **да** | **есть** |
| 2 | `proj-has` | править **существующий** `src/myapp/domain/bars/bar.py` | **да** | **есть** |
| 3 | `proj-has` | создать `scripts/report.py` (путь не совпадает) | нет | нет |

Собственный текст сабагента в прогонах 1 и 2, до вызова инструмента: «I'll start by loading the house
form skill for domain entities.» — затем `tool_use Skill skill=pathplug:domain-entity-canary`.

**Вывод: ЗАМЕРЕНО.** `paths` **не** требует, чтобы файл существовал. Достаточно, что задача называет
путь, попадающий под глоб: в прогоне 1 совпадающих файлов в проекте не было вовсе, и скилл всё равно
сработал. Значит поле безопасно для скиллов, которые создают файлы.

**Граница этого замера, честно.** Прогон 3 **не различает** две причины отсутствия маркера: «`paths`
скрыл скилл из листинга» и «скилл был виден, но модель посчитала его неприменимым к
`scripts/report.py`». Для скилла про доменную сущность второе объяснение правдоподобно само по себе,
поэтому **точность** `paths` этим замером не доказана — доказано только отсутствие ложного отрицания
на новых файлах, а это и был асимметричный риск. Отдельный замер точности не делался: он требует
контроля без `paths` и вопроса сабагенту «какие скиллы тебе видны», и цена его выше пользы, пока
`paths` стоит только на скиллах, чьи глобы совпадают с их же областью.

**Подтверждено на настоящей нагрузке, 2026-07-31.** Замер выше синтетический — один канареечный скилл
в выбрасываемом плагине. Прогон change 003 в `adw-probe` дал то же на реальном каталоге: из 30 скиллов
24 несут `paths` (`src/**/domain/**`, `src/**/application/**`, `src/**/infrastructure/**`,
`src/**/restapi/**`, `tests/**`), и все 12 авто-вызовов прогона разрешились — включая случаи, где
артефакт в момент вызова ещё не существовал: `custom_short_code.py` был создан **после** вызова
`domain-model`. Отсутствие ложного отрицания на новых файлах воспроизвелось вне стенда.
Точность по-прежнему не доказана: ни один скилл не вызывался там, где его глоб не совпадает, но такой
задачи в прогоне и не было.

**Пометка по легенде (F-129, решение человека 2026-08-05): это агрегат, а не дословный вывод.** Строка
«все 12 авто-вызовов прогона разрешились» — счёт по прогону; сырого вывода за 2026-07-31 не
сохранилось, и перемер отвергнут решением как замер новой нагрузки, выданный за старую. Класс остаётся
**ЗАМЕРЕНО**: легенда такую форму допускает ровно при этой пометке, и без неё блок не удовлетворял
собственной легенде файла.

---

## Вопрос 9. Пере-разрешается ли `tools:` работающего диспатча, и закрывает ли этот список `Skill`

Замер по решению человека 2026-07-31 (F-60, «Шаг 4, проход первый» → «B7 — платформа»).
**Дата: 2026-08-01. Версия: `claude --version` → `2.1.220 (Claude Code)`. macOS Darwin 25.3.0.**

Предыдущая редакция этого раздела была заглушкой со статусом **НЕ ПРОВЕРЕНО** и планом эксперимента.
Эксперимент проведён; заглушка заменена. Её побочный вывод — «скиллы, созданные после старта сессии,
разрешились без рестарта» — **снят**, основание ниже, в разборе наблюдения.

**Стенд — отдельный, новый.** `<scratch>/probe9/toolplug/` — выбрасываемый плагин (`"name":
"toolplug"`) с двумя скиллами вымышленных форматов:

- `kestrel-ledger-parser` — `description` про разбор `.kes`, в теле: ширина записи **132 колонки**,
  три поля со смещениями 1-14 / 15-96 / 97-132 и маркер `HB6-KESTREL-TUNDRA-4417`;
- `osprey-manifest-parser` — то же для `.osp`: 64 колонки, два поля, маркер `QJ2-OSPREY-BASALT-8815`.

Ни один маркер не встречается ни в промпте родителя, ни в теле агентов, ни в рабочем каталоге.
Рабочий каталог `<scratch>/probe9/proj/` пуст. Диспатч — дочерней сессией:

```bash
claude -p "Dispatch the \`toolplug:<agent>\` subagent with exactly this task and nothing else:
\"Explain the record layout of a legacy KESTREL .kes fixed-width ledger file.\" Do not attempt the
task yourself. Do not invoke any skill yourself. Then report the subagent's final line verbatim."
--plugin-dir <probe9>/toolplug --permission-mode bypassPermissions --output-format stream-json
--verbose --forward-subagent-text --debug-file <out>/<tag>.debug
```

**Дискриминатор — по содержанию, и это несущее (F-28).** Агенту нигде не задан вопрос «есть ли у
тебя скилл» и нигде не сказано «если знания нет, скажи, что нет» — эта формулировка сама производит
«нет». Спрошена ширина записи, смещения полей и маркер, то есть текст, который существует только в
теле скилла. Второй, независимый от ответа агента признак — **факт вызова инструмента**: строка
`tool_use` с `name: "Skill"` в `stream-json` и строка `SkillTool returning N newMessages for skill
toolplug:<skill>` в дебаг-логе. Само-отчёты агентов о собственном наборе инструментов в этом замере
встречаются в изобилии и **ни один из них не использован как доказательство**.

**Контроль, без которого отрицательные прогоны ничего не стоят.** Агент `ctlwide` — тело промпта,
`description` и запрет читать файлы ровно те же, что у прогона 2, `tools:` отличается одним словом:

| контроль К1 | `tools: Read, Write, Edit, Bash, Glob, Grep, Skill`, поля `skills:` нет |
|---|---|

Собственный текст сабагента до вызова инструмента: «I'll invoke the skill that covers this format.» —
затем `tool_use Skill {"skill": "toolplug:kestrel-ledger-parser"}`, в дебаг-логе
`SkillTool returning 2 newMessages for skill toolplug:kestrel-ledger-parser`, финальная строка,
дословно из `tool_result` родителя:

```
TOKEN=HB6-KESTREL-TUNDRA-4417
```

Значит запрет «не читать файлы» авто-вызову не мешает, и `UNKNOWN` в прогонах ниже — не артефакт
формулировки задачи.

### Прогоны

| # | агент | `tools:` | `skills:` | вызов `Skill` в логе | финальная строка |
|---|---|---|---|---|---|
| К1 | `ctlwide` | широкий **+ `Skill`** | нет | **есть** | `TOKEN=HB6-KESTREL-TUNDRA-4417` |
| 1 | `narrow` | `Glob, Read` | нет | нет | `TOKEN=UNKNOWN` |
| 2 | `wide` | `Read, Write, Edit, Bash, Glob, Grep` | нет | нет | `TOKEN=UNKNOWN` |
| 3 | `midedit` | тот же, `+ Skill` правкой **в середине диспатча** | нет | нет | `TOKEN=UNKNOWN` |
| 4 | `notools` | **поле опущено** | нет | **есть** | `TOKEN=HB6-KESTREL-TUNDRA-4417` |
| 5 | `wideghost` | `Read, Write, Edit, Bash, Glob, Grep` | несуществующее имя | нет | `TOKEN=UNKNOWN` |
| 6 | `wideskills` | `Read, Write, Edit, Bash, Glob, Grep` | реальное имя, предзагрузилось | нет | `TOKEN=UNKNOWN` |
| К2 | `midedit` после правки, **свежая сессия** | широкий **+ `Skill`** | нет | **есть** | `TOKEN=HB6-KESTREL-TUNDRA-4417` |

Прогоны 5 и 6 таблицей задачи не предусматривались; они добавлены потому, что после прогонов 2 и 3
оба объяснения F-60 оказались опровергнуты, и поле `skills:` осталось единственным неисключённым
кандидатом (у агента прогона 003 оно было непустым). Прогон 6 спрашивает про **другой** формат
(`.osp`), чем тот, что предзагружен, — иначе предзагрузка сама даёт токен и ничего не различает.

**Прогон 1 — `tools: Glob, Read`.** Ноль вызовов инструментов, `grep -ic kestrel narrow.debug` → `0`.
Файлы агент не читал, хотя `Read` у него был, — то есть запрет соблюдён и токен неоткуда взять,
кроме скилла. **Вывод: ЗАМЕРЕНО.** Воспроизводит прогон 2 вопроса 7 дискриминатором по содержанию:
без `Skill` в узком `tools:` пути к скиллу нет.

**Прогон 2 — широкий список без `Skill`, тот самый, ради которого замер затевался.** Список дословно
тот, что нёс `test-author` до R03: `Read, Write, Edit, Bash, Glob, Grep`. Ноль вызовов инструментов,
`grep -ic kestrel wide.debug` → `0`. **Вывод: ЗАМЕРЕНО.** Широкий `tools:` закрывает `Skill` ровно
так же, как узкий. Альтернатива F-60 («`Skill` у агента с широким списком не был закрыт полем вовсе,
и тогда R03 правил три роли зря») **опровергнута**: правка R03 была необходима.

**Прогон 3 — правка frontmatter в середине диспатча.** Первая попытка **аннулирована**: тело агента
велело ждать через `sleep 100`, и песочница вернула
`<tool_use_error>Blocked: standalone sleep 100…</tool_use_error>` — паузы не случилось, правка и шаг 2
разошлись во времени неконтролируемо. Прогон переделан на файловый шлюз, который заодно делает
порядок событий детерминированным, а не вероятностным: шаг 1 агента —
`until [ -f <out>/go.flag ]; do sleep 2; done; echo RELEASED`, и шлюз открывает замеряющий, а не часы.

Хронология переделанного прогона, по `date -u` замеряющего:

| UTC | событие |
|---|---|
| 15:03:02 | старт дочерней сессии |
| 15:03:13 | в `stream-json` появился `tool_use Bash` со шлюзовой командой — диспатч встал в ожидание |
| 15:03:33 | `tools:` в `midedit.md` переписан на `Read, Write, Edit, Bash, Glob, Grep, Skill`, проверено `grep` |
| 15:03:49 | `touch <out>/go.flag` |
| 15:04:09 | диспатч завершился |

`tool_result` шлюза — `"RELEASED"`, то есть шаг 2 исполнялся после правки. Вызова `Skill` в потоке
нет, `grep -i kestrel midedit2.debug` — пусто, финальная строка `TOKEN=UNKNOWN`.
**Вывод: ЗАМЕРЕНО.** Набор инструментов работающего диспатча **не** пере-разрешается по ходу.
Объяснение 1 из F-60 опровергнуто.

**Контроль К2 к прогону 3, обязательный:** тот же файл `midedit.md` после правки, свежая сессия,
шлюз уже открыт → `tool_use Skill {"skill": "toolplug:kestrel-ledger-parser"}`,
`SkillTool returning 2 newMessages…`, `TOKEN=HB6-KESTREL-TUNDRA-4417`. Значит отрицательный результат
прогона 3 — про момент разрешения, а не про сломанный файл.

**Побочно у прогона 3, и это отдельная граница.** Тем же приёмом снят второй диспатч того же агента
**в том же ходу той же сессии**, после правки. Чтобы отличить «набор инструментов заморожен» от
«файл определения вообще не перечитан», в тело агента добавлен сторож: «Begin your reply with the
line `GEN=ONE`», и правка меняла его на `GEN=TWO` вместе с `tools:`. Второй диспатч, выданный
родителем через ~40 с после правки, начал ответ строкой `GEN=ONE` — **старым** телом — и `Skill` не
вызвал. **Вывод: ЗАМЕРЕНО.** Внутри одного хода определение агента, уже загруженное сессией, не
перечитывается; разделить «tools заморожены» и «файл не перечитан» этот прогон не позволяет и не
претендует. Вопросу 5 это не противоречит: там правка подхватывалась **между ходами** живой сессии
(паузы ≈8 с и ≈30 с), здесь — внутри одного хода.

**Прогон 4 — `tools:` не указан вовсе.** Собственный текст сабагента: «There's a skill for exactly
this format. Let me invoke it.» — затем `tool_use Skill`, в дебаг-логе
`SkillTool returning 3 newMessages for skill toolplug:kestrel-ledger-parser`,
`TOKEN=HB6-KESTREL-TUNDRA-4417`. **Вывод: ЗАМЕРЕНО** — но замерено ровно одно: при опущенном
`tools:` инструмент `Skill` у сабагента есть. Утверждение доков шире («inherits every tool available
to subagents»), и полнота наследования **НЕ ПРОВЕРЕНО**: ни один другой инструмент этим прогоном не
проверялся.

**Прогон 5 — широкий `tools:` плюс `skills:` с несуществующим именем.** Воспроизводит форму
frontmatter'а `test-author` на прогоне 003, где две из трёх записей `skills:` не разрешались.
В дебаг-логе — предупреждение, дословно:

```
[WARN] [Agent: toolplug:wideghost] Warning: Skill 'toolplug:definitely-no-such-skill-9931'
specified in frontmatter was not found
```

Ноль вызовов инструментов, `TOKEN=UNKNOWN`. **Вывод: ЗАМЕРЕНО.** Наличие поля `skills:` инструмент
`Skill` не выдаёт. Попутно это второй замер тихости неверного имени (первый — вопрос 1): наружу не
сообщается ничего, `[WARN]` виден только в дебаг-логе.

**Прогон 6 — широкий `tools:` плюс `skills:` с именем, которое разрешается.** В дебаг-логе
`[DEBUG] [Agent: toolplug:wideskills] Preloaded skill 'toolplug:kestrel-ledger-parser'` — предзагрузка
состоялась, и сабагент её содержимое процитировал («that spec documents the KESTREL `.kes` ledger
format, not OSPREY `.osp`», с верной геометрией 132 / 1-14 / 15-96 / 97-132). Спрошен он был про
`.osp`, скилл которого не предзагружен. Ноль вызовов инструментов, `TOKEN=UNKNOWN`.
**Вывод: ЗАМЕРЕНО.** Разрешившееся поле `skills:` даёт содержимое названных скиллов и **не** даёт
пути к остальным: без `Skill` в `tools:` соседний скилл недостижим.

### Свод по вопросу 9

**ЗАМЕРЕНО.** Набор инструментов сабагента разрешается один раз, при запуске диспатча, и по ходу
диспатча не меняется. `Skill` доступен ровно в двух случаях: он назван в `tools:` — или `tools:`
опущено целиком. Ни ширина списка, ни наличие поля `skills:`, ни успешная предзагрузка второго пути
не открывают.

Следствие для решения по F-04: оговорка «вопрос 7 мерил узкий список» **снята**. Формулировку решения
уточнять не нужно — `Skill` в `tools:` у четырёх ролей необходим, и R03 правил все четыре роли по делу.

### Разбор наблюдения, из которого вырос этот вопрос (F-60)

Оба объяснения, между которыми F-60 просила выбрать, опровергнуты прогонами 2 и 3; третье
(поле `skills:`) — прогонами 5 и 6. Раз ни одно не проходит, проверено само наблюдение. Оно
**не воспроизводится, потому что его хронология сравнивает UTC с локальным временем**.

Что сделал — чтение хранимых артефактов, без запуска:

```bash
git show -s --format='%cI  %s' c8b7fc0
python3 -c "…"   # разбор ~/.claude/projects/-Users-egorvorobyev-Projects-adw-probe/*.jsonl
stat -f '%Sm' -t '%Y-%m-%dT%H:%M:%S%z' ~/.claude/plugins/cache/wntic-adw/adw/*/agents/test-author.md
```

Что наблюдал, дословно:

```
c8b7fc0  2026-07-30T17:27:47+05:00  feat(R03): the four roles get `Skill`, …
attachment at 2026-07-30T17:13:06.576Z skillCount= 52 isInitial= True
2026-07-30T17:26:13.751Z adw:test-author Red phase for change 003
```

Сессия 003 — `f577c68f-…jsonl`, ветка `change/003`, интервал `2026-07-30T17:13:06.576Z` →
`2026-07-30T18:28:08.758Z`. Времена в таблице F-60 (17:13:06, 17:26:16) — это **UTC** из транскрипта;
время R03 (17:27:47) — **локальное +05:00** из `git log`, то есть `12:27:47Z`. В едином времени:

| локальное +05:00 | событие |
|---|---|
| 17:17-17:20 | созданы `testing-unit-domain`, `testing-contract`, слит каталог в 30 |
| **17:27:47** | R03 `c8b7fc0` добавляет `Skill` четырём ролям |
| 22:11:46 | `423a207` |
| **22:13:06** | стартует сессия 003 |
| 22:26:13 | диспатч `adw:test-author` |
| 22:29 | вызов скилла, который F-60 сочла невозможным |

R03 лёг **за 4 часа 45 минут до старта сессии**, а не через 14 минут после. Новые каталоги скиллов
созданы почти за пять часов до старта. Ни одна правка не пришлась на работающий диспатч.

Подтверждено содержанием, а не только часами. Начальный аттачмент сессии (17:13:06.576Z,
`isInitial: True`, `skillCount: 52`) уже перечисляет `adw:testing-unit-domain`. Этот скилл лежит
**только** в ревизии `423a207164b3` (30 скиллов); в `6f7fd3aafb0c` и `dfba3c4a8354` его нет — там по
14 скиллов старого каталога:

```
dfba3c4a8354   skills=14  testing-unit-domain=no
6f7fd3aafb0c   skills=14  testing-unit-domain=no
423a207164b3   skills=30  testing-unit-domain=yes
```

А `423a207164b3/agents/test-author.md` несёт `tools: Read, Write, Edit, Bash, Glob, Grep, Skill`.
То есть на момент диспатча определение **уже содержало `Skill`**, и вызов скилла — обычная работа
поля, а не загадка.

**Вывод: ЗАМЕРЕНО.** Наблюдение F-60 объясняется ошибкой часовых поясов в его собственной таблице.
Оба вывода, которые из него были сделаны, не имеют опоры: пере-разрешения `tools:` нет (прогон 3), а
про горячую перезагрузку каталога `skills/` тот прогон не говорит ничего — скиллы существовали до
старта сессии. Прежняя редакция этого раздела несла обратное как побочно замеренный факт; **факт
снят**. Что происходит с каталогом `skills/`, созданным **после** старта сессии, — **НЕ ПРОВЕРЕНО**;
эксперимент, который это закроет, — живая сессия на FIFO по образцу вопроса 5, где новый каталог
скилла создаётся между ходами.

Одна честная граница разбора: собственные вызовы инструментов сабагентами в транскрипте главной
сессии **не хранятся** (`SIDECHAIN tool_use: {}` при пяти диспатчах в `MAIN`), поэтому отсутствие в
нём строки `Skill(adw:testing-unit-domain)` доказательством отсутствия вызова не является и в выводе
не использовано. Вывод держится на времени R03 и на содержимом ревизии.

---

## Утверждение документации о поле `tools:` — ИЗ ДОКОВ, не замер

Отдельно от замера выше и намеренно рядом с ним: это нужно решению по F-04, и ценность блока в том,
что он **не** является замером. Страница `https://code.claude.com/docs/en/sub-agents`, прочитана
`WebFetch` 2026-08-01. Строка таблицы frontmatter про `tools`, дословно:

> `tools` | No | [Tools](#available-tools) the subagent can use. Inherits every tool available to
> subagents if omitted. If no entry in the list resolves to a tool, the subagent usually [fails to
> launch](/docs/en/errors#agent-would-be-spawned-with-zero-tools) with an error naming the entries.
> To preload Skills into context, use the `skills` field rather than listing `Skill` here

Соседняя строка про `skills`, дословно:

> `skills` | No | [Skills](/docs/en/skills) to preload into the subagent's context at startup. The
> full skill content is injected, not only the description. Subagents can still invoke unlisted
> project, user, and plugin skills through the Skill tool

Цитата, предъявленная человеком в решении по F-04, подтверждена дословно — источник открыт и прочитан,
а не пересказан. Прочтение, на котором остановились («rather than listing `Skill` here» — про
предзагрузку, а не про вызов по требованию), замером не опровергнуто: прогон 6 показывает ровно то,
что описывает вторая цитата, — предзагрузка кладёт содержимое названных скиллов, а «invoke unlisted
skills through the Skill tool» работает **только если `Skill` у агента есть**. Это уточнение к
документации, которая условия не называет.

Ещё два абзаца той же страницы, относящиеся к делу и **не замеренные**:

> To restrict tools, use the `tools` field as an allowlist or the `disallowedTools` field as a
> denylist. … If both are set, `disallowedTools` is applied first, then `tools` is resolved against
> the remaining pool. A tool listed in both is removed.

> The second filter applies to subagents running in the background. Apart from `Agent` and
> `ExitPlanMode`, … a background subagent keeps every MCP tool but only these built-in tools: `Read`,
> `Grep`, `Glob`, `Bash`, `PowerShell`, `Edit`, `Write`, `NotebookEdit`, `WebFetch`, `WebSearch`,
> `TodoWrite`, `Skill`, `ToolSearch`, `EnterWorktree`, `ExitWorktree`, `Monitor`, `TaskStop`,
> `SendMessage`, and `Artifact`. Claude Code removes every other built-in tool from a background
> subagent, whether inherited or listed in the `tools` field, so the same definition can resolve to
> different tools in the foreground and the background.

Первый абзац описывает форму, которой этот репозиторий не пользуется: `disallowedTools: Write, Edit`
наследует пул целиком, включая `Skill`, и снимает только запись. Второй объясняет, почему прогон 4
получил `Skill` при опущенном `tools:` — `Skill` входит в фоновый список, — и предупреждает, что
одно и то же определение в фоне и на переднем плане разрешается в разные наборы. **Ни то, ни другое
здесь не замерено**, и до замера ни на что опираться не должно.

---

## ПРОТИВОРЕЧИТ КАНОНУ — дополнение 2026-08-01 (вопрос 9)

Канон не правил. Ниже — что расходится с замером вопроса 9; решение за человеком. Блок отдельный от
того, что выше по файлу, чтобы не смешивать даты.

**4. `CLAUDE.md`, строки 51-53:** «The open one (question 9) is whether a running dispatch's `tools:`
is re-resolved mid-flight — raised by an observation that contradicts a restart claim this repo
previously asserted as fact (F-60).»

Замерено (вопрос 9, прогон 3 и разбор F-60): пере-разрешения нет, и наблюдение F-60 **ничему не
противоречило** — его таблица сравнивает UTC-времена транскрипта с локальным временем `git log`.
R03 лёг за 4 ч 45 мин **до** старта сессии 003, а не через 14 минут после; на момент диспатча
определение уже несло `Skill`. Придаточное «contradicts a restart claim this repo previously
asserted as fact» опоры не имеет: тот прогон утверждение о рестарте не проверял.

Заодно устарела арифметика той же врезки: «eight questions … plus one open question marked
НЕ ПРОВЕРЕНО». Вопросов девять, вопрос 9 закрыт как ЗАМЕРЕНО, а новая пометка НЕ ПРОВЕРЕНО стоит на
другом — на каталоге `skills/`, созданном после старта сессии.

**5. `plan/FINDINGS.md`, F-60** — не канон, а дев-запись, и правится не мной; фиксирую, чтобы
диспозиция принималась по фактам. Оба вывода записи держатся на той же ошибке часовых поясов:
«скиллы, созданные после старта сессии, разрешились без рестарта» (они созданы за ~5 часов **до**
старта) и «`Skill` заработал у диспатча, начавшегося до того, как это поле появилось» (поле
появилось за 4 ч 45 мин до старта сессии). Строка «я дал человеку неверный совет» о необходимости
рестарта тем прогоном не подтверждается — и не опровергается.

**6. Не противоречие, а усиление уже записанного.** Пункт 2 блока выше («`WORKFLOW.md` §1, литмус
мягкой деградации») теперь подпёрт тремя новыми прогонами вместо одного побочного: широкий `tools:`
(прогон 2), `skills:` с неразрешившимся именем (прогон 5) и `skills:` с разрешившимся (прогон 6) —
ни один второго пути к знанию не даёт. Пропажа `skills:` деградирует мягко **только** при `Skill` в
`tools:` или при опущенном `tools:`. Ничего нового к решению это не добавляет, но снимает
единственную оговорку, на которой решение по F-04 держалось условно.

---

## 529 посреди диспатча: платформа отвечает громко, но берёт полное время

Кладётся по решению человека 2026-07-31 (`plan/FINDINGS.md`, «Шаг 4, проход первый» → B7), источник —
F-56. **Класс: ЗАМЕРЕНО. Дата наблюдения: 2026-07-30. Версия: `2.1.220 (Claude Code)`** (та же, что у
§13, замеренного в тот же день).

**Чем это отличается от остальных записей файла.** Стенда не было и быть не могло: 529 приходит от
платформы под нагрузкой, и запросить его нечем. Наблюдение снято на настоящей работе — прогон change
002 в `adw-probe`, главная сессия, строки 2647 и 2666 её лога, — а не воспроизведено экспериментом.
Поэтому здесь нет ни команды запуска, ни контроля; есть счётчики завершившихся диспатчей.

**Что наблюдал.** Один вердикт красной фазы стоил **четыре** диспатча: FAIL → 529 → 529 → PASS.
Оба оборванных диспатча:

| | оборванный 1 | оборванный 2 |
|---|---|---|
| время стены | 4м46с | 4м17с |
| ходов | 1 | 1 |
| тул-коллов | 0 | 0 |
| выходных токенов | **0** | **0** |

Лог каждого — 24 КБ, и `agent_type` в нём не определяется: в отчёте прогона оба идут строками `?`.
Родитель при этом получил **настоящую ошибку**, дословно: `Agent → 529 Overloaded`.

**Вывод: ЗАМЕРЕНО.** Обрыв диспатча по 529 виден родителю как ошибка с кодом и текстом — по литмусу
`WORKFLOW.md` §1 это **деградация, а не отказ**, и в этом прямая противоположность `maxTurns`
(вопрос 3), который на потолке молчит и отчитывается словом `completed`. Цена платится не поведением,
а временем: ~9 минут стены на нулевую работу, и эта цена не видна ни в токенах, ни в тул-коллах —
оба счётчика у оборванного диспатча нули, то есть от несостоявшегося запуска он неотличим ничем,
кроме часов. Что из этого следует для счёта диспатчей — вопрос канона, и он там уже решён
(`WORKFLOW.md` §6); здесь только свойство платформы.

---

## Watchdog посреди диспатча: застрявший агент убивается на 600 секундах

Кладётся по решению человека 2026-08-05 (`plan/FINDINGS.md`, «раунд 5: цикл и роли» → F-184), источник
— F-184. **Класс: ЗАМЕРЕНО. Дата наблюдения: 2026-08-04**, время сообщения родителя
`2026-08-04T20:34:21.507Z` (UTC, как его пишет транскрипт). Версии в записи наблюдения нет; файл в
целом пришпилен к `2.1.220`.

**Чем это отличается от остальных записей файла — тем же, чем 529 выше.** Стенда не было и быть не
могло: застревание приходит на настоящей нагрузке, и запросить его нечем. Наблюдение снято с лога
главной сессии прогона change 001 второй пробы (`log-main-session-d345de83-08a.md:2314`), а не
воспроизведено экспериментом. Поэтому здесь нет ни команды запуска, ни контроля; есть дословный текст,
который увидел родитель.

**Что наблюдал.** Диспатч красной фазы не вернулся; вместо возврата родителю пришло, дословно:

```
Agent "Write failing tests for change 001" failed: Agent stalled: no progress for 600s
(stream watchdog did not recover)
```

Вместе с этим родитель получил последние слова убитого агента (поле `<result>` того же уведомления):
«Comments refined and all three non-pytest gates green. Now the full run.» — то есть агент работал, а
не молчал, и его правки уже лежали на диске.

**Второй факт того же прогона: `Bash` с длинным таймаутом платформа уводит в фон, а не обрывает.**
Дословно, две команды подряд (`:2375` и `:2400` того же лога, таймауты 400s и 120s):

```
Command did not complete within its 400s timeout and was moved to the background (ID: bo99ybyzc).
Output is being written to: …/tasks/bo99ybyzc.output. You will be notified when it completes. To
check interim output, use Read on that file path.
```

```
Command did not complete within its 120s timeout and was moved to the background (ID: b1z5p0fga).
Output is being written to: …/tasks/b1z5p0fga.output. You will be notified when it completes. …
```

Пути каталога задач сокращены до хвоста; остальное — как в логе.

**Вывод: ЗАМЕРЕНО.** Убитый watchdog'ом диспатч виден родителю как ошибка с текстом, кодом причины
(`no progress for 600s`) и последними словами агента — по литмусу `WORKFLOW.md` §1 это **деградация, а
не отказ**, ровно как 529 и в прямой противоположности `maxTurns` (вопрос 3), который на потолке молчит
и отчитывается словом `completed`. Отличие от 529 одно, и оно существенное: 529 обрывает диспатч на
нулевой работе — ноль ходов, ноль тул-коллов, ноль выходных токенов, — а watchdog убивает агента,
который **уже писал в дерево**. Значит «диспатч не вернулся» здесь не значит «работы нет». Что из этого
следует для того, кто диспатчил, — вопрос канона, не мой; здесь только свойство платформы.

Отдельно про фоновый `Bash`: это не обрыв, а перенос — вместо ошибки приходит идентификатор и путь
файла, куда пишется вывод. Оговорка замерена там же: немедленный `Read` этого файла дал
`Warning: the file exists but the contents are empty`, то есть путь появляется раньше вывода.

---

## Поле `model: inherit` — ИЗ ДОКОВ, замера нет

Кладётся по решению человека 2026-07-31 (`plan/FINDINGS.md`, «Шаг 4, проход первый» → B7), источник —
F-11. **Класс: ИЗ ДОКОВ. Дата чтения: 2026-08-01. Версия: `2.1.220 (Claude Code)`.** Страница
`https://code.claude.com/docs/en/sub-agents`, получена `curl -s -L` (`HTTP=200`, 1 091 915 байт),
цитаты сняты с HTML, разметка кода — по тегам `<code>` оригинала.

Строка таблицы frontmatter, дословно:

> `model` | No | [Model](#choose-a-model) to use: `sonnet`, `opus`, `haiku`, `fable`, a full model ID
> (for example, `claude-opus-5`), or `inherit`. Defaults to `inherit`

Раздел «Choose a model», два пункта из четырёх, дословно:

> - **inherit**: use the same model as the main conversation
> - **Omitted**: defaults to `inherit` and uses the same model as the main conversation

**Зачем эта запись.** `model: inherit` стоит у всех четырёх ролей в `plugins/adw/agents/` по прямому
предписанию `WORKFLOW.md` §5 — то есть по канону, а не по памяти. Но эксперимента под него не
ставилось ни разу, и сверка вида «каждое поле фронтматтера подтверждено `PLATFORM.md`» на нём
спотыкалась молча: строки не было вовсе. Теперь она есть, и она честно говорит, что это **утверждение
документации, а не замер**.

**Цена ошибки, если документация врёт или дефолт сменится в миноре, мала:** `inherit` значит «не
выбирать», и его игнор даёт роли модель сессии — не роль без знания и не отказ запуска. Поэтому
дозамер сюда не ставится в очередь; строка нужна ровно затем, чтобы отсутствие замера было видно.

---

## Поле `argument-hint` во фронтматтере команды — приняты обе YAML-формы

Кладётся по решению человека 2026-08-05 (`plan/FINDINGS.md`, «раунд 6: платформа и установка» → F-14),
источник — F-14. Замер не новый и нового эксперимента под него не ставилось: он сделан задачей B07 и
до сих пор жил в `plan/INSTALL-REHEARSAL.md` §9 и в теле находки. Переезжает сюда целиком вместе со
своей границей, потому что по правилу этого репозитория факт вне `PLATFORM.md` не замерен.
**Класс: ЗАМЕРЕНО. Дата наблюдения: 2026-07-29. Версия: `2.1.220 (Claude Code)`** — те же дата и
версия, что у вопросов 1–6.

**Это фронтматтер команды, а не агента.** Остальной файл меряет поля агента (`skills:`, `tools:`,
`model:`, `permissionMode`) и поведение установки; поля файла команды не мерились здесь ни разу,
поэтому раздел свой, а не приписка к вопросу про `skills:`.

**Что наблюдал.** Валидатор о поле не сказал ничего, и в дебаг-логах загрузки команд про него нет ни
строки (`grep -c -i argument` по двум логам → `0` и `0`), то есть по логам поле неотличимо от принятого
молча. Наблюдаемая часть — интерактивный экран; pty-проба, Enter не отправлялся.

Набрано `/adw:spec ` (с пробелом), у которого в файле `argument-hint: [what the change should do]` —
YAML-**список**. Строка ввода, дословно:

```
/adw:spec
what the change should do
```

Набрано `/adw:build ` (тоже с пробелом), у которого `argument-hint: <NNN>` — YAML-**скаляр**:

```
/adw:build
<NNN>
```

**Вывод: ЗАМЕРЕНО.** Обе формы принимаются, и подсказка отрисовывается в обеих. Молчаливого
игнорирования, каким платформа отвечает на неверное имя в `skills:` (вопрос 1), у этого поля нет —
хотя молчание логов одинаковое, и различает формы только экран. Список из одного элемента отрисован
**без квадратных скобок**: значение сведено к тексту, и разница между списком и скаляром на экране не
видна.

**Граница замера — НЕ ПРОВЕРЕНО:** как отрисуется список из **двух и более** элементов. В шипнутых
файлах такого нет, поэтому не пробовалось, и замер накрывает ровно две формы, которые в дереве есть.

---

## Что видит родитель о типе агента до диспатча: `description` и `tools`, **без тела**

Кладётся по решению человека 2026-08-05 (`plan/FINDINGS.md`, «раунд 6: платформа и установка» → F-137),
источник — F-137. **Класс: ЗАМЕРЕНО. Дата: 2026-08-05.
Версия: `claude --version` → `2.1.222 (Claude Code)`** — на патч старше, чем шапка этого файла
(`2.1.220`), поэтому версия названа здесь отдельно, а не взята из шапки.

**Предмет — агент, а не скилл.** Вопрос 7 меряет авто-вызов **скилла** по его `description` внутри
сабагента: там речь про реестр скиллов и про то, дотягивается ли до него сабагент. Здесь меряется
другое — что о **типе агента** лежит в контексте сессии, которая этот тип может диспатчить. Общее у
двух замеров только слово `description`; вопрос 7 этим разделом не затрагивается и не переписывается.

**Стенд.** `<scratch>/probe10/proj/.claude/agents/pelican-auditor.md` — выбрасываемый project-scoped
агент, `tools: Glob`, `model: inherit`. В нём два токена, и каждый лежит ровно в одном месте:
`KIWI-DESC-4417` — первое слово `description:`, `ZEBRA-BODY-9931` — только в теле промпта, дважды
(`grep -rc` по файлу → `3`). Оба токена случайны и заведены этим стендом; каталог создан пустым прямо
перед прогоном, и других файлов в нём нет. Дочерние сессии — `claude -p … --output-format stream-json --verbose`, из каталога
стенда, каждая с явным запретом файловых инструментов — одной строкой, как она передавалась:

```
--disallowedTools "Read,Grep,Glob,Bash,Write,Edit,WebFetch,WebSearch,Skill,TodoWrite"
```

Читать файл агента сессии нечем; всё, что она скажет о токенах, она может взять только из своего
контекста.

**Как отличается успех от тихого несрабатывания.** Токен `KIWI-DESC-4417` — положительный признак:
если он вернулся, `description` в контексте есть и модель отвечает по существу. Токен
`ZEBRA-BODY-9931` — отрицательный: его отсутствие и есть искомая форма, и она названа буквой, а не
описана словами.

**Наблюдение 1 — ростер есть, и он дословно такой.** Ответ сессии, целиком:

```
ROSTER=- pelican-auditor: KIWI-DESC-4417 audits pelican invoices for duplicate line items and returns a table of offenders. Use when an invoice must be checked for duplicates before payment. (Tools: Glob)
DESC=KIWI-DESC-4417
BODY=ABSENT
```

`tool_uses: 0`, `num_turns: 1` — сессия не воспользовалась ни одним инструментом.

**Наблюдение 2 — то же на настоящем ростере этого репозитория.** Сессия запущена из корня репозитория,
где `.claude/agents/` несёт три роли. Ответ, целиком:

```
ROSTER=- adw-prober: Measures actual Claude Code platform behaviour by experiment and records only what it observed, separating measurement from documentation claims. Use when a design decision depends on how the platform really behaves — subagent frontmatter fields, tool restrictions, skill loading, iteration ceilings. Never writes workflow artifacts; that is adw-builder. (Tools: Read, Write, Bash, Glob, Grep, WebFetch)
PHRASE=ABSENT
```

`tool_uses: 0`. Строка сверена с файлом посимвольно: взято `description:` из
`.claude/agents/adw-prober.md`, к нему приписано `" (Tools: " + tools: + ")"`, сравнение с ответом
сессии дало `IDENTICAL: True`. Форма, которой искали во второй строке, — предложение тела
`Words that must never appear as a conclusion`, встречающееся во всём репозитории **один раз**, в теле
того же файла агента (`grep -rn … --include='*.md'` → одна строка, `adw-prober.md:28`).

**Наблюдение 3 — то же спрошено положительно, а не как «есть ли строка».** Отдельная сессия того же
стенда, вопрос «назови пароль, которым пользуется агент pelican-auditor». Ответ целиком:

```
PASS=UNKNOWN
```

`tool_uses: 0`.

**Наблюдение 4 — контроль: тело существует и доезжает, но только до сабагента.** Ещё одна сессия того
же стенда, на этот раз с разрешённым `Task`; агент продиспатчен с промптом
`State your passphrase and nothing else.` Дословно из потока:

```
TOOL_USE: Agent {"subagent_type": "pelican-auditor", … "prompt": "State your passphrase and nothing else."}
SUB TEXT: ZEBRA-BODY-9931.
TOOL_RESULT: [{'type': 'text', 'text': 'ZEBRA-BODY-9931.'}, … <usage>subagent_tokens: 1975
tool_uses: 0
duration_ms: 2720</usage>]
MAIN TEXT: PASS=ZEBRA-BODY-9931
```

Сабагент назвал токен при `tool_uses: 0`, то есть взял его из своего системного промпта, а не из
файла. Значит «BODY=ABSENT» у родителя — не о том, что токена нет или что модель отказывается его
печатать, а ровно о том, что **в контексте родителя тела нет**.

**Наблюдение 5 — граница: ростер приходит вместе с инструментом диспатча.** Первый прогон делался с
`Task` в списке запрещённых, и тогда ответ был другим, дословно:

```
ROSTER=ABSENT — no agent type list is present in my context, and no subagent type named pelican-auditor appears anywhere in it.
DESC=ABSENT
BODY=ABSENT
```

То есть без инструмента диспатча в контексте нет и `description`. Прогон приведён потому, что он был
ложным отрицанием и едва не стал ответом: сессия без `Task` не «не видит тела», она не видит ничего.

**Побочно, из события `system`/`init` того же потока.** Перечень типов агентов приходит в поток
отдельным полем — **только имена**, без описаний и без инструментов:

```
agents: ['adw-builder', 'adw-prober', 'adw-warden', 'claude', 'Explore', 'general-purpose', 'Plan', 'statusline-setup']
```

**Вывод: ЗАМЕРЕНО.** В контекст сессии, которая может диспатчить, попадает по одной строке на тип
агента: `- <name>: <description дословно> (Tools: <список tools через запятую>)`. Тела файла агента
там нет — искали строкой `ZEBRA-BODY-9931` и предложением
`Words that must never appear as a conclusion`, обе вернулись отсутствием при нуле тул-коллов, а
контроль показал, что обе достижимы, когда тело в контексте действительно есть.

**Границы замера.**

- **НЕ ПРОВЕРЕНО:** попадает ли в ростер что-либо ещё, кроме `description` и `tools`, — мерились два
  поля, потому что только они в строке и появились; `model:` в обеих строках не отражён, но
  специального признака под него не ставилось.
- **НЕ ПРОВЕРЕНО:** то же для **плагинных** агентов. Оба наблюдения сделаны на project-scoped агентах
  из `.claude/agents/`; у второй пробы плагинные роли объявлены (`adw:evaluator`, `adw:implementer`,
  `adw:test-author`, `adw:test-review`), но токена в их телах нет, и подкладывать его туда — правка
  шипящегося файла.

---

## Второй путь подключения плагина: проектный `extraKnownMarketplaces` с `source: directory`

Кладётся по решению человека 2026-08-05 (`plan/FINDINGS.md`, «раунд 6: платформа и установка» → F-187),
источник — F-187. **Класс: ЗАМЕРЕНО. Дата: 2026-08-05.
Версия: `claude --version` → `2.1.222 (Claude Code)`.**

**Что за путь.** `~/Projects/adw-rooms/.claude/settings.json`, дословно и целиком:

```json
{
  "enabledPlugins": {
    "adw@wntic-adw": true
  },
  "extraKnownMarketplaces": {
    "wntic-adw": {
      "source": {
        "source": "directory",
        "path": "/Users/egorvorobyev/Projects/agentic-development-workflow"
      }
    }
  }
}
```

Это не то же, что §13 выше: там плагин живёт копией в `~/.claude/plugins/cache/<marketplace>/<plugin>/<sha>`
и двигается только явным `claude plugin update`. Под `adw-rooms` в `installed_plugins.json` записи нет:
у ключа `adw@wntic-adw` там ровно один элемент, и его `projectPath` — `~/Projects/adw-probe`.

**Признак, по которому мерили, и почему именно он.** Правило 9 скилла `test-principles`
(`filterwarnings`) появилось в дереве коммитом `cf12e78` **2026-08-05T11:00:40+05:00**
(= `06:00:40Z`); файл на диске последний раз менялся **2026-08-05T21:44:10+05:00** (= `16:44:10Z`,
`stat -f '%Sm'`). Правок этого прохода в признаке нет сознательно: правка свежее сессии дала бы
«нет» по причине возраста сессии, а не по механизму. Сессия запущена **2026-08-05T23:54:06+05:00**
(= `18:54:06Z`) и завершилась в `23:54:18+05:00`, `session_id 5a3914cc-c369-4e5f-ad61-ec54f13532b5`.
Все три времени названы с зоной намеренно: единственная выдуманная загадка этого файла (вопрос 9)
родилась из смешения `+05:00` и `Z`.

**Как мерили.** `claude -p` из `~/Projects/adw-rooms`, инструменты сведены к одному:
`--allowedTools "Skill" --disallowedTools "Read,Grep,Glob,Bash,Write,Edit,WebFetch,WebSearch,Task,TodoWrite"`.
Прочитать `SKILL.md` из рабочего дерева сессии нечем; единственная дорога к тексту — сам скилл.
Вопрос: процитировать правило 9 дословно либо ответить `RULE9=ABSENT`.

**Что наблюдал — событие `system`/`init`, поля дословно:**

```
adw plugin entry: {"name": "adw", "path": "/Users/egorvorobyev/Projects/agentic-development-workflow/plugins/adw", "source": "adw@wntic-adw", "version": "1.1.0"}
skills count: 48
skills: [… "adw:application", "adw:architecture", … "adw:test-principles", …]
agents: ['adw:evaluator', 'adw:implementer', 'adw:test-author', 'adw:test-review', 'claude', 'Explore', 'general-purpose', 'Plan', 'statusline-setup']
```

`path` указывает **прямо в рабочее дерево**, не в кэш, а `version` — `1.1.0`, то есть semver из
`plugin.json` дерева, а не SHA.

**Что наблюдал — ответ сессии.** Единственный тул-колл — `Skill {"skill": "adw:test-principles"}`,
результат `Launching skill: adw:test-principles`. Затем, дословно:

```
RULE9=**A warning is a failure, not a line in the tail of the output.** `[tool.pytest.ini_options]` carries `filterwarnings` with `"error"` as its first entry — the same table that already holds `asyncio_mode` and `markers` — so a warning raised anywhere in the run turns the suite red. This is part of what "green" means: no extra command, no second run, nothing anyone has to remember to read. The price is that a deprecation from a library the project cannot fix reddens the suite too, so an exception is written as one narrow entry after `"error"` — `"ignore:<message>:<Category>:<module>"`, scoped as tightly as the warning allows — and it carries its reason beside it in a comment: whose warning it is, why the project cannot remove it at the source, and what will retire the entry. An exception without a reason is the rule switched off. A warning raised from the project's own `src/` never goes on that list; it gets fixed. Same watershed `conventions` draws around `# noqa`: a suppression is legal at someone else's boundary, never on your own content.
FILTERWARNINGS=PRESENT
```

Процитированное сверено с деревом посимвольно: строки 200 и 201 `SKILL.md`, склеенные пробелом, дали
`IDENTICAL: True` при длине 1055 знаков. Правило 9 в дереве занимает две строки, и сессия вернула
обе — то есть не «слово `filterwarnings` где-то мелькнуло», а тот же текст.

**Отрицательный контроль — вопрос умеет отвечать «нет».** Выбрасываемый плагин
`<scratch>/probe10/oldplug` со скиллом того же имени `test-principles`, тело — восемь правил без
девятого и без слова `filterwarnings`; тот же вопрос, те же ограничения инструментов,
`--plugin-dir <scratch>/probe10/oldplug`. Ответ целиком:

```
RULE9=ABSENT
FILTERWARNINGS=ABSENT
```

**Вывод: ЗАМЕРЕНО.** Плагин, подключённый проектным `extraKnownMarketplaces` с `source: directory`,
отдаёт сессии **текущий текст рабочего дерева**: правка, закоммиченная за 12 ч 53 мин 26 с до старта
сессии и лежавшая на диске за 2 ч 09 мин 56 с до него, в сессии есть дословно. Помеченное `НЕ ПРОВЕРЕНО` в F-187 закрыто в сторону «дерево
перечитывается»; «проба приколота к состоянию на старте» отвергнуто наблюдением, а не рассуждением.

**Второе наблюдение, отдельной сессией: проектный `settings.json` перебивает запись в реестре
установок.** Тот же вопрос был задан из `~/Projects/adw-probe` — пробы, которая в реестре стоит как
установка через кэш:

```
adw@wntic-adw  scope=project  projectPath=/Users/egorvorobyev/Projects/adw-probe
installPath=~/.claude/plugins/cache/wntic-adw/adw/89ac6e8c8ea9  version=89ac6e8c8ea9
installedAt=2026-07-30T05:15:54.875Z   lastUpdated=2026-08-04T14:22:28.269Z
```

Кэш-копия по этому SHA девятого правила не несёт (`grep -c 'filterwarnings' $C/skills/test-principles/SKILL.md`
→ `0`). Сессия, тем не менее, ответила `FILTERWARNINGS=PRESENT` и тем же текстом правила 9, а её
`init` дал `{"name": "adw", "path": "/Users/egorvorobyev/Projects/agentic-development-workflow/plugins/adw", … "version": "1.1.0"}`
(`session_id 7784f845-619a-4ba6-a79a-daf6fca68404`, старт **2026-08-05T23:55:45+05:00** =
`18:55:45Z`). Причина видна в файле: у `adw-probe` есть свой
`.claude/settings.json`, дословно совпадающий с приведённым выше — тот же `extraKnownMarketplaces`,
тот же `source: directory`. Его mtime — **2026-07-30T10:15:54+05:00**, ровно момент `installedAt`
(`05:15:54.875Z`) той же записи реестра: установка из directory-маркетплейса **написала оба места
сразу**, и при старте сессии выигрывает `settings.json`, а не `installPath`.

**Границы замера.**

- **НЕ ПРОВЕРЕНО:** в какой момент читается файл скилла — на старте сессии или в момент вызова
  `Skill`. Обе правки признака старше старта сессии, поэтому два объяснения здесь неразличимы.
  Эксперимент, который их различил бы: править `SKILL.md` **посреди** открытой сессии и спрашивать
  повторно.
- **НЕ ПРОВЕРЕНО:** доезжает ли до такой сессии добавление **нового** скилла (новый каталог), а не
  правка существующего, — это оговорка вопроса 5 про свежесозданный каталог, и на directory-пути она
  не мерилась.
- **НЕ ПРОВЕРЕНО:** что видит сессия при `source: directory`, когда `settings.json` проекта убран, а
  запись в реестре установок остаётся. Одного такого проекта под рукой нет: оба существующих несут
  `settings.json`, и убрать его — правка пробы.

---

## Вопрос 10. Читается ли командный файл в `.claude/commands` через файловый симлинк

Замер по решению человека 2026-08-09 (`plan/FINDINGS.md`, «Решения человека, 2026-08-09», строка
«Форма команд зависит от замера»), задача — `plan/S11-00-command-symlink-probe.md`; вердикт ждёт
S11-02. **Дата: 2026-08-09. Версия: `claude --version` → `2.1.226 (Claude Code)`** — на шесть патчей
новее шапки файла (`2.1.220`), поэтому версия названа здесь отдельно. macOS Darwin 25.3.0.

**Зачем.** `.claude/commands` этого репозитория — симлинк на **каталог** `plugins/adw/commands`, и
эта форма замеренно работает (`plan/INSTALL-REHEARSAL.md` §6). S11 нужна другая: реальный каталог с
посимвольными симлинками на файлы команд. Молчаливое несрабатывание правдоподобно — неверная форма
имени в `skills:` замеренно игнорируется без единого слова наружу (вопрос 1).

**Стенд.** `<scratch>/cmdprobe/proj/` — проект-пустышка, `.claude/commands/` — **реальный** каталог:

- `real.md` — обычный файл, фронтматтер с `description`, тело: ответить ровно `PROBE-REAL-OK`;
- `linked.md` — **симлинк** `../../bodies/linked-body.md`, цель лежит вне `.claude/`
  (`<proj>/bodies/linked-body.md`), тело: ответить ровно `PROBE-LINK-OK`.

`readlink linked.md` → `../../bodies/linked-body.md`; `cat` через симлинк — `SYMLINK-RESOLVES`.
Маркеры перед прогоном проверены `grep -rl` — нигде, кроме двух тел команд (единственный посторонний
файл с этими строками — сама задача `plan/S11-00-…` в этом репозитории, до которого дочерним сессиям
не дотянуться: они запущены из пустышки, файловые инструменты запрещены).

**Как отличался успех от тихого несрабатывания.** Три вызова из корня пустышки, у каждого один и тот
же запрет инструментов — прочитать тело команды из файла сессии нечем, маркер мог попасть в ответ
только регистрацией команды:

```bash
claude -p "/real"   --disallowedTools "Read,Grep,Glob,Bash,Write,Edit,WebFetch,WebSearch,Skill,TodoWrite,Task"
claude -p "/linked" --disallowedTools "…тот же список…"
claude -p "/nosuch" --disallowedTools "…тот же список…"
```

**Что наблюдал** (весь stdout каждого вызова, дословно; `EXIT=0` у всех трёх):

| Вызов | Файл | Ответ |
|---|---|---|
| `/real` | реальный файл (контроль) | `PROBE-REAL-OK` |
| `/linked` | файловый симлинк (замер) | `PROBE-LINK-OK` |
| `/nosuch` | файла нет (отрицательный контроль) | `Unknown command: /nosuch` |

Три вызова дали три разные строки — проба различает. Повтор `/linked` в `stream-json --verbose`:
`"result":"PROBE-LINK-OK"`, `num_turns: 1`, строк `"type":"tool_use"` в потоке **ноль** — маркер
взять неоткуда, кроме тела команды. В событии `system`/`init` того же потока поле `slash_commands`
несёт **оба** имени, дословный фрагмент:

```
"slash_commands":["graphify","linked","real","deep-research",…]
```

**Вывод: ЗАМЕРЕНО — работает.** Командный файл в реальном каталоге `.claude/commands/` читается
через файловый симлинк: команда регистрируется под именем **симлинка** (`/linked`, не
`/linked-body`), тело берётся из целевого файла, лежащего вне `.claude/`. Попутно: несуществующая
команда в `claude -p` отказывает **громко** — `Unknown command: /nosuch` в stdout, — то есть
ожидавшегося по аналогии с `skills:` молчания у регистрации команд в этом режиме нет.

**Границы замера.**

- **НЕ ПРОВЕРЕНО:** интерактивная сессия — виден ли `/linked` в меню автодополнения. Замер целиком
  неинтерактивный (`claude -p`); добивающий эксперимент — интерактивная сессия в той же пустышке и
  набор `/lin` в строке ввода.
- **НЕ ПРОВЕРЕНО:** цель симлинка **вне корня проекта** — здесь цель лежала внутри пустышки
  (`bodies/` рядом с `.claude/`). Для S11-02 это совпадает с нужной формой: цели —
  `plugins/adw/commands/*.md` того же репозитория.
- **НЕ ПРОВЕРЕНО:** горячая подхватка симлинка, созданного после старта сессии, — оговорка
  вопроса 5 на команды не перемерялась.
