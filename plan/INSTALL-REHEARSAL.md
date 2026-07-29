# INSTALL-REHEARSAL.md — репетиция установки плагина

**Дата: 2026-07-29. Версия: `claude --version` → `2.1.220 (Claude Code)`. macOS Darwin 25.3.0.**
Задача B07. Всё ниже — **наблюдения**: команда и её вывод. Где наблюдения не было, так и написано.

Пометки те же, что в `plan/PLATFORM.md`: **ЗАМЕРЕНО** (команда запущена, вывод приведён),
**ИЗ ДОКОВ**, **НЕ ПРОВЕРЕНО** (это законченный ответ, а не обещание).

---

## 0. Стенд и что осталось в системе после репетиции

Чистый каталог проекта — `<scratch>/rehearsal/proj/`, на старте пустой (`ls -a` → пусто).
Локальный маркетплейс — сам репозиторий (`.claude-plugin/marketplace.json`, источник `directory`).

Оговорка про «чистый»: сам каталог пуст, но лежит **внутри** git-репозитория скратчпада, оставшегося
от проб B01/B06 (`git -C <scratch>/rehearsal/proj rev-parse --show-toplevel` → `<scratch>`,
`git tag --list 'change/*'` → `change/007`). Ни одна проба ниже от этого не зависит, а `/adw:spec` этот
факт увидел сам и учёл (§3).

Первый заход делался в **изолированном** конфиге, `CLAUDE_CONFIG_DIR=<scratch>/rehearsal/home/.claude`:
изоляция подтверждена (`claude plugin marketplace list` → `No marketplaces configured`, тогда как в
настоящем конфиге их два). Установка там прошла, но **живая сессия в изолированном конфиге не
авторизуется**: `claude -p "Reply with exactly: AUTH-OK"` → `Not logged in · Please run /login`
(в `~/.claude/.credentials.json` файла нет — креды не в конфиг-каталоге). Поэтому всё, что требует
работающей сессии, сделано в настоящем конфиге, но **scope'ом `project`** — так установка привязана
к чистому каталогу и в других проектах выключена (проверено в §6).

**Что осталось в настоящем конфиге и как убрать.** Установка живёт: запись
`adw@wntic-adw` в `~/.claude/plugins/installed_plugins.json` со `scope: "project"` и
`projectPath` = чистый каталог; маркетплейс `wntic-adw` в `~/.claude/plugins/known_marketplaces.json`;
`pluginUsage/adw@wntic-adw` в `~/.claude.json`; копия плагина в
`~/.claude/plugins/cache/wntic-adw/adw/53b25ae555b2/`. Объявление маркетплейса и включение плагина —
в `<scratch>/rehearsal/proj/.claude/settings.json`, то есть в скратчпаде. Каталога под маркетплейс в
`~/.claude/plugins/marketplaces/` не появилось — у источника `directory` клона нет.

Оставлено **намеренно**: финальная проверка шага 1 (`/adw:spec` в чистом проекте) за главной сессией, и
ей нужна живая установка. Теардаун — две команды из чистого каталога, **ими я не прогонял**:

```bash
claude plugin uninstall adw --scope project -y
claude plugin marketplace remove wntic-adw
```

Снимок состояния до установки — `<scratch>/rehearsal/snapshot/` (`installed_plugins.before.json`,
`marketplaces.before.txt`, `plugins.before.txt`); `md5` файла установок до репетиции —
`6204dd3ccf30b8faac125cd38e4cd45f`.

Побочное: чтобы получить интерактивный экран, принят диалог доверия (`1` в pty-пробе) — это записало
`hasTrustDialogAccepted: true` в `~/.claude.json` для **корня скратчпада** (доверие ключуется по
git-корню, не по каталогу проекта).

---

## 1. Манифесты проходят валидатор платформы

```
$ claude plugin validate plugins/adw
Validating plugin manifest: …/plugins/adw/.claude-plugin/plugin.json
⚠ Found 1 warning:
  ❯ version: No version specified. Consider adding a version following semver (e.g., "1.0.0")
✔ Validation passed with warnings

$ claude plugin validate .
Validating marketplace manifest: …/.claude-plugin/marketplace.json
⚠ Found 1 warning:
  ❯ plugins[0] plugin.json → version: No version specified. …
✔ Validation passed with warnings
```

