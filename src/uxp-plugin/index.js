// Production Processor UXP Plugin - the default Photoshop front-end for the
// AI Reference Retriever.
//
// The plugin owns no path of its own: it resolves the retriever folder from
// the project (retriever_config.json + ~/production_processor_dir.txt) and
// then reuses the project's own launcher scripts (run.bat / start_hidden.vbs).

const PLUGIN_ID = "com.retriever.launcher";
const POINTER_FILE = "production_processor_dir.txt"; // ~/<pointer> -> retriever folder
const CONFIG_FILE = "retriever_config.json"; // <retriever>/<config> -> how to launch
const PATH_KEY = "retrieverPath"; // panel-local memory of the user's choice

// Where the retriever may live, relative to the user's home folder.
const HOME_CANDIDATES = [
  "Downloads\\ai-reference-retriever-extracted\\ai-reference-retriever",
  "Downloads\\ai-reference-retriever",
  "Desktop\\ai-reference-retriever",
  "Documents\\ai-reference-retriever",
  "ai-reference-retriever",
];

// Used when the project does not ship a config file.
const DEFAULT_TOOL = {
  entry: "app.py",
  launcher: "run.bat",
  hiddenLauncher: "start_hidden.vbs",
  boardFolder: "board",
  pointerFile: POINTER_FILE,
};

let retrieverPath = null;
let tool = DEFAULT_TOOL;
let missingPath = null; // a remembered folder that is no longer there

// ------------------------------------------------------------- helpers ------
// Every UXP module is required lazily: a failing require must not take the
// whole panel down.
function fs() {
  try {
    const storage = require("uxp").storage;
    return storage ? storage.localFileSystem : null;
  } catch (e) {
    return null;
  }
}

function homeDir() {
  try {
    const home = require("os").homedir();
    if (home) return home;
  } catch (e) {
    // no os module in this host
  }
  return null;
}

// Windows joins folders with "\\", a Mac with "/". A Mac home folder starts with "/".
const IS_MAC = (homeDir() || "").charAt(0) === "/";
const SEP = IS_MAC ? "/" : "\\";
const MAC_LAUNCHER = "run.command"; // the Mac counterpart of run.bat

function shellOpenPath(path) {
  return require("uxp").shell.openPath(path);
}

// ------------------------------------------------------------- filesystem ---
// The UXP file system API works with urls: file:///C:/Users/...
function toUrl(path) {
  return "file:///" + String(path).replace(/\\/g, "/").replace(/^\/+/, "");
}

async function entryForPath(path) {
  const localFileSystem = fs();
  if (!localFileSystem) return null;
  try {
    return await localFileSystem.getEntryWithUrl(toUrl(path));
  } catch (e) {
    return null;
  }
}

async function exists(path) {
  return !!(await entryForPath(path));
}

async function readText(path) {
  const entry = await entryForPath(path);
  if (!entry || !entry.isFile) return null;
  try {
    return await entry.read({ format: "text" });
  } catch (e) {
    return null;
  }
}

async function writeText(path, text) {
  const localFileSystem = fs();
  if (!localFileSystem) return false;
  try {
    const entry = await localFileSystem.createEntryWithUrl(toUrl(path), { overwrite: true });
    await entry.write(text);
    return true;
  } catch (e) {
    return false;
  }
}

// A folder is the retriever if it carries the launcher or the tool itself.
async function isRetrieverFolder(dir) {
  if (!dir) return false;
  return (
    (await exists(dir + SEP + tool.launcher)) ||
    (await exists(dir + SEP + tool.hiddenLauncher)) ||
    (await exists(dir + SEP + tool.entry))
  );
}

// --------------------------------------------------------- panel memory ---
// The panel's own copy of the choice. It is a cache: the shared pointer in
// the user's home folder is the durable one, because that survives a
// reinstall of the plugin (this storage does not).
function readLocal() {
  try {
    return (window.localStorage.getItem(PATH_KEY) || "").trim() || null;
  } catch (e) {
    return null;
  }
}

function rememberLocal(dir) {
  try {
    if (readLocal() !== dir) window.localStorage.setItem(PATH_KEY, dir);
  } catch (e) {
    console.error("Failed to remember path:", e);
  }
}

function forgetLocal() {
  try {
    window.localStorage.removeItem(PATH_KEY);
  } catch (e) {
    console.error("Failed to forget path:", e);
  }
}

