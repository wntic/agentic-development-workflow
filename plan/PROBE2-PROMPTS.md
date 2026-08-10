# Промпты первых изменений второй пробы — `adw-rooms`

Дев-запись, не шипится. Это **входы для интервью** `/adw:spec`, а не спеки: спеку пишет команда, задавая
вопросы, и её ответы — человека. Промпт задаёт предмет и границы, а не устройство.

Проба заведена 2026-08-04 пустой — три файла (`README.md`, `.gitignore`, `.claude/settings.json`),
плагин из каталога (`source: directory`). Субстрата нет намеренно: change 001 приносит пакетный корень,
оболочку приложения, wiring, тулчейн и `Makefile`. Почему это важно и что именно замеряет прогон 001 —
**F-165**: четыре механизма greenfield-пути (правило вертикального среза в `spec.md`, раздел про субстрат
`implementer.md:133`, шипящийся `templates/Makefile`, исключение шага 0 `build.md:52`) не исполнялись
как задуманы ни разу, потому что первая проба пред-заняла путь bootstrap-коммитом.

**Оговорка, без которой файл вреден.** Она без номеров намеренно: **каждый промпт, написанный до того,
как существует изменение перед ним** — а здесь такие все, и дописанные позже тоже, — к моменту, когда до
него дойдёт дело, встретит другую живую спеку. **Перечитай его против `specs/` и правь**, не вставляй
буквально. Это не осторожность, а прямая цитата из харнес-поста Anthropic, на котором стоит
красная линия 5: «errors in the spec would cascade into the downstream implementation», и их планировщик
сознательно избегает granular technical details.

**Ни одного идентификатора** — ни класса, ни модуля, ни таблицы — в промптах нет. Имена выбираются в
скелете и читаются из кода; `/adw:spec` их в `Design` запрещает прямо.

**Таблица ниже — прогноз, а не карта покрытия**: строку каждого изменения после прогона приводят к тому,
что случилось. 001 и 002 приведены, 003–005 — пока предсказание.

Куда это растёт и что каждое изменение трогает **впервые** (замерено по первой пробе: `domain-service`,
`patterns`, `StrEnum`, списки с пагинацией — ноль файлов):

| | что добавляет | чего касается впервые |
|---|---|---|
| 001 | бронь на интервал | greenfield-путь целиком, субстрат, `Makefile`, **`domain-service`** |
| 002 | отказ при пересечении | **стор** — exclusion-констрейнт и миграция; `409` как класс отказа, отличный от `422` |
| 003 | список броней за период | фильтры, пагинация, `Sequence[...]`, `*Result` |
| 004 | отмена брони | **`StrEnum`** и переходы состояний |
| 005 | уведомление о брони | **компенсирующая транзакция**, `ICan<Verb>`, вторая группа инфраструктуры |

Пятое изменение промпта пока не имеет — его предмет зависит от того, что покажут первые четыре.

---

## 001 — забронировать переговорку

```
/adw:spec Book a meeting room for an interval of time.

This is the project's first change, so it brings the substrate with it: the package root, the
application shell, the wiring, the toolchain and the Makefile. What I want proven end to end is one
behaviour, not a scaffold.

`POST /bookings` with a room identifier, a start instant and an end instant returns `201` and the
booking, including the identifier the service assigned it. `GET /bookings/{id}` returns `200` with the
same data — the room, the interval, and nothing the caller did not send except the identifier.

What I have already decided:

- an interval is **half-open**: it includes its start and excludes its end. Two bookings where one ends
  exactly when the other begins do not collide. I am stating this now because change 002 is about
  collisions and I do not want that rule invented there;
- the toolchain is laid at **`line-length = 120`**, written into `[tool.ruff]` explicitly rather than
  left to the default. That is a project-setup decision and this is the change that lays the project;
  I am telling you the number because the condition the house style names for choosing it — signatures
  and single-line comments colliding with the limit — cannot be observed on an empty project;
- instants are stored and returned in UTC, and the response reports them in the same form for every
  booking regardless of how the request wrote them;
- a room on this change is **just a value the caller supplies**. There is no room registry, nothing
  validates that the room exists, and two callers naming the same room mean the same room;
- an interval whose end is not strictly after its start is refused with `422` and nothing is stored;
- the booking outlives the process: it is in PostgreSQL, not in memory, and a second instance of the
  application reports it.

Out of scope, deliberately: no overlap checking at all — two bookings of the same room at the same time
are both accepted on this change, and change 002 is where that stops. No cancellation, no listing, no
room registry, no users or authentication, no notification, no recurring bookings, and no audit
timestamps in the response.

What I have not decided and want you to ask me: what the identifier of a booking looks like to a caller;
whether a bookable interval has a maximum length and what happens past it; whether a booking that starts
in the past is refused or accepted; and what exactly a malformed instant answers, given that the refusal
for a backwards interval is a domain rule rather than a schema constraint.
```

