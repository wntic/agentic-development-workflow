# R00 — реструктуризация каталога скиллов. Согласованное решение

Решение человека, принято 2026-07-30 в диалоге. Этот файл — единственный дом решения; задачи R01–R03
его не пересказывают, а ссылаются.

Предыстория в двух строках: каталог откатан к 48 дослитийным скиллам (`1d72f0c`), потому что форма из
13 тем была решением мёртвого поколения — T08 сливал «по карте spec §7» с `gate.py` как оракулом
приёмки, и ни спеки, ни скрипта больше нет. Цена откката измерена в F-57.

## Канон, против которого нарезано

Из `code.claude.com/docs/en/skills`, сверено 2026-07-30:

- `description` + `when_to_use` обрезается на **1536 символах** в листинге.
- Листинг всех скиллов имеет **общий бюджет ≈1% контекстного окна**, и он общий со встроенными
  скиллами. При переполнении Claude Code **выбрасывает описания**, начиная с наименее вызываемых;
  имена остаются всегда.
- Тело: «Keep the body itself concise… every line is a recurring token cost. State what to do rather
  than narrating how or why.»
- Тело входит в контекст одним сообщением и **остаётся до конца сессии**. При авто-компакции
  сохраняются первые **5000 токенов** каждого вызванного скилла, общий бюджет **25 000**.
- Крупная тема канонически = `SKILL.md` как «overview and navigation» + файлы, подтягиваемые по нужде.
- Ловушка: `disable-model-invocation: true` **заодно** запрещает предзагрузку в сабагента.

## Что измерено на восстановленных 48

- Тела здоровые: медиана **145** строк, максимум **328**, свыше 500 — ни одного.
- Descriptions: сумма **30 508** символов. `test-discovery-invariants` (1668) сам за потолком 1536.
  В сессии 2026-07-30 два скилла пришли **без описания вообще** — документированное переполнение.
- Лексика мёртвых поколений: `manifest` 67 в 17 файлах, `graph` 56/16, `declares` 59/16,
  `scaffold` 43/9, «the spec» 27/19, `node` 19/3, `validator` 15/6, `runner` 12/4, `epic` 11/3.
  Концентрация: `conventions` 109, `restapi-app-bootstrap` 25, `test-discovery-invariants` 19,
  `meta-skill-author` 19, `meta-uc-author` 16.
- Четыре секции канонического тела — у 34 из 48. `Hard stops` есть во всех 48.

## Правило нарезки

**Гранулярно остаётся то, что типичное изменение добавляет или правит по одному. Сливается то, что
производится один раз на проект, либо всегда идёт комплектом.**

Слияние комплекта — выигрыш, а не потеря точности: одно срабатывание отдаёт роли всё, что ей и так
понадобится. Итог — **48 → 30**, и **ни одного тела свыше 500 строк** (максимум 494). Значит
supporting files не нужны нигде, каждый скилл остаётся одним `SKILL.md`, и дефект T08 — роутер-
конкатенация с указателем на topic-файл, который предзагрузка не тянет (F-10) — не воспроизводится.

### Тринадцать слияний

| Цель | Из чего | Строк тела после |
|---|---|---|
| `architecture` | general-layered-architecture + general-python-package + general-imports-conventions | 387 |
| `python-style` | general-typing-conventions + general-logging | 254 |
| `domain-model` | domain-entity + domain-value-object + domain-enum + domain-filter | 322 |
| `domain-ports` | domain-repository-protocol + domain-capability-protocol | 149 |
| `application` | application-command + application-query | 310 |
| `patterns` | pattern-compensating-tx + pattern-unit-of-work | 263 |
| `infra-persistence` | infra-sqlalchemy-repository + infra-sqlalchemy-table | 479 |
| `infra-wiring` | infra-settings + infra-di-provider | 295 |
| `restapi-app` | restapi-app-bootstrap + restapi-middleware | 437 |
| `restapi-route-contracts` | restapi-auth-dependency + restapi-error-responses | 175 |
| `testing-unit-domain` | test-domain-{entity,value-object,enum,service} | 388 |
| `testing-contract` | test-repository-contract + test-store-repository-contract | 353 |
| `testing-integration-setup` | test-integration-isolation + test-integration-authed-client | 494 |

