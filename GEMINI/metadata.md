# metadata.py

Project metadata constants.

- `GAME_VERSION`: current packaged version string.
- `RELEASE_DATE`: release date for the current package.
- `GAME_VERSION_NOTE`: short human-readable note describing the main intent of the release.

For v0.7.54 the note highlights the new semantic event-bus trace logging that records emitted event names with summarized context/results into `action_log` when logging is enabled.


## 0.7.55 update
- `GAME_VERSION` and `VERSION.txt` now point to `0.7.55`.
- The current note summarizes the new metadata registry, action log schema, and board layout schema docs.

- 0.7.56: control/profile intent retune for mark-profit and token-placement execution.


## 0.7.57
Victory token rules updated: purchase placement(1 coin max), revisit remains up to 3, lap rewards become coins 3 vs shards 3 vs cash 5.


## 0.7.58
- Added rule injection stage 1 (`game_rules.py`).


Current version 0.7.59 introduces external ruleset loading for injected GameRules.


## 0.7.60 note
Version `0.7.60` corresponds to rule injection stage 3.


### 0.7.61
Version 0.7.61 marks rule-injection stage 4: structural board metadata is separated from numeric ruleset metadata.
