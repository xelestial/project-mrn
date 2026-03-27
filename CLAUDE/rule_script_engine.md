# rule_script_engine.py

Role:
- Loads JSON rule scripts and executes safe, declarative actions for selected high-level events.
- Intended as a bridge toward more data-driven rules without replacing the engine with a full interpreter.

Supported default events:
- `landing.f.resolve`
- `fortune.cleanup.resolve`
- `game.end.evaluate`

Supported actions:
- `track_strategy_stat`
- `change_f`
- `change_shards`
- `set_result`
- `apply_same_tile_bonus`
- `evaluate_end_rules`
- `cleanup_burdens`


## v7.61 forensic patch notes
- Rule-script driven F changes now include the originating event name in `resource_f_change`.