С `--strict` тот же единственный warning становится ошибкой: `✘ Validation failed (--strict treats
warnings as errors)`. Других замечаний у валидатора нет — ни к раскладке, ни к `templates/`, ни к
`skills/CONVENTIONS.md`, лежащему в `skills/` не скиллом. **ЗАМЕРЕНО.** Отсутствие `version` — решение
задачи B07 (пиновка оставляет установки висеть), и цена его теперь известна ровно одной строкой:
`--strict` красен.

---

## 2. Установка в чистый каталог из локального маркетплейса

```
$ cd <scratch>/rehearsal/proj && ls -a
(пусто)

$ claude plugin marketplace add /Users/egorvorobyev/Projects/agentic-development-workflow --scope project
Adding marketplace…✔ Successfully added marketplace: wntic-adw (declared in project settings)

$ claude plugin install adw@wntic-adw --scope project
Installing plugin "adw@wntic-adw"...✔ Successfully installed plugin: adw@wntic-adw (scope: project)

$ cat .claude/settings.json
{
  "extraKnownMarketplaces": {
    "wntic-adw": { "source": { "source": "directory", "path": "…/agentic-development-workflow" } }
  },
  "enabledPlugins": { "adw@wntic-adw": true }
}

$ claude plugin list
  ❯ adw@wntic-adw
    Version: 53b25ae555b2
    Scope: project
    Status: ✔ enabled
```

**ЗАМЕРЕНО.** Ставится с дефолтной раскладкой, без единого объявленного пути компонента.

**Инвентарь глазами платформы** (`claude plugin details adw`, дословно шапка):

```
  Skills (17)  accept, application, architecture, build, commit, conventions, domain-model,
               domain-ports, infra-integration, infra-persistence, meta-skill-author,
               meta-uc-author, python-style, restapi, spec, testing-integration, testing-unit
  Agents (4)  evaluator, test-author, test-review, implementer
  Hooks (0)
  MCP servers (0)
  LSP servers (0)
  Projected token cost — Always-on: ~2,482 tok added to every session
```

Семнадцать «скиллов» — это 13 скиллов **плюс** 4 команды: реестр у платформы один, и команды в этом
инвентаре от скиллов не отделены. Хуков ноль — и это наблюдение, а не заявление.

**Что загрузила живая сессия** (`claude -p … --debug-file`, строки дословно):

```
[DEBUG] Checking plugin adw: skillsPath=exists, skillsPaths=0 paths
[DEBUG] Attempting to load skills from plugin adw default skillsPath:
        /Users/egorvorobyev/Projects/agentic-development-workflow/plugins/adw/skills
[DEBUG] Loaded 4 commands from plugin adw default directory
[DEBUG] Loaded 4 agents from plugin adw default directory
[DEBUG] Loaded 13 skills from plugin adw default directory
```

4 + 4 + 13 — ровно то, что лежит в дереве. И существенная деталь: путь загрузки — **рабочее дерево
репозитория**, а не копия в кэше. Для источника `directory` в `known_marketplaces.json`
`installLocation` равен самому исходному каталогу; копия
`~/.claude/plugins/cache/wntic-adw/adw/53b25ae555b2/` при этом создана и в `installed_plugins.json`
названа `installPath`. Две правды об одном корне — см. §8 и §10.

---

## 3. Команды видны с префиксом `adw:`

Два независимых наблюдения.