// -------------------------------------------------- shared project lookup ---
// One pointer file keeps the UXP panel, the CEP panel and the JSX scripts on
// the same target. It lives in the user's home folder, so the folder that was
// chosen once stays the default on this machine until it is changed by hand.
function pointerPath() {
  const home = homeDir();
  return home ? home + SEP + tool.pointerFile : null;
}

async function readPointer() {
  const p = pointerPath();
  if (!p) return null;
  const saved = (await readText(p) || "").trim();
  return saved || null;
}

async function writePointer(dir) {
  const p = pointerPath();
  if (!p) return;
  if ((await readPointer()) !== dir) {
    await writeText(p, dir);
  }
}

// Load the project's own contract (which script launches the tool, etc).
async function loadToolConfig(dir) {
  const txt = await readText(dir + SEP + CONFIG_FILE);
  if (!txt) return DEFAULT_TOOL;
  try {
    const cfg = JSON.parse(txt);
    return Object.assign({}, DEFAULT_TOOL, cfg.tool || {});
  } catch (e) {
    return DEFAULT_TOOL;
  }
}

/**
 * Resolve the retriever folder.
 *
 * The folder the user saved is the default - full stop:
 *   1. the panel's own memory of the saved folder (the choice itself)
 *   2. the durable copy of that choice in the home folder, which is what
 *      keeps it alive across a reinstall of the plugin (this storage does
 *      not survive that)
 *   3. known locations under the home folder - only for a first run
 *
 * Nothing outside the panel can move the choice: the pointer file is only
 * ever written FROM the saved choice, and the installer never overwrites a
 * pointer that still points at a real folder.
 *
 * A saved folder that has since been moved or deleted is still shown as the
 * default, with a warning, so the choice is not lost - moving the folder
 * back restores it.
 */
async function resolveRetriever() {
  // 1. the saved choice
  const cached = readLocal();
  if (cached) {
    if (await isRetrieverFolder(cached)) {
      // keep the durable copy in step with the choice
      await writePointer(cached);
      return { dir: cached, missing: null };
    }
    return { dir: cached, missing: cached };
  }

  // 2. the durable copy of the choice (fresh install of the panel)
  const pointed = await readPointer();
  if (pointed) {
    if (await isRetrieverFolder(pointed)) {
      rememberLocal(pointed);
      return { dir: pointed, missing: null };
    }
    return { dir: pointed, missing: pointed };
  }

  // 3. first run: adopt a known location as the default for this machine
  const home = homeDir();
  if (home) {
    for (const rel of HOME_CANDIDATES) {
      const dir = home + SEP + rel.split("\\").join(SEP);
      if (await isRetrieverFolder(dir)) {
        rememberLocal(dir);
        await writePointer(dir);
        return { dir: dir, missing: null };
      }
    }
  }
  return { dir: null, missing: null };
}

// Resolve + keep the durable copy in step with the saved choice.
async function ensureRetriever() {
  const { dir, missing } = await resolveRetriever();
  missingPath = missing;
  if (!dir) {
    retrieverPath = null;
    return null;
  }
  tool = await loadToolConfig(dir);
  retrieverPath = dir;
  return dir;
}

// ------------------------------------------------------------------- UI -----
function updateFolderDisplay(extra) {
  const el = document.getElementById("folderPath");
  if (el) el.textContent = retrieverPath || "Not set";
  const info = document.getElementById("toolInfo");
  if (info) {
    info.textContent =
      extra !== undefined
        ? extra
        : retrieverPath
        ? "launcher: " + tool.launcher + "  |  board: " + tool.boardFolder
        : "";
  }
}

function setStatus(msg, isError) {
  const el = document.getElementById("status");
  if (!el) return;
  el.textContent = msg;
  el.classList.toggle("error", !!isError);
  if (!isError) {
    setTimeout(() => {
      el.textContent = "";
    }, 8000);
  }
}

