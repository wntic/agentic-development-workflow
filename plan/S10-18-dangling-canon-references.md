# S10-18 — три ссылки на `§9` и «dry-run» уходят из шипящихся скиллов

Тип агента: **`adw-builder`**
Слой: **ядро** (`plugins/adw/skills/test-application-handler/SKILL.md`,
`plugins/adw/skills/test-fake-repository/SKILL.md`)
Происхождение: решение человека 2026-08-05, `plan/FINDINGS.md`, секция «Решения человека, 2026-08-05 —
принятые в ходе исполнения S10», строка **F-207**.

**Восемнадцатая задача — видимое событие.** Она появилась не «по ходу»: находка F-207 записана главной
сессией, диспозиция принята человеком отдельным решением и легла в реестр **до** написания этого файла, и в
таблице `INDEX.md` она стоит своей строкой. Правило 1 внизу `INDEX.md` требует именно этого.

Читать сначала:
- в `plan/FINDINGS.md` — тело **F-207** заголовочным грепом
  (`rtk proxy grep '^## F-' plan/FINDINGS.md`, потом читать только эту запись) и строку диспозиции в
  названной секции;
- `plugins/adw/skills/test-application-handler/SKILL.md` — раздел на строке ~181 целиком: его заголовок и
  первый абзац;
- `plugins/adw/skills/test-fake-repository/SKILL.md` — пункт на строке ~167 целиком;
- `CLAUDE.md`, раздел «How skills work», два стоящих правила — «A skill must not know what invokes it» с его
  тестом («прочёл бы это новый разработчик как онбординг-документ?») и «Derivation has one home»;
- `plan/ORIENT.md` §3 — правило поставки по местоположению и прямая строка о том, что шипящийся файл **не
  может** ссылаться на `WORKFLOW.md`.

Основание замерено:

```bash
rtk proxy grep -rn 'dry-run\|dry run\|criteria\.md\|spec\.md\|report back\|orchestrator\|the cycle\|red phase\|green phase\|WORKFLOW\|§[0-9]\|adw:' \
  plugins/adw/skills/ | rtk proxy grep -v 'CONVENTIONS.md'
```

Три попадания — протечки, и все три в двух файлах:

| файл:строка | что стоит |
|---|---|
| `test-application-handler:181` | заголовок «## Assert strength — pin the contract, not a coincidence **(§9)**» |
| `test-application-handler:183` | «is exactly what **the §9 adversarial pass** flags … (distilled from real weak asserts **the adversarial pass** caught)» |
| `test-fake-repository:167` | «**the §9 assert** for it can never be strong (**the dry-run** hit exactly this)» |

Остальные совпадения свипа — не протечки: «cycle» в `python-style` и `architecture` — цикл импорта,
«orchestrator» в `domain-service`, `testing-unit-domain`, `architecture` — форма домен-сервиса. Не трогать.

`§9` — раздел `WORKFLOW.md`, которого в потребительском проекте нет вовсе, то есть ссылка висячая.
«Dry-run» — словарь нашей дев-записи.

## Задача

Три места переписываются на **предметный язык**: без номера раздела, без имени нашего прогона, без слов,
которых у читателя-потребителя не существует. Смысл сохраняется целиком — он верен, и правится только то,
чем он назван.

Ориентиры для формулировок, не буквальный текст:

- вместо «(§9)» в заголовке — ничего или предметное уточнение: заголовок и без номера говорит, о чём
  раздел;
- вместо «the §9 adversarial pass flags» — то, что происходит по существу: слабое утверждение находит
  **разбор, спрашивающий, упал бы тест на правдоподобно неверной реализации**. Кто именно этот разбор ведёт
  — не дело скилла;
- вместо «(distilled from real weak asserts the adversarial pass caught)» — «distilled from real weak
  asserts» или равное по смыслу: происхождение рецептов сохраняется, имя нашего механизма уходит;
- вместо «(the dry-run hit exactly this)» — «this has been hit in practice» или равное: факт, что случай
  настоящий, сохраняется, имя нашего прогона уходит.

**Проверь себя тестом правила:** прочёл бы новый разработчик получившуюся строку как онбординг-документ, не
спотыкаясь? На «§9 adversarial pass» он спотыкается — ни §9, ни этого прохода у него нет.

## Deliverables

Два файла, три переписанных места. Больше ничего.

## Границы

- **Только эти два файла.** Ни `python-style`, ни `architecture`, ни `domain-service`, ни
  `testing-unit-domain` — их совпадения свипа законны и названы выше.
- **Содержание рецептов не менять.** Предмет задачи — четыре оборота, а не техника сильного ассерта.
- **Ни одного нового упоминания цикла, роли или прогона** взамен убранных: замена не должна оказаться
  другой протечкой.
- **Нумерацию и структуру разделов не менять** — только текст заголовка на `:181` в части «(§9)».
- **`CONVENTIONS.md` в `meta-skill-author` не трогать** — он вне свипа сознательно.
- **Проб не править.**
- Не чинить найденное по дороге — находка идёт в `plan/FINDINGS.md`, и пишет её главная сессия. Если свип
  из «Основания» даст на твоём прогоне больше трёх протечек — **доложи, не расширяй объём**.

## Проверка

Прогнана на нетронутом дереве до отправки задачи; ответ «до» назван у каждой строки.

```bash
git diff --stat -- plugins/adw/skills/test-application-handler/ plugins/adw/skills/test-fake-repository/
# до: пусто. После: ровно два файла
rtk proxy grep -rc '§[0-9]' plugins/adw/skills/ | rtk proxy grep -v ':0'
# до: test-application-handler:2 и test-fake-repository:1. После: пусто
rtk proxy grep -rc 'dry-run\|dry run' plugins/adw/skills/ | rtk proxy grep -v ':0'
# до: test-fake-repository:1. После: пусто
rtk proxy grep -rc 'WORKFLOW' plugins/adw/skills/
# до: ни одной непустой строки. После: так же
rtk proxy grep -c 'Assert strength' plugins/adw/skills/test-application-handler/SKILL.md
# до: 1. После: 1 — раздел на месте, номер из заголовка ушёл
rtk proxy grep -o 'weak' plugins/adw/skills/test-application-handler/SKILL.md | wc -l
# до: 2 (оба вхождения на строке 183). После: не меньше 1 — содержание про слабый ассерт не урезано
# (форма `grep -c` считает СТРОКИ, а не вхождения, и дала бы 1: все совпадения на строке 183.
#  Прогон до отправки поймал это — правило F-136, восьмой раз за проход, и первый на единице счёта)
rtk proxy grep -rn 'adversarial\|evaluator\|change 00' plugins/adw/skills/
# до: одна строка (test-application-handler:183). После: пусто
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json' -o -name 'anchors.json'
# до: пусто. После: пусто — красная линия 2
```

## Что скажет warden

- **два файла**, и ни один из файлов с законными «cycle»/«orchestrator» не тронут;
- **ни одной ссылки на `§`, `WORKFLOW` или «dry-run» в каталоге не осталось** — это предъявляется грепом,
  и он же входит теперь в проверку любого прохода по каталогу;
- **замена не оказалась другой протечкой** — ни роли, ни номера изменения, ни имени прогона в новом тексте
  нет;
- **техника сильного ассерта цела** — правились обороты, а не рецепты;
- **тест правила применён** — получившиеся строки читаются как онбординг-документ;
- **числа рядом с командами** — каждая строка «Проверки» несёт «до» и «после» (правило раунда 1, F-156).
