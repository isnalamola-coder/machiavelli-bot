# Phase 5 audit — scenario rule gates

## Characterization barrier: T031 and T048

The pre-gate phase suite was recorded with the repository Python 3.13 environment:

```text
./.venv/Scripts/python.exe -m pytest -q \
  tests/machiavelli/game/test_scenario.py \
  tests/machiavelli/services/test_player_interaction_service.py \
  tests/machiavelli/engine/test_setup.py \
  tests/machiavelli/engine/test_core.py \
  tests/machiavelli/engine/test_disasters.py \
  tests/machiavelli/engine/test_expenditure.py \
  tests/machiavelli/engine/test_income.py \
  tests/machiavelli/engine/test_maintenance.py \
  tests/machiavelli/engine/test_control.py \
  tests/machiavelli/engine/test_rebellions.py \
  tests/machiavelli/engine/test_military.py
```

Original baseline result: `197 passed, 1 skipped, 84 subtests passed`.

`tests/machiavelli/engine/test_core.py` now contains literal, deterministic and
versioned snapshots for startup, maintenance and campaign with all five rules active,
including `first_turn_famine=True`. The same constants are consumed by both the T031
characterization test and the T048 regression test; no expected value is derived
from the observed execution.

Each snapshot records exactly:

- the five rule values and final `turn_number`;
- famine, independent garrisons and active sieges;
- every player identifier, Discord identifier, assigned power, controlled provinces,
  home countries, armies, fleets, garrisons, assassination counters, ducats and
  rebellions;
- effective commands immediately before `Game.advance_turn()` performs its normal
  cleanup, plus the empty post-turn command collections;
- the complete ordered event sequence and deterministic JSON payload of every event.

The fixture uses real `Game`, `Player`, `Scenario`, `SetupManager`,
`MaintenanceResolver`, `ExpenditureProcessor`, `MilitaryResolver`, `ControlManager`,
`IncomeManager` and disaster logic. Only the disaster tables and RNG are fixed so the
literal expected values remain reproducible. The active startup snapshot explicitly
contains the initial `famine_spawn`; the campaign snapshot covers conversion into an
active fortress garrison, famine attrition and cleanup, plague spawn and death.

The existing isolated characterizations still protect the permanent exclusion of
`fortress` from urban income, home-country retention, victory city counts and
recruitment.

## Integrated rule matrix: T049

`test_each_inactive_rule_has_exact_integrated_state_and_event_order` executes the same
real domain fixture once for each inactive rule:

- `fortress_active=False`;
- `assassinations_active=False`;
- `famine_active=False`;
- `first_turn_famine=False`;
- `plague_active=False`.

For every case, the test compares a literal snapshot both before execution and after
the complete startup → maintenance → campaign sequence. It also compares the full
ordered event-type sequence, checks that the rule's prohibited event types are absent,
and verifies that removing those prohibited types from the active sequence preserves
the exact relative order of all remaining phases. The three active flows are rerun in
the same matrix using the unchanged T031 expectations.

## Corrected branch coverage

- **T034**: setup uses real `Player` instances and proves every player finishes with
  `ass_counters == []` while retaining the expected power, units, home countries and
  controlled provinces.
- **T036**: interaction tests now cover the positive active-fortress paths for a
  garrison actor, the siege command, conversion and an urban-rebellion target, while
  retaining the no-recruitment rule.
- **T038**: stale `E A` and `E E` commands are placed between two valid expenses; the
  test proves the remaining commands preserve FIFO order, exact costs, final balance
  and exact event order without an event for the disabled command.
- **T044**: active-fortress pacification removes the urban rebellion and emits the
  exact `rebellion_pacify` payload; the inactive counterpart preserves state and emits
  nothing.

## Final military collection validation: T047

`MilitaryResolver._validate_final_collections()` now validates every owned and
independent garrison destination through the scenario's defensible-city helper before
commit. A garrison in `city=None`, an ordinary `city`, or an inactive `fortress` is
rejected.

The same helper is applied before appending a type-`G` retreat destination.
`test_final_garrison_collections_reject_non_defensible_destinations_atomically` covers
all six owned/independent combinations, and
`test_garrison_retreat_rejects_non_defensible_destination_before_append` covers all
three invalid destination kinds. Every case compares the complete military snapshot
and proves no state or event remains after failure.

## Final verification

- Phase-specific suite: `241 passed, 1 skipped, 93 subtests passed`.
- Full suite: `513 passed, 1 skipped, 97 subtests passed`.
- `ruff format --check` on the modified Python files: green.
- `ruff check` on the modified Python files: green.
- `mypy machiavelli`: `Success: no issues found in 39 source files`.

The full run reports 59 pre-existing `discord.utils` deprecation warnings. No test
failure or new rule-gate warning remains.