// -------------------------------------------------------------- actions -----
async function launchRetriever() {
  setStatus("Launching...");
  const dir = await ensureRetriever();
  if (!dir) {
    setStatus("Retriever folder not found - pick it below.", true);
    return;
  }
  if (missingPath) {
    setStatus("The saved folder is not there any more: " + dir, true);
    return;
  }

  // Reuse the project's own launchers, console-free variant first.
  const candidates = IS_MAC
    ? [{ label: MAC_LAUNCHER, path: dir + SEP + MAC_LAUNCHER }]
    : [
        { label: tool.hiddenLauncher, path: dir + SEP + tool.hiddenLauncher },
        { label: tool.launcher, path: dir + SEP + tool.launcher },
      ];

  const errors = [];
  for (const c of candidates) {
    if (!(await exists(c.path))) continue;
    try {
      const err = await shellOpenPath(c.path);
      if (!err) {
        setStatus("Retriever launched!");
        return;
      }
      errors.push(c.label + ": " + err);
    } catch (e) {
      errors.push(c.label + ": " + e.message);
    }
  }

  setStatus(
    "Launch failed: " + (errors.length ? errors.join("  |  ") : "no launcher script found"),
    true
  );
}

async function openBoardFolder() {
  const dir = await ensureRetriever();
  if (!dir) {
    setStatus("Retriever folder not found - pick it below.", true);
    return;
  }
  if (missingPath) {
    setStatus("The saved folder is not there any more: " + dir, true);
    return;
  }
  const board = dir + SEP + tool.boardFolder;
  try {
    const err = await shellOpenPath(board);
    if (err) {
      setStatus("Error: " + err, true);
    } else {
      setStatus("Board folder opened");
    }
  } catch (e) {
    setStatus("Error: " + e.message, true);
  }
}

async function chooseFolder() {
  const localFileSystem = fs();
  if (!localFileSystem) {
    setStatus("File access is not available in this plugin.", true);
    return;
  }
  try {
    const folder = await localFileSystem.getFolder();
    if (!folder) return;
    const dir = localFileSystem.getNativePath(folder);
    if (!(await isRetrieverFolder(dir))) {
      setStatus("Selected folder doesn't contain " + tool.launcher);
      return;
    }
    retrieverPath = dir;
    tool = await loadToolConfig(dir);
    missingPath = null;
    // the choice is kept in two places: the panel's own memory and the
    // shared pointer in the home folder, so it survives a restart and a
    // reinstall. It stays the default until it is changed here again.
    rememberLocal(dir);
    await writePointer(dir);
    updateFolderDisplay();
    setStatus("Folder saved - it will be used from now on.");
  } catch (e) {
    setStatus("Error: " + e.message);
    console.error("Choose folder failed:", e);
  }
}

// ---------------------------------------------------------------- theme ----
// Follow the host's theme so the panel looks native in Photoshop's light and
// dark UI, and swap the icon for the one drawn for that theme.
const THEME_ICONS = {
  dark: "icons/dark/icon@2x.png",
  light: "icons/light/icon@2x.png",
};

function applyTheme(theme) {
  const isLight = theme === "light";
  document.documentElement.setAttribute("data-theme", isLight ? "light" : "dark");
  const icon = document.getElementById("panelIcon");
  if (icon) {
    const src = isLight ? THEME_ICONS.light : THEME_ICONS.dark;
    if (icon.getAttribute("src") !== src) icon.setAttribute("src", src);
  }
}

function initTheme() {
  try {
    const thememanager = require("uxp").thememanager;
    if (!thememanager) return;
    thememanager.onThemeChange((payload) => {
      if (payload && payload.theme) applyTheme(payload.theme);
    });
    const current = thememanager.getSystemTheme();
    if (current && typeof current.then === "function") {
      current
        .then((payload) => {
          if (payload && payload.theme) applyTheme(payload.theme);
        })
        .catch(() => {});
    }
  } catch (e) {
    // no theme manager in this host - the dark default in the CSS stands
  }
}

// ------------------------------------------------------------------ boot ----
async function init() {
  const dir = await ensureRetriever();
  if (!dir) {
    retrieverPath = null;
    const home = homeDir();
    updateFolderDisplay(
      "not found - home: " + (home || "unknown") + " | fs: " + (fs() ? "ok" : "unavailable")
    );
    return;
  }
  if (missingPath) {
    // the choice is still the choice - it is just not on disk right now
    updateFolderDisplay("saved folder - but it is not there any more");
    setStatus(
      "The saved folder is gone: " + dir + " - choose another below.",
      true
    );
    return;
  }
  updateFolderDisplay();
}

document.addEventListener("DOMContentLoaded", () => {
  document.getElementById("launchBtn").addEventListener("click", launchRetriever);
  document.getElementById("boardBtn").addEventListener("click", openBoardFolder);
  document.getElementById("folderBtn").addEventListener("click", chooseFolder);
  initTheme();
  init();
});
