# event_system.py

`EventDispatcher` provides a synchronous in-process event bus for game effect handling.

It now also supports an optional trace hook so semantic event emissions such as
`tile.purchase.attempt` or `rent.payment.resolve` can be recorded into the engine
action log without coupling the dispatcher to the logging backend.
