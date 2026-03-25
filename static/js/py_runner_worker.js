// static/js/py_runner_worker.js
let pyReady = null;
let pyodide = null;

const WORKDIR = "/workspace";
const localUrl = "/static/pyodide/pyodide.js";
const cdnUrl   = "https://cdn.jsdelivr.net/pyodide/v0.25.1/full/pyodide.js";

async function loadPyodideSmart() {
  try { importScripts(localUrl); }
  catch { importScripts(cdnUrl); }

  pyodide = await self.loadPyodide({ stdout: () => {}, stderr: () => {} });
}

function ensureReady() {
  if (!pyReady) pyReady = loadPyodideSmart();
  return pyReady;
}

function pathParts(p) {
  return String(p || "")
    .replace(/^\/+/, "")
    .split("/")
    .filter(Boolean);
}

function parentDir(path) {
  const parts = pathParts(path);
  parts.pop();
  return "/" + parts.join("/");
}

function ensureDir(fs, absDir) {
  const parts = pathParts(absDir);
  let cur = "";
  for (const part of parts) {
    cur += "/" + part;
    if (!fs.analyzePath(cur).exists) fs.mkdir(cur);
  }
}

function removeTree(fs, absPath) {
  const info = fs.analyzePath(absPath);
  if (!info.exists) return;

  const mode = info.object.mode;
  const isDir = fs.isDir(mode);
  const isFile = fs.isFile(mode);

  if (isFile) {
    fs.unlink(absPath);
    return;
  }

  if (isDir) {
    const names = fs.readdir(absPath).filter(n => n !== "." && n !== "..");
    for (const name of names) {
      removeTree(fs, absPath + "/" + name);
    }
    fs.rmdir(absPath);
  }
}

function writeWorkspace(files) {
  const fs = pyodide.FS;

  // IMPORTANT: do not try to delete the directory we're currently in
  try {
    pyodide.runPython(`import os; os.chdir("/")`);
  } catch (_) {}

  if (fs.analyzePath(WORKDIR).exists) {
    removeTree(fs, WORKDIR);
  }
  fs.mkdir(WORKDIR);

  for (const [relPathRaw, contentRaw] of Object.entries(files || {})) {
    const relPath = String(relPathRaw || "").replace(/^\/+/, "");
    if (!relPath) continue;

    const absPath = WORKDIR + "/" + relPath;
    ensureDir(fs, parentDir(absPath));
    fs.writeFile(absPath, String(contentRaw ?? ""), { encoding: "utf8" });
  }
}

function listFilesRecursive(absDir, relBase = "") {
  const fs = pyodide.FS;
  const out = {};

  for (const name of fs.readdir(absDir)) {
    if (name === "." || name === "..") continue;
    const absPath = absDir + "/" + name;
    const relPath = relBase ? relBase + "/" + name : name;

    const stat = fs.stat(absPath);
    if (fs.isDir(stat.mode)) {
      Object.assign(out, listFilesRecursive(absPath, relPath));
    } else if (fs.isFile(stat.mode)) {
      try {
        out[relPath] = fs.readFile(absPath, { encoding: "utf8" });
      } catch (_) {
        // skip unreadable/binary-ish files
      }
    }
  }

  return out;
}

async function runWorkspace({ files, args, entry_file }) {
  const entryFile = String(entry_file || "main.py");

  writeWorkspace(files || { [entryFile]: "" });

  pyodide.globals.set("JS_ARGS", Array.isArray(args) ? args : []);
  pyodide.globals.set("ENTRY_FILE", entryFile);

  pyodide.runPython(`
import os, sys

os.chdir("${WORKDIR}")

if "${WORKDIR}" not in sys.path:
    sys.path.insert(0, "${WORKDIR}")

keep = {
    "sys", "os", "builtins", "importlib",
    "types", "io", "site", "pathlib",
    "collections", "abc", "re", "json", "math"
}
for name in list(sys.modules):
    if name not in keep and not name.startswith("_frozen_importlib"):
        sys.modules.pop(name, None)

sys.argv = [str(ENTRY_FILE)] + list(JS_ARGS)
`);

  const io = pyodide.pyimport("io");
  const sys = pyodide.pyimport("sys");

  const outBuf = io.StringIO();
  const errBuf = io.StringIO();
  const prevOut = sys.stdout;
  const prevErr = sys.stderr;

  sys.stdout = outBuf;
  sys.stderr = errBuf;

  let result = null;
  try {
    result = await pyodide.runPythonAsync(`
entry_file = str(ENTRY_FILE)
globals_dict = {"__name__": "__main__", "__file__": entry_file}
with open(entry_file, "r", encoding="utf-8") as f:
    code = f.read()
exec(compile(code, entry_file, "exec"), globals_dict, globals_dict)
`);
  } finally {
    sys.stdout = prevOut;
    sys.stderr = prevErr;
  }

  const stdout = outBuf.getvalue();
  const stderr = errBuf.getvalue();
  const filesAfter = listFilesRecursive(WORKDIR);

  try { pyodide.globals.delete("JS_ARGS"); } catch (_) {}
  try { pyodide.globals.delete("ENTRY_FILE"); } catch (_) {}

  return {
    ok: true,
    stdout,
    stderr,
    result: result == null ? null : String(result),
    files: filesAfter,
  };
}

self.onmessage = async (e) => {
  const t0 = performance.now();
  const msg = e.data || {};
  const { id, kind } = msg;

  try {
    await ensureReady();

    if (kind === "run_workspace") {
      const res = await runWorkspace({
        files: msg.files || {},
        args: msg.args || [],
        entry_file: msg.entry_file || "main.py",
      });
      self.postMessage({
        id,
        ...res,
        runtime_ms: Math.round(performance.now() - t0),
      });
      return;
    }

    throw new Error("Unknown worker request");
  } catch (err) {
    self.postMessage({
      id,
      ok: false,
      error: String(err && err.message ? err.message : err),
      runtime_ms: Math.round(performance.now() - t0),
    });
  }
};
