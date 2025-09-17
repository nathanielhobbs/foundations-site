// py-worker.js
self.onmessage = () => {}; // quiet default

importScripts('https://cdn.jsdelivr.net/pyodide/v0.26.3/full/pyodide.js');

let pyodide = null;

async function boot() {
  pyodide = await loadPyodide({ stdin: () => null }); // disable input()
  // Build a small prelude that:
  //  - blocks open()
  //  - restricts __import__ to a whitelist
  //  - captures stdout/stderr
  const prelude = `
import sys, builtins, types
from contextlib import redirect_stdout, redirect_stderr
# --- permissions ---
def _blocked_open(*args, **kwargs):
    raise PermissionError("File access is disabled in this sandbox.")
builtins.open = _blocked_open

_ALLOWED = {"math","random","statistics","itertools","functools","collections"}
_real_import = builtins.__import__
def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
    root = name.split('.')[0]
    if root not in _ALLOWED:
        raise ImportError(f"Import of '{name}' is not allowed")
    return _real_import(name, globals, locals, fromlist, level)
builtins.__import__ = _guarded_import

# --- stdio capture helpers ---
class _Buf:
    def __init__(self): self._b=[]
    def write(self,s): self._b.append(s)
    def get(self): return ''.join(self._b)
_stdout_buf = _Buf()
_stderr_buf = _Buf()
def _run_user(code):
    out, err = "", ""
    try:
        with redirect_stdout(_stdout_buf), redirect_stderr(_stderr_buf):
            exec(code, {"__name__":"__main__"})
    except SystemExit:
        pass
    except Exception as e:
        print(repr(e), file=sys.stderr)
    return _stdout_buf.get(), _stderr_buf.get()
`;
  await pyodide.runPythonAsync(prelude);
  postMessage({ kind: 'ready' });
}

boot();

self.onmessage = async (ev) => {
  const { kind, code } = ev.data || {};
  if (kind !== 'run' || !pyodide) return;

  try {
    const result = await pyodide.runPythonAsync(`
_out, _err = _run_user(${JSON.stringify(code)})
_out, _err
`);
    const [out, err] = result.toJs();
    if (out) postMessage({ kind: 'stdout', data: out });
    if (err) postMessage({ kind: 'stderr', data: err });
    postMessage({ kind: 'done' });
  } catch (e) {
    postMessage({ kind: 'error', data: String(e) });
  }
};

