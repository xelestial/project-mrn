# test_event_effects.py

Covers event registration, override hooks, and semantic event trace logging.

The semantic trace assertions verify that event-bus emissions such as
`tile.purchase.attempt` and `game.end.evaluate` are recorded into `action_log`
when engine logging is enabled.