---

## 002 — пересечения отклоняются

```
/adw:spec Refuse a booking that collides with one the room already has.

Today two callers can book the same room for the same hour and both get `201`. That stops here: a
request whose interval collides with an existing booking of that room is refused, and nothing is stored.

What I have already decided:

- **half-open intervals decide collision**, as change 001 established: bookings that merely touch —
  one ending exactly when the next begins — do not collide and are both accepted. This boundary is the
  point of the change, not a detail;
- collision is **per room**: the same interval in a different room is accepted, and the refusal names
  neither the colliding booking's identifier nor who made it;
- a refusal leaves the existing booking exactly as it was, and the refused interval stays bookable —
  nothing is reserved by a failed attempt;
- containment, partial overlap on either side, and identical intervals are all collisions. A booking
  strictly inside another is refused just as one that straddles its end is.

Out of scope: no cancellation, so there are no cancelled bookings to exclude from the check yet — when
cancellation arrives it will have to say whether a cancelled booking still blocks, and that is that
change's decision, not this one. No waiting list, no suggesting a free slot, no partial acceptance, no
moving an existing booking out of the way.

What I have not decided and want you to ask me: which status code a collision answers, and whether the
body says anything beyond that it collided; and what two callers submitting the same slot at the same
instant are guaranteed — I want the options named with what each costs, including whether that guarantee
can be proven by a test in this suite at all or only by a live run.
```

---

## 003 — список броней за период

```
/adw:spec List the bookings of a room over a period.

A caller who has a room and a week wants to see what is booked in it. `GET /bookings` with a room and a
window returns `200` and the bookings of that room touching that window, in a stable order, together
with enough information to page through them.

What I have already decided:

- the window is a filter, not a slice: a booking that **starts before the window and ends inside it**
  belongs in the answer, and so does one that starts inside and ends after. A booking that merely
  touches the window's edge follows the same half-open rule as everything else in this service;
- the order is by start instant, ascending, and it is **stable**: two bookings with the same start come
  back in the same order on every call;
- a window with nothing in it answers `200` and an empty collection — never `404`;
- the room is required. There is no "all rooms" listing on this change.

Out of scope: no free-slot search, no grouping by day, no cursor into the future beyond the window
asked for, no sorting by anything but the start instant, no filtering by who booked it, and no listing
of rooms.

What I have not decided and want you to ask me: how paging is expressed and what a caller learns about
how much is left; whether there is a ceiling on how many bookings one call may return and what asking
for more does; whether the window has a maximum span; and whether the response repeats the same shape
`GET /bookings/{id}` returns or a narrower one — and if narrower, what a caller loses.
```

---

## 004 — отмена брони

```
/adw:spec Cancel a booking, and stop it holding its slot.

A booking can be cancelled while it still matters, after which it no longer holds its interval: the slot
it occupied becomes bookable again, and the booking itself remains readable as cancelled rather than
vanishing.

What I have already decided:

- a cancelled booking **stops colliding**. The rule change 002 established now reads against live
  bookings only, and the interval a cancelled booking held is accepted for a new booking;
- the booking is not deleted. Reading it still answers `200`, and what it answers says it is cancelled —
  a caller can tell a cancelled booking from one that never existed;
- cancelling is about the booking's own state and nothing else: the interval, the room and the
  identifier do not change;
- the state a booking is in is part of what a read reports, so this change makes visible something that
  had no representation before.

Out of scope: no restoring a cancelled booking, no reason or comment attached to a cancellation, no
record of who cancelled it or when, no automatic cancellation of anything, and no notification.

What I have not decided and want you to ask me: what cancelling a booking twice answers, and what
cancelling one that never existed answers — I want those two treated as one decision, because together
they decide whether the answer tells a caller what the service holds; whether a booking whose interval
has already passed can be cancelled at all; and whether the listing from change 003 shows cancelled
bookings by default, hides them, or takes that as a filter.
```

---

## Порядок работы

Один промпт — один прогон целиком: `/adw:spec` → `/adw:build` → `/adw:accept`, и только потом следующий.
Два действия человека, которых не заменяет ничто: **прочитать оба диффа на приёмке** и, если разбирается
прогон, читать отчёт `run-report` (с 2026-08-04 установлена 1.1.2 — считает запуски инструмента, а не
вызовы `Bash`).

Первая проба потеряла человека именно здесь: приёмки проходили, диффы не читались, и §11.6 —
«измеренный разрыв между тем, что написал агент, и тем, что человек написал бы сам» — остался без
источника. Шаг 5 §10 (харвест скиллов из живого кода) открывается, когда такой разрыв будет записан
впервые.