**(а) Палитра интерактивной сессии.** Пробы через pty (`script -q /dev/null claude`, ввод дописывается
в stdin, Enter не отправляется ни разу; ANSI снят `perl`'ом). Набрано `/adw:` — экран, дословно:

```
/adw:spec                       (adw) Interview a human into one change —
                                writes spec.md and criteria.md on a new cha…
/adw:build                      (adw) Run the change cycle on a change
                                branch — tests, a verdict on them, the base…
```

Набрано `/adw:acc` → `/adw:accept  (adw) Accept a finished change — merge its …`;
набрано `/adw:com` → `/adw:commit  (adw) Lint, stage, and commit specified …` и следом
`/adw:conventions (adw) Reference skill (produces no …)`. Список в 80 колонках скроллится, поэтому
все четыре сняты не одним экраном, а тремя вводами.

**(б) Команды действительно исполняются под этим префиксом.** Неизвестное имя даёт отказ:
`claude -p "/adw:nosuchcommand"` → `Unknown command: /adw:nosuchcommand`. Известные — исполняются, и
в ответе видно тело именно этого файла (все четыре прогона в чистом каталоге, `--allowedTools ""`):

- `/adw:spec` → «`specs/` does not exist — this is the project's first change», далее ruling про
  вертикальный срез и субстрат прицепом — то есть `commands/spec.md:36` из шага 1 «Orient», — плюс
  номер изменения,
  посчитанный по тегам объемлющего репозитория: «`git tag --list 'change/*'` → `change/007` … Max is 7,
  so: `specs/changes/008-<slug>/`». Закончил тремя вопросами человеку;
- `/adw:build 999` → «Stopping at step 0 — the preconditions do not hold», по пунктам: нет дельты,
  нет `Makefile` («an absent check is not a green one»), ветка не `change/999`;
- `/adw:accept 999` → «Stopping. Change `999` cannot be accepted», с перечислением тех же
  предусловий по своему файлу;
- `/adw:commit` → отчёт, что все четыре шага требуют `Bash`, которого в сессии нет.

**ЗАМЕРЕНО.** Все четыре команды видны и работают как `/adw:*`.

---

## 4. Четыре агента цикла видны как типы сабагентов

Спрошен несуществующий тип — список отдаёт сама платформа, это `tool_result`, а не пересказ модели:

```
TOOL_RESULT: Agent type 'zzz-nonexistent-type' not found. Available agents: adw:evaluator,
adw:implementer, adw:test-author, adw:test-review, claude, Explore, general-purpose, Plan,
statusline-setup
```

**ЗАМЕРЕНО.** Четыре роли адресуются `adw:test-author`, `adw:test-review`, `adw:implementer`,
`adw:evaluator` — ровно форма, которую `commands/build.md` велит использовать при установке плагином.

---

## 5. Скиллы видны

Три наблюдения об одном: строка загрузчика `Loaded 13 skills from plugin adw default directory`;
инвентарь `claude plugin details adw` (§2), где среди 17 записей все 13 скиллов названы по именам;
палитра, где скилл
виден слэш-командой — `/adw:conventions (adw) Reference skill (produces no …)`. Плюс §7: содержимое
скилла доехало до сабагента. **ЗАМЕРЕНО.**

---

## 6. Checked-out и installed загрузки не включены одновременно

Установка сделана `--scope project` и привязана к чистому каталогу — в `installed_plugins.json`:

```json
"adw@wntic-adw": [ { "scope": "project",
  "installPath": "/Users/egorvorobyev/.claude/plugins/cache/wntic-adw/adw/53b25ae555b2",
  "version": "53b25ae555b2", "gitCommitSha": "53b25ae555b2150ef7e46a5c96c9de66c24cbd08",
  "projectPath": "<scratch>/rehearsal/proj" } ]
```

Отсюда два наблюдения, по каждому проекту своё.

**В чистом каталоге** — только installed-загрузка. Дерево целиком:
`.claude/settings.json` и ничего больше (`find … -maxdepth 3` даёт три строки: каталог, `.claude`,
`settings.json`). Ни `.claude/skills`, ни `.claude/commands`, ни `.claude/agents` — значит удваиваться
нечем, и в палитре имена только префиксные (§3).

**В репозитории воркфлоу** — только checked-out-загрузка. `claude plugin list` с cwd репозитория:
`adw@wntic-adw … Scope: project … Status: ✘ disabled`. Палитра в репозитории, pty-проба, дословно:

```
/adw:
No commands match "/adw:"
```

и на `/spe` — `/spec  Interview a human into one change — writes …` **без** маркера `(adw)`, то есть
из симлинков `.claude/commands -> ../plugins/adw/commands`. Список типов сабагентов в репозитории (тем
же приёмом, что в §4):

```
Agent type 'zzz-nonexistent-type' not found. Available agents: adw-builder, adw-prober, adw-warden,
claude, Explore, general-purpose, Plan, statusline-setup
```

Четырёх ролей цикла здесь нет вовсе: симлинкованы только `skills` и `commands`, а `.claude/agents/`
несёт три сборочные роли. **ЗАМЕРЕНО:** ни в одном из двух проектов две загрузки не включены разом; в
каждом ровно одна, и по префиксу видно какая.

Как выглядело бы удвоение, здесь не воспроизводилось: коллизия имён уже замерена в `PLATFORM.md`
(вопрос 1) — короткая форма отдаётся проектному скиллу, плагинный **молча** затеняется. Второй раз не
мерил.

---

## 7. F-01 — разрешается ли `skills: adw:<name>` после настоящей установки

Спрашивался **настоящий** агент цикла, `adw:test-review` (у него в фронтматтере `skills:`
блок-списком из двух элементов — `adw:testing-unit` и `adw:testing-integration`), из чистого каталога, где плагин установлен и
`--plugin-dir` не подавался. Сессия: `--allowedTools "Task Read Bash Glob Grep"` (набор агента
пересекается с набором сессии, `PLATFORM.md`, побочное 3), `--forward-subagent-text`, `--debug-file`.

Промпт сабагенту: отвечать **только** тем, что уже в контексте, инструментами не пользоваться; сколько
артефактов несёт unit-тема, как называются топик-файлы, и какой у домена per-layer speed target.
Ответ (дословно из `tool_result` родителя):

```
ARTIFACTS=7
FILES=handler.md, fake.md, entity.md, value-object.md, enum.md, domain-service.md, architecture-rule.md
SPEED=< 10 ms
<usage>subagent_tokens: 14347  tool_uses: 0  duration_ms: 4886</usage>
```

Сверка с диском: `skills/testing-unit/SKILL.md:8` — «This theme covers 7 test artifacts»;
`ls skills/testing-unit/` — те же семь имён; `SKILL.md:37` — `< 10 ms` в колонке домена. `tool_uses: 0`,
то есть прочитать файл было нечем. Дебаг-лог той же сессии:

```
[DEBUG] [Agent: adw:test-review] Preloaded skill 'adw:testing-unit'
[DEBUG] [Agent: adw:test-review] Preloaded skill 'adw:testing-integration'
```

**ЗАМЕРЕНО: F-01 закрыта в пользу префикса.** После настоящей установки из маркетплейса форма
`adw:<name>` разрешается, и предзагружаются оба элемента блок-списка. Строки `Skill … was not found`
в логе нет ни одной.

**Методическая оговорка, стоившая одного прогона.** Первый вариант промпта просил агента напечатать
H1 «каждого блока знаний, который тебе дали, а если такого нет — `NO-SKILL`». Ответ: `NO-SKILL` — при
`subagent_tokens: 14161` и двух строках `Preloaded skill` в логе того же прогона. То есть **само-отчёт
агента о собственном контексте дал ложное отрицание**; различающим оказался только вопрос **по
содержанию**. Это ровно то, ради чего в задаче написано «проверяется тем, что агент цитирует
содержимое скилла, а не тем, что он успешно завершился» — и заодно предупреждение: «агент сказал, что
знания нет» доказательством отсутствия предзагрузки не является.

---

## 8. F-18 — достижим ли `templates/*.md` из сессии потребляющего проекта

Проба в чистом каталоге, `--allowedTools "Read Glob Grep Bash"`: «команда `/adw:spec` велит заполнять
артефакты из `templates/spec.md` и `templates/criteria.md`, shipped next to that command; найди и
прочитай оба, напечатай `PATH=` и `FIRST=`, либо `PATH=NOT-FOUND` / `READ-DENIED=<дословный отказ>`;
пути не угадывать». Ответ, дословно:

```
PATH=/Users/egorvorobyev/.claude/plugins/cache/wntic-adw/adw/53b25ae555b2/templates/spec.md
FIRST=# <NNN> — <short title of the change>
PATH=/Users/egorvorobyev/.claude/plugins/cache/wntic-adw/adw/53b25ae555b2/templates/criteria.md
FIRST=# Criteria — <NNN-slug>
```

Обе первые строки совпадают с файлами B03 дословно. Записи не требовалось, отказа доступа не было
(«Both reads succeeded; no permission was denied»), хотя оба файла лежат **вне** cwd.

Три наблюдения из того же прогона, каждое важнее самого «нашёл».

1. **Переменной окружения на корень плагина в сессии нет.** `env | grep -i -E "CLAUDE|PLUGIN"` в
   сессии даёт `CLAUDECODE`, `CLAUDE_CODE_ENTRYPOINT`, `CLAUDE_CODE_EXECPATH`,
   `CLAUDE_CODE_SESSION_ID`, `CLAUDE_EFFORT`, `CLAUDE_PID`, `AI_AGENT` — и **никакого**
   `CLAUDE_PLUGIN_ROOT`. Зато в `PATH` дописан `…/agentic-development-workflow/plugins/adw/bin` —
   каталога `bin/` в плагине нет (`ls plugins/adw` даёт четыре каталога и `.claude-plugin`), а путь
   всё равно добавлен. Опереться на него, чтобы вывести корень плагина, эта проба не пробовала.
2. **Путь получен поиском и дизамбигуацией, а не по ссылке.** Агент нашёл на диске **четыре** копии
   плагина с `commands/spec.md` и `templates/`: три ревизии в
   `~/.claude/plugins/cache/wntic-adw/adw/` (`53b25ae555b2`, `1f90295daa45`, `6e12ec33fa3b`) и рабочее
   дерево репозитория. Выбрал `53b25ae555b2` по `installPath` из `installed_plugins.json`. Две старые
   ревизии (остатки прошлых заходов) **не несут `templates/spec.md` вообще** — перепроверено мной
   отдельно, `ls ~/.claude/plugins/cache/wntic-adw/adw/*/templates`: у `1f90295daa45` и `6e12ec33fa3b`
   лежат `capability.md change.md criteria.md overview.md verdict.md`, у `53b25ae555b2` —
   `Makefile capability.md criteria.md spec.md verdict.md`. То есть неверная дизамбигуация здесь
   означала бы `NOT-FOUND` или, хуже, чужой шаблон.
3. **Выбранная копия — не та, из которой сессия исполняет команду.** Дебаг-лог того же прогона:
   `Attempting to load skills from plugin adw default skillsPath: …/Projects/agentic-development-workflow/plugins/adw/skills`.
   Живой корень — рабочее дерево; агент сознательно от него отказался («it is not the registered
   install»). Здесь содержимое совпадало, поэтому цена нулевая; при расхождении дерева и кэша
   расхождение молчит.

И то, что агент заметил сам, дословно: «The command text at `commands/spec.md:126-127` says the
skeletons are "shipped next to this command." Literally they are not — they sit in `templates/` at the
plugin root, a sibling of `commands/`, not inside it.»

**ЗАМЕРЕНО: F-18 достижимость подтверждена, но не по ссылке, а поиском** — и поиск на этой машине
имел четыре кандидата, два из которых не содержат нужного файла. Deliverable B03 достижим; формулировка
«next to this command» и отсутствие имени корня — расхождение в файле, который принадлежит B04, поэтому
здесь оно записано, а не поправлено.

---

## 9. F-14 — принимается ли `argument-hint`, и показывается ли подсказка

Валидатор о поле не сказал ничего (§1 — единственный warning про `version`); в дебаг-логах загрузки
команд ни одной строки про `argument-hint` нет (`grep -c -i argument` по двум логам → `0` и `0`), то
есть по логам поле неотличимо от принятого молча. Наблюдаемая часть — интерактивный экран; pty-проба,
Enter не отправлялся.

Набрано `/adw:spec ` (с пробелом), у которого в файле `argument-hint: [what the change should do]` —
YAML-список. Строка ввода, дословно:

```
/adw:spec
what the change should do
```

Набрано `/adw:build ` (тоже с пробелом), у которого `argument-hint: <NNN>` — YAML-строка:

```
/adw:build
<NNN>
```

**ЗАМЕРЕНО.** Обе формы принимаются, подсказка показывается. Список из одного элемента отрисован без
квадратных скобок — то есть значение сведено к тексту, и разница между «списком» и «строкой» на экране
не видна. **НЕ ПРОВЕРЕНО:** как отрисуется список из **двух и более** элементов — в шипнутых файлах
такого нет, поэтому не пробовал.

---

## 10. Побочное, замеренное попутно

1. **`version` в установке появляется сам — как SHA HEAD'а.** `claude plugin list` → `Version:
   53b25ae555b2`, в `installed_plugins.json` — `"version": "53b25ae555b2"` и
   `"gitCommitSha": "53b25ae555b2150ef7e46a5c96c9de66c24cbd08"`, что равно
   `git rev-parse HEAD` репозитория. При этом установленная **копия несёт рабочее дерево, а не HEAD**:
   на момент установки `git status --short` показывал `M .claude-plugin/marketplace.json` и
   `M plugins/adw/.claude-plugin/plugin.json`, и `grep` по копии в кэше находит именно
   незакоммиченное описание. То есть метка ревизии и содержимое копии могут расходиться.
2. **Кэш накапливает ревизии и не чистится.** В `~/.claude/plugins/cache/wntic-adw/adw/` три каталога,
   два — от прошлых заходов с другой раскладкой `templates/`.
3. **Изолированный `CLAUDE_CONFIG_DIR` для установки годится, для живой сессии — нет** (§0: `Not
   logged in`).
4. **`/help` и `SlashCommand` в `-p` недоступны:** `claude -p "/help"` → `/help isn't available in this
   environment.`; сессия с `--allowedTools "SlashCommand"` ответила «I don't have a SlashCommand tool».
   Поэтому список команд снят палитрой через pty, а не «спроси модель, что она видит».

---

## 11. Чего эта репетиция не проверяла

- **Финальная проверка шага 1** — `/adw:spec` в чистом проекте даёт S-спеку за одно интервью: её
  прогоняет главная сессия, не B07. Здесь `/adw:spec` запускался одним неинтерактивным ходом
  (`-p`, `--allowedTools ""`) только чтобы увидеть, что команда разрешается и исполняет своё тело (§3);
  он вернул ориентировку и три вопроса, и на этом ход кончился — интервью не велось, спека не писалась.
- **Установка из GitHub** (`/plugin marketplace add wntic/agentic-development-workflow`, как в
  `README.md`): проверялся источник `directory`, не `github`. **НЕ ПРОВЕРЕНО.**
- **Интерактивные `/plugin …`-команды** внутри сессии: всё делалось CLI-подкомандами
  `claude plugin …`. **НЕ ПРОВЕРЕНО**, отличается ли их поведение.
- **Обновление и удаление плагина** (`claude plugin update` / `uninstall`) — не прогонялись, кроме
  того, что команды теардауна выписаны в §0.

---

## §12. Финальный гейт шага 1 — прогон главной сессии

Дописано **главной сессией**, не builder'ом: `Проверка` задачи B07 отдаёт этот гейт ей.
Критерий из `WORKFLOW.md` §10: «`/adw:spec` даёт S-спеку за одно интервью». 2026-07-29, `2.1.220`.

**Стенд.** Два чистых проекта в скратчпаде, каждый — свой git-репозиторий на `main`, `specs/` нет,
плагин виден только установкой (`Status: ✔ enabled`, `scope: project`). Промпт по существу один и
тот же в обоих: описание изменения плюс ответы, которые дал бы человек, — чтобы интервью закрылось
за один проход и было видно, спросит ли команда лишнее.

Побочно устранено перед прогоном: в корне скратчпада лежал посторонний git-репозиторий, оставленный
сломанной командой главной сессии. Чистый проект разрешался в него, и гейт молча мерил бы не то.

**Прогон 2 (полный, с разрешённым git) — наблюдения:**

```
branch: change/001
specs/changes/001-health-endpoint/criteria.md
specs/changes/001-health-endpoint/spec.md
d20144e spec(001): health-эндпоинт с версией сервиса
83efb85 chore: project root
specs/changes/001-health-endpoint/spec.md:3:Affects: health.md
specs/changes/001-health-endpoint/spec.md:5:Depth: S
```

Ветка `change/001` от `main`; два файла; коммит; `Depth: S`; сработал триггер 1 (новый
capability-файл, первый ограниченный контекст) → секция `Design` присутствует со связывающими
именами, триггеры 2–5 не сработали. Интервью не задало ни одного вопроса — всё, что нужно, было в
ответах. Остатков HTML-комментариев шаблона: ноль.

**ГЕЙТ ПРОЙДЕН.**

**Два наблюдения из сравнения прогонов, оба ушли в `FINDINGS.md`:**

- **F-23.** Прогон 1 дал `spec.md` **без** полей `Affects:` и `Depth:` (`grep -nE
  '^(Affects|Depth):'` → ноль совпадений), прогон 2 — с ними. Один промпт, один шаблон, разный
  результат. Недетерминированность здесь хуже самого дефекта: `Affects` читают и `/adw:accept`, и
  шаг 0 `/adw:build`.
- **F-17.** Развилка «`Verification` при глубине S» наблюдена в оба конца: прогон 1 секцию дописал и
  пометил отступление, прогон 2 не дописал и назвал дыру человеку. В обоих случаях команда сказала
  вслух; молчаливого пропуска не было.

**Что этот гейт НЕ проверял.** `/adw:build` и `/adw:accept` против настоящего изменения — это шаг 2
§10, и ни одна из двух команд живьём не гонялась. Здесь замерено ровно то, что обещает §10.
