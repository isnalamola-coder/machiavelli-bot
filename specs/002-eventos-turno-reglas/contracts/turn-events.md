# Contract: Turn events, persistence and reporting

## Domain API

```python
type FrozenJSONValue = (
    None | bool | int | float | str |
    tuple["FrozenJSONValue", ...] |
    Mapping[str, "FrozenJSONValue"]
)

@dataclass(frozen=True, slots=True)
class TurnEvent:
    type: EventType
    data: Mapping[str, FrozenJSONValue]

    def to_json(self) -> str: ...

    @classmethod
    def from_persisted(
        cls,
        *,
        row_id: int,
        event_type: str,
        data_json: str,
    ) -> "TurnEvent": ...
```

Construction validates the exact payload table from `spec.md` together with FR-001
and FR-006; FR-007 applies specifically to removing types without a current producer.
It copies the input and recursively freezes mappings with `MappingProxyType` and
lists with `tuple`. The frozen dataclass rejects reassignment of `type` and `data` with
`FrozenInstanceError`; mutating the caller's original objects cannot change an event,
and the public tree rejects nested mutation. `to_json()` recursively materializes fresh
native dictionaries and lists before serialization. Loading parses a JSON object and
invokes the same constructor. Unknown types, malformed JSON, non-object payloads,
missing/extra keys or invalid nested values raise `InvalidTurnEventError`; persisted
failures expose `row_id` and raw `event_type` and chain the original error.

`TurnEvent.military_resolution(...)` remains the canonical adapter from military
primitives and delegates to the same validation. `TurnEvent.expense(...)` may remain
as a convenience only for the three expense types and `bribe_executed`; it cannot
bypass validation.

## Game aggregate

```python
turn_events: list[TurnEvent]

def add_event(self, event: TurnEvent) -> None: ...
```

`add_event` appends the event object without serializing or rendering it. No public
path may append `str`, Markdown or a `type|json` record.

At entry to `GameEngine.run()`, the list is replaced exactly once with an empty
list. Producers append in execution order. A failed service call does not save the
mutated instance.

## Rollout invariant

The closed `EventType` catalog, all producers, `Game.turn_events`, `add_event()`,
save/load and SQLite v4 are one vertical cut. There is no supported intermediate
checkpoint with removed enum values or `to_record()` still required by a consumer,
with typed events written to SQLite v3, or with the v4 schema read as `message`.
Tests for every affected boundary are prepared first and the complete cut must return
the product to a green state before reporting or scenario-rule work begins.

## SQLite v4

```sql
CREATE TABLE game_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    data_json TEXT NOT NULL,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE
);
```

The v4 upgrade uses one explicit SQLite transaction containing, in this order,
`DROP TABLE game_events`, `CREATE TABLE game_events (...)`, and
`PRAGMA user_version = 4`. The implementation must use transaction-preserving
statements rather than an `executescript()`/outer-version-write sequence that could
commit the schema before the version. Only after all three operations succeed may it
commit. A failure after `DROP`, after `CREATE`, or before commit rolls back to the v3
table, rows, and `user_version=3`; games, players and commands are never dropped.

Save contract:

1. Delete rows for the game inside the aggregate transaction.
2. Insert `(game_id, event.type, event.to_json())` in list order.
3. Commit together with game/player/command state.

Load contract:

1. Select `id, event_type, data_json` by `game_id ORDER BY id ASC`.
2. Build each event with `TurnEvent.from_persisted`.
3. Abort the aggregate load on the first corrupt row; never skip it.

## Reporting API

```python
class TurnReporter:
    @staticmethod
    def generate(game: Game) -> list[str]: ...
```

The method is read-only and returns:

```text
game/turn header
season/year header
zero or more event lines, in persisted order
current situation header and lines
```

Every `EventType` has a non-empty Spanish representation. Known identifiers become
public names or `<@discord_id>` mentions. Unknown identifiers are passed through
`discord.utils.escape_markdown(value, as_needed=False)` and then
`discord.utils.escape_mentions(value)` before display. Inputs such as `@everyone`,
`@here`, `<@123>`, backticks, asterisks, underscores, pipes, and backslashes remain
inert; only a known `discord_id` may create a real mention. Raw JSON, Python class
names and tracebacks are never rendered.

For `military_resolution`, each item produces its own line under these non-empty
groups, in order: results, cancelled orders, broken convoys, dislodgements,
rebellions and sieges. Empty groups are omitted; no item is summarized away. When
all six groups are empty, the event remains valid and produces exactly one line:
`Sin cambios militares.`

## Application service and session

```python
@contextmanager
def game_service_session(db_path: str | Path) -> Iterator[GameService]: ...

class GameService:
    def run_turn(self, channel_id: int) -> list[str]: ...
    def get_turn_report(self, channel_id: int) -> list[str]: ...
```

The session uses `DatabaseManager` and always closes its connection. `run_turn`
performs `load -> GameEngine.run -> TurnReporter.generate -> repository.save` in one
worker. It exposes no dislodgement resolver. `get_turn_report` loads and renders the
persisted typed sequence.

Discord imports the service API, not `sqlite3` or repositories. `run_game` delegates
the complete synchronous call once through `asyncio.to_thread`; chunking and sends
remain in Discord. A synchronized asynchronous test blocks the worker with a
`threading.Event` and proves that a witness coroutine completes before the worker is
released, demonstrating actual event-loop availability without timing thresholds.

## Public failure behaviour

`run_game` and `game_report` catch `InvalidTurnEventError`, log its row/type context
and respond ephemerally with an actionable Spanish message equivalent to:

```text
No se pudo generar el informe porque el historial del turno no es válido.
Comunícaselo al administrador para que revise los eventos guardados.
```

The message contains no row data, JSON, exception name or traceback. Existing
military error translations remain unchanged.

## Scenario-rule boundaries

- Setup validates inactive-fortress garrisons before emitting events or assigning
  powers.
- Interaction services hide disabled famine/assassination actions; the expenditure
  processor also discards persisted stale commands without charging or emitting.
- Disaster public methods are no-ops when their controlling rule is false.
- `GameEngine` decides the phase timing for first-turn and seasonal famine and skips
  assassination resolution when disabled.
- Military, rebellions and campaign target generation use the same scenario helper
  for defendable cities.
- Income, home-country control, victory and recruitment continue to exclude
  `fortress` regardless of `fortress_active`.
