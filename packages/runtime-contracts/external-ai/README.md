# External AI HTTP Contract

This directory freezes the server-to-worker HTTP contract for `external_ai` participants.

## Scope

- `request`: canonical decision request envelope sent from the runtime server to an external AI worker
- `response`: canonical choice response returned by that worker

## Notes

- `legal_choices` is the authoritative choice list.
- The worker should respond with one `choice_id` from that list.
- Runtime timeout / retry / fallback policy remains owned by the server seat descriptor.
