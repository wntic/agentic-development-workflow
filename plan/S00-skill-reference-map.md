# S00 — отображение имён и форма указателя. Решение, не задача

Тип: **решение человека, записанное один раз.** Ни один файл `plugins/adw/` этой записью не правится.
Слой: дев-запись.
Происхождение: просев каталога 2026-07-30 (см. `FINDINGS.md`, находки этого прохода).

Задачи S01–S03 обязаны брать отображение и форму **отсюда**. Если каждая выведет их сама, получится
тринадцать способов написать одно правило — та же болезнь, от которой в каталоге есть правило
«деривация живёт в одном доме».

---

## Что случилось

Каталог сжали с ~40 тем до 13. Тела слили, а **имена не подмели**: сегодня в `plugins/adw/skills/`
лежит ~230 ссылок на скиллы, которых не существует, плюс 12+ авторских маркеров `<!-- merged from … -->`
прямо в телах, которые правило 8 `meta-skill-author` запрещает.

Почему это хуже остатков `gate`: правило 5 каталога требует cross-cutting правила **ссылаться, а не
пересказывать**. Значит висячий указатель — не путаница, а **отсутствие правила**: единственный
носитель знания об упаковке в `domain-model` — это указатель, и он ведёт в никуда.

## Отображение: старое имя → сегодняшний адрес

| Старое имя | Адрес сегодня |
|---|---|
| `general-python-package` | `architecture`, раздел про механику пакетов |
| `general-layered-architecture` | `architecture`, раздел про четыре слоя |
| `general-imports-conventions` | `architecture`, раздел про импорты |
| `general-typing-conventions` | `python-style`, раздел про типизацию |
| `general-logging` | `python-style`, раздел про логирование |
| `domain-entity`, `domain-value-object`, `domain-enum`, `domain-filter`, `domain-exception(s)` | `domain-model` (монолит, разделы по артефактам) |
| `domain-repository-protocol`, `domain-capability-protocol`, `domain-protocols` | `domain-ports` |
| `application-command` | `application`, `command.md` |
| `application-query` | `application`, `query.md` |
| `pattern-compensating-tx` | `application`, `compensating-tx.md` |
| `pattern-unit-of-work` | `application`, `unit-of-work.md` |
| `infra-sqlalchemy-repository` | `infra-persistence`, `repository.md` |
| `infra-sqlalchemy-table` | `infra-persistence`, `table.md` |
| `infra-store-repository` | `infra-persistence`, `store-repository.md` |
| `infra-capability-adapter` | `infra-integration`, `adapter.md` |
| `infra-di-provider` | `infra-integration`, `container.md` |
| `infra-settings` | `infra-integration`, `settings.md` |
| `restapi-endpoint` | `restapi`, `endpoint.md` |
| `restapi-schema` | `restapi`, `schema.md` |
| `restapi-auth-dependency` | `restapi`, `auth-dependency.md` |
| `restapi-error-responses` | `restapi`, `error-responses.md` |
| `restapi-app-bootstrap` | `restapi`, `bootstrap.md` |
| `restapi-file-transfer` | `restapi`, `file-transfer.md` |
| `test-domain-entity` | `testing-unit`, `entity.md` |
| `test-domain-value-object` | `testing-unit`, `value-object.md` |
| `test-domain-enum` | `testing-unit`, `enum.md` |
| `test-application-handler` | `testing-unit`, `handler.md` |
| `test-fake-repository` | `testing-unit`, `fake.md` |
| `test-architecture-rule` | `testing-unit`, `architecture-rule.md` |
| `test-restapi-endpoint` | `testing-integration`, `endpoint.md` |
| `test-repository-contract` | `testing-integration`, `repository-contract.md` |
| `test-store-repository-contract` | `testing-integration`, `store-repository-contract.md` |
| `test-discovery-invariants` | `testing-integration`, `discovery.md` |

**Два имени решаются контекстом, а не похожестью.** `domain-service` — это и раздел `domain-ports`
(сам сервис), и `testing-unit/domain-service.md` (тест на него); `test-domain-service` — только
второе. Решает то, о чём просит цитирующая фраза: пишем сервис или тест на сервис.

**Не отображать, оставить как есть:**
- `python-multipart` — пакет PyPI, не скилл (ловушка F-48: похожесть имени не признак);
- `infra-read-model` — сознательная ссылка на будущий скилл в `CONVENTIONS.md`; её судьба решается
  вместе с этим файлом в S03, а не отображением.

## Форма указателя: четыре случая, одно правило

Выведена из замеров, а не выбрана: предзагружается **только `SKILL.md`** темы, топик-файлы рядом — нет
(`PLATFORM.md`, вопрос 1); F-10 замерила, что читатель **открывает** топик-файлы тех тем, что у него
предзагружены; и скилл не имеет права знать, кто его читает, значит не может знать, лежит ли цель в
контексте.

| Случай | Форма |
|---|---|
| раздел этого же файла | `→ §<Заголовок> ниже` (или `выше`) |
| монолитная тема (`architecture`, `python-style`, `conventions`, `domain-model`, `domain-ports`) | ``→ `architecture` §<Заголовок>`` |
| топик-файл чужой темы | ``→ `restapi`, `endpoint.md`` ` |
| роутер → свой топик | ``→ **read `endpoint.md` now**`` — **не меняется** |

Одно правило: **указатель всегда квалифицирован темой, кроме случая «этот же файл».**

Почему третий случай именно такой: топик-файл не инжектируется никому, даже при предзагрузке темы.
Читатель, у которого тема есть, открывает файл; читатель, у которого нет, вызывает скилл, получает
роутер, и роутер своим императивом присылает его в тот же файл. Обе ветки ведут в одно место — это
литмус мягкой деградации (красная линия 7), а не удобство.

Почему четвёртый не меняется: там императив обоснован **измеренным** режимом отказа — мягкая ссылка
оставляет агента писать артефакт по краткому изложению роутера. Менять то, что обосновано замером,
из соображений единообразия — регресс.

## Дом правила

Правило о форме указателя живёт в **`meta-skill-author`** и больше нигде. S03 сливает его туда вместе
с содержимым `CONVENTIONS.md`; до S03 задачи S01–S02 применяют его по этому файлу.

## Границы этого решения

- Отображение — **только переименование адреса**. Ни одно правило по существу не меняется, ни один
  шаблон не переписывается, ни одна тема не делится и не сливается.
- Тексты, на которые указатель ведёт, не переносятся между темами. Если указатель ведёт в тему, где
  нужного раздела нет, это **находка**, а не повод перенести текст.
- Ни скрипта для массовой замены, ни файла состояния. Замена делается чтением каждого сайта: формы
  разные (маршрутный пункт, Out of scope, императив, мягкая ссылка), и слепой `sed` их не различает.
