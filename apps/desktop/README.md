# MRN Desktop

Electron shell for the dedicated MRN client.

## Development

1. Start the renderer dev server:
   - `cd ../web && npm run dev -- --host 127.0.0.1 --port 9000`
2. Start Electron:
   - `npm run dev`

## Production build

- `npm run dist`

The packaged app loads the built renderer from `../web/dist`.
