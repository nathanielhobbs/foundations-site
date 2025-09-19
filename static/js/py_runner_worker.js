// static/js/py_runner_worker.js
let pyReady = null;
let pyodide = null;

const localUrl = "/static/pyodide/pyodide.js";
const cdnUrl   = "https://cdn.jsdelivr.net/pyodide/v0.25.1/full/pyodide.js";

async function loadPyodideSmart() {
  try { importScripts(localUrl); } catch { importScripts(cdnUrl); }
  pyodide = await self.loadPyodide({ stdout: () => {}, stderr: () => {} });
}
function ensureReady() { if (!pyReady) pyReady = loadPyodideSmart(); return pyReady; }

self.onmessage = async (e) => {
  const { id, code } = e.data || {};
  const t0 = performance.now();
  try {
    await ensureReady();
    const py = pyodide.pyimport("builtins");
    const io = pyodide.pyimport("io");
    const sys = pyodide.pyimport("sys");

    const outBuf = io.StringIO();
    const errBuf = io.StringIO();
    const prevOut = sys.stdout;
    const prevErr = sys.stderr;
    sys.stdout = outBuf;
    sys.stderr = errBuf;

    let result = null;
    try { result = await pyodide.runPythonAsync(code); }
    finally { sys.stdout = prevOut; sys.stderr = prevErr; }

    const stdout = outBuf.getvalue();
    const stderr = errBuf.getvalue();

    self.postMessage({ id, ok:true, stdout, stderr, result: result==null ? null : String(result), runtime_ms: Math.round(performance.now()-t0) });
  } catch (err) {
    self.postMessage({ id, ok:false, error: String(err && err.message ? err.message : err), runtime_ms: Math.round(performance.now()-t0) });
  }
};

