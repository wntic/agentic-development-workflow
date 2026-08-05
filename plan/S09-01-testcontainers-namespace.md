# S09-01 — три импорта `testcontainers` переезжают в `community`

Тип агента: **`adw-builder`**
Слой: **ядро** (`plugins/adw/skills/testing-integration-setup/SKILL.md`,
`plugins/adw/skills/testing-contract/SKILL.md`)
Происхождение: решение человека 2026-08-05, `plan/FINDINGS.md`, секция «Решения человека, 2026-08-05 —
три замечания по коду второй пробы», строка **F-167**.

Читать сначала:
- в `plan/FINDINGS.md` — тело **F-167** заголовочным грепом
  (`rtk proxy grep '^## F-' plan/FINDINGS.md`, потом читать только эту запись);
- `plugins/adw/skills/testing-integration-setup/SKILL.md`, шаблон `tests/integration/conftest.py` —
  фикстуры `postgres_container` (строка ~81) и `minio_container` (~102);
- `plugins/adw/skills/testing-contract/SKILL.md`, шаблон conftest клиентского стора — фикстура
  `qdrant_url` (~208).

Основание замерено на `.venv` второй пробы, `testcontainers 4.15.0`:

```
testcontainers.postgres -> DeprecationWarning: use testcontainers.community.postgres instead
testcontainers.qdrant   -> DeprecationWarning: use testcontainers.community.qdrant instead
```

Плоский модуль — шим из шести строк: он реэкспортирует из `testcontainers.community.<x>` и
предупреждает. Устарел **весь плоский слой**, а не отдельный модуль, поэтому и `minio` тоже.

## Задача

Три импорта, ни одной строки прозы:

| файл | строка | было | стало |
|---|---|---|---|
| `testing-integration-setup/SKILL.md` | ~81 | `from testcontainers.postgres import PostgresContainer` | `from testcontainers.community.postgres import PostgresContainer` |
| `testing-integration-setup/SKILL.md` | ~102 | `from testcontainers.minio import MinioContainer` | `from testcontainers.community.minio import MinioContainer` |
| `testing-contract/SKILL.md` | ~208 | `from testcontainers.qdrant import QdrantContainer` | `from testcontainers.community.qdrant import QdrantContainer` |

Имена классов не меняются — шим реэкспортирует их под теми же именами, это замерено импортом.

## Deliverables

Два файла, три изменённые строки. Больше ничего.

## Границы

- **Только эти два файла.** Флор версии в списке dev-зависимостей — задача **S09-02** (файл
  `conventions/SKILL.md`), не заходи туда.
- **`conventions/SKILL.md:328` не трогать вовсе** — там `testcontainers.*` стоит как **глоб в
  `[tool.mypy] module`**, и он покрывает `testcontainers.community.*` без правки. Это не импорт.
- **Прозу про testcontainers не переписывать** — `testing-contract:43`, `:320`,
  `test-principles:30`, `:194` называют инструмент, а не путь модуля. Они верны как есть.
- Пины образов (`postgres:17-alpine`, `minio/minio:RELEASE.…`, `qdrant/qdrant:v1.12.4`) и комментарии
  рядом с ними не трогать.
- Не чинить найденное по дороге — находка в `plan/FINDINGS.md` пишется главной сессией, не тобой.

## Проверка

```bash
git diff --stat -- plugins/adw/skills/            # ровно два файла
rtk proxy grep -rn 'from testcontainers\.' plugins/adw/
# ровно три строки, и в каждой путь начинается с testcontainers.community.
rtk proxy grep -rn 'PostgresContainer\|MinioContainer\|QdrantContainer' plugins/adw/
# имена классов на местах, по два вхождения на каждый (импорт + конструктор)
rtk proxy find plugins/adw -name '*.py' -o -name '*.sh' -o -name 'hooks.json'   # пусто
```

## Что скажет warden

- **основание измерено** — предупреждение рантайма приведено дословно, с версией пакета;
- **механизмов ноль** — три строки в шаблонах;
- **флор версии не тронут** — он принадлежит другой задаче, и `conventions` не в этом диффе;
- **глоб mypy не спутан с импортом** — `conventions:328` остался как был.
