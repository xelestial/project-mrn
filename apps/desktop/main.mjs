import { app, BrowserWindow, Menu, shell } from "electron";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

function rendererEntry() {
  const devUrl = process.env.MRN_ELECTRON_DEV_SERVER_URL;
  if (typeof devUrl === "string" && devUrl.trim()) {
    return { kind: "url", value: devUrl.trim() };
  }
  return {
    kind: "file",
    value: path.resolve(__dirname, "../web/dist/index.html"),
  };
}

async function createMainWindow() {
  const window = new BrowserWindow({
    width: 1600,
    height: 1000,
    minWidth: 1280,
    minHeight: 800,
    autoHideMenuBar: false,
    backgroundColor: "#071225",
    webPreferences: {
      preload: path.resolve(__dirname, "preload.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  window.webContents.setWindowOpenHandler(({ url }) => {
    void shell.openExternal(url);
    return { action: "deny" };
  });

  const entry = rendererEntry();
  if (entry.kind === "url") {
    await window.loadURL(entry.value);
    window.webContents.openDevTools({ mode: "detach" });
    return window;
  }
  await window.loadFile(entry.value);
  return window;
}

app.whenReady().then(async () => {
  Menu.setApplicationMenu(
    Menu.buildFromTemplate([
      {
        label: "MRN",
        submenu: [
          { role: "about" },
          { type: "separator" },
          { role: "reload" },
          { role: "forceReload" },
          { role: "toggleDevTools" },
          { type: "separator" },
          { role: "quit" },
        ],
      },
      {
        label: "Window",
        submenu: [{ role: "minimize" }, { role: "zoom" }],
      },
    ])
  );

  await createMainWindow();

  app.on("activate", async () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      await createMainWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