### Семнадцать остаются как есть

`domain-service`, `domain-exception`, `infra-store-repository`, `infra-capability-adapter`,
`restapi-endpoint`, `restapi-schema`, `restapi-file-transfer`, `test-application-handler`,
`test-fake-repository`, `test-restapi-endpoint`, `test-discovery-invariants`,
`test-infra-capability-adapter`, `test-architecture-rule`, `test-principles`, `conventions`,
`meta-skill-author`, `meta-uc-author`.

## Безусловная часть — не зависит от нарезки

1. **Вычистить лексику мёртвых поколений.** Не косметика: скилл сообщает агенту, что существует
   манифест и граф узлов, которых нет. `conventions` дословно ссылается на удалённый генератор и на
   §16 несуществующей спеки; `meta-skill-author` называет путь `.claude/skills/`.
2. **Сжать descriptions до ~300 символов.** Ключевой сценарий вперёд; отрицательную маршрутизацию
   («Does not produce X — use Y») перенести в секцию `When to use vs. neighbours`, где ей и место.
   Цель — ~9 000 символов против 30 508, в 3,4 раза.
3. **Проставить `when_to_use` и `paths`.** Ни того, ни другого нет ни у одного из 48. `paths` даёт
   точную авто-активацию по глобу и стоит ноль строк enforcement.
4. **Вернуть четыре правила из F-57**, в первую очередь `@pytest.mark.ac("AC-n")`.

## Как роли получают скиллы

Смешанно, по признаку «всегда ли применяется» — опирается на замер вопроса 7 в `PLATFORM.md`
(авто-вызов внутри сабагента работает без поля `skills:`, если `Skill` есть в `tools:`).

- **Предзагрузка** — только сквозное, что действует всегда: `conventions`, `architecture`,
  `python-style` у implementer'а; `conventions`, `test-principles` у test-author'а.
- **Авто-вызов** — всё артефактное: роль подтягивает `domain-model` / `application` /
  `infra-persistence` / `restapi-endpoint` ровно тогда, когда производит этот артефакт.
- **`Skill` обязан быть в `tools:` каждой роли** — без него пути к скиллу нет вообще (замер 7,
  прогон 2), и это же точная форма F-04.

Стартовая цена implementer'а падает с девяти предзагруженных тел до трёх.

## Порядок

Два прохода, в этом порядке — решение человека.

| # | Задача | Что |
|---|---|---|
| R01 | вычистка | лексика + descriptions + `when_to_use` + `paths` на **48** файлах |
| R02 | слияния | 48 → 30 по таблице выше, плюс четыре правила F-57 |
| R03 | агенты | `skills:` по признаку выше, `Skill` в `tools:` |

Вычистка идёт первой, потому что её диff читаем и проверяется грепом, а слияние потом двигает уже
чистый текст — git видит перемещение, а не переписывание. Обратный порядок дал бы один нечитаемый
диff, в котором вычистка и слияние неразличимы; ровно так прошлый проход по скиллам получил слепое
переименование, испортившее фразу в `python-style`.

## Красные линии — сверка

- **РЛ 2 (бюджет enforcement = ноль).** Не нарушается: ни скрипта, ни хука, ни проверки формата.
  Пункты 1–4 — текст и frontmatter.
- **РЛ 1 (механизм только под измеренный провал).** `paths` и переход на авто-вызов — не новые
  механизмы, а поля платформы; оба под замеренным провалом (переполнение листинга; цена предзагрузки
  6810 против 1996 токенов).
- **РЛ 3 (воркфлоу не строит себя дольше, чем приложения).** Счёт: **две фичи** в `adw-probe` против
  одного прохода правок. Эта работа — второй проход, и после неё следующим действием идёт фича, а не
  правка воркфлоу.
- **РЛ 7 (мягкая деградация).** `paths` исчезнет → скилл станет активироваться шире, это деградация.
  Авто-вызов не сработает → роль не получит артефактного скилла; **это и есть слабое место выбора**,
  и оно принято сознательно: точность держится на `description`, а не на поле.
