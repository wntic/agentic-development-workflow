# S02 — роутеры и их топик-файлы, пять тем

Тип: правка каталога. Слой: **ядро**.
Отображение и формы — **`plan/S00-skill-reference-map.md`**. Обоснование операции — `S01`, не повторять.

Читать сначала:
- `plan/S00-skill-reference-map.md`
- каждый правимый файл целиком перед его правкой
- `plan/FINDINGS.md`: F-45 (остатки «гейта»), F-48 (список слов — не признак)

`testing-unit` в эту задачу **не входит** — он целиком принадлежит S04, чтобы ни один файл не правился
двумя задачами. Именно так возникла регрессия F-36: два прохода по одному шву в разное время.

## Deliverables

Пять тем, 24 файла. Операция та же, что в S01: фантомные ссылки → адреса по S00, маркеры
`<!-- merged from … -->` снять, названные ниже остатки третьего захода — по месту.

| Тема | Файлы | Строк с фантомами | Маркеров |
|---|---|---|---|
| `application` | `SKILL.md`, `command.md`, `query.md`, `unit-of-work.md`, `compensating-tx.md` | 17 | 4 |
| `infra-persistence` | `SKILL.md`, `repository.md`, `store-repository.md`, `table.md` | 20 | 3 |
| `infra-integration` | `SKILL.md`, `adapter.md`, `container.md`, `settings.md` | 16 | 3 |
| `restapi` | `SKILL.md` + 7 топиков | 26 | 7 |
| `testing-integration` | `SKILL.md` + 7 топиков | 25 | 7 |

Именованные сайты, каждый читается и правится отдельно:

1. **`infra-persistence/SKILL.md:3` — единственная разрешённая правка фронтматтера во всём проходе.**
   `description` несёт «the Alembic revision discipline **the implementer owns**» — имя роли в тексте,
   который платформа показывает в листинге каждой сессии. Замена: формулировка, которая **уже лежит в
   `when_to_use` этого же файла** — «the Alembic revision discipline **that pairs with a schema
   change**». Пересчитать сумму `description` + `when_to_use`: должна остаться ≤1536 (сейчас 481).
2. **`infra-persistence/SKILL.md:26`** — «Phrased for the **spec-author / test-author** reader» → снять
   адресата: правило про `ConflictError` действует независимо от того, кто читает.
3. **`infra-integration/adapter.md:88` и `:218`** — «the no-silenced-types **gate** forbids it» и «the
   **`/verify`** no-silenced-types gate greps for it». `/verify` — команда третьего захода, её нет.
   Назвать то, что действительно ловит: `mypy` сообщает, инлайновый `ignore` прячет.
4. **`restapi/error-responses.md:45`** — «fails **the gate** with an extra `422`» → инвариант
   discovery-теста, который реально существует (`testing-integration`, `discovery.md`). И вычеркнуть
   провенанс чужого проекта: «*(Surfaced when **mm**'s first real integration run flagged …)*».
5. **`testing-integration/SKILL.md:106`** — худший абзац каталога, четыре ссылки на снесённое в одном
   месте: «The change cycle's **gate** carves out…», «the gate's **own probe**», «(spec **§5.1**, ruling
   on **T04b**)», «turns the whole gate permanently **RED**». Спеки §5.1 и задачи T04b не существует.
   Оставить **инвариант без машины**: страж окружения обязан `skip`, а не `raise`, потому что падающая
   фикстура делает весь ярус красным на машине без демона Docker. Ни гейта, ни инвентаря, ни ссылки на
   чужой документ.
6. **`testing-integration/discovery.md:47`** — «before any **implementer** runs» → «до того, как
   появятся тела».

## Границы

- Правила по существу не меняются; шаблоны кода, примеры и `Hard stops` — не трогать.
- Фронтматтер трогается **ровно в одном файле** — `infra-persistence/SKILL.md`, поле `description`, по
  пункту 1. Во всех остальных 23 файлах фронтматтер побайтово неизменен.
- Императивы роутера к своим топикам (`→ **read `endpoint.md` now**`) **не менять** — они обоснованы
  измеренным режимом отказа (S00, четвёртый случай).
- Текст между темами не переносится. Указатель ведёт туда, где раздела нет → находка, не перенос.
- `testing-unit` не трогать (S04). `CONVENTIONS.md` и `meta-skill-author` не трогать (S03). Пять
  монолитов не трогать (S01).
- Не трогать `restapi/auth-dependency.md:7` («routes an authed app **gates**» — законный глагол) и
  `python-multipart` (пакет PyPI, не скилл). Ловушка F-48.
- Ни скрипта, ни массовой замены по дереву.

## Проверка

Тема за темой, коммит на тему допустим:

- `grep -rE '`(general|domain|infra|test|testing|restapi|application|pattern)-[a-z-]+`'` по 24 файлам →
  ноль, кроме имён тринадцати существующих тем.
- `grep -r '<!-- merged from'` по 24 файлам → ноль.
- `grep -rn '/verify\|§5\.1\|T04b\|\bmm\b'` по 24 файлам → ноль.
- `grep -rnE '\b(implementer|test-author|test-review|evaluator|coordinator)\b'` по 24 файлам → ноль,
  включая фронтматтер `infra-persistence`.
- `description` + `when_to_use` у `infra-persistence` ≤1536; у остальных 23 файлов фронтматтер в
  `git diff` не появляется.
- Абзац `testing-integration/SKILL.md:106` читается как правило про `skip`, и в нём нет слов `gate`,
  `RED`, `inventory`, `baseline`, `spec §`.
- Ни одного `.py`, `.sh`, `hooks.json`, `anchors.json`.

## Что скажет warden

- «Гейт» заменён на «наш чек» / «проверка цикла» → ОТКЛОНИТЬ: машина просто переименована, а не
  заменена инвариантом.
- Инвариант про `skip` дописан, а ссылка на T04b/§5.1 осталась → ОТКЛОНИТЬ.
- Правка фронтматтера в файле, которого нет в пункте 1 → ОТКЛОНИТЬ.
- Императив роутера превращён в мягкую ссылку «for consistency» → ОТКЛОНИТЬ: это регресс против
  замера.
- Тронут `testing-unit`, `CONVENTIONS.md`, `meta-skill-author` или любой из пяти монолитов →
  ОТКЛОНИТЬ.
- Провенанс `mm` оставлен «как исторический» → ОТКЛОНИТЬ: имя чужого проекта в шипящемся файле не
  значит ничего для читателя и врёт про происхождение правила.
