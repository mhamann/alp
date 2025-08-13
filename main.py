import subprocess
import sys
from pathlib import Path
import json
import os

# Execute the VM stub on the provided program (default: hello_world.alp)
vm_path = str(Path(__file__).parent.joinpath("runtime","vm.py"))
program_path = sys.argv[1] if len(sys.argv) > 1 else str(Path(__file__).parent.joinpath("examples","hello_world.alp"))

def _get_by_path(obj, path):
  cur = obj
  for part in path.split('.'):
    if isinstance(cur, dict) and part in cur:
      cur = cur[part]
    elif isinstance(cur, list):
      try:
        idx = int(part)
      except Exception:
        return None
      if idx < 0 or idx >= len(cur):
        return None
      cur = cur[idx]
    else:
      return None
  return cur

if program_path.endswith(".jsonl"):
    # simple golden runner
    ok = True
    for line in Path(program_path).read_text().splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        prog = str(Path(__file__).parent.joinpath(t["program"]))
        expected = t.get("expect")
        env = os.environ.copy()
        for k, v in (t.get("env") or {}).items():
            env[str(k)] = str(v)
        stdin_data = t.get("stdin")
        run = subprocess.run([sys.executable, vm_path, prog], input=stdin_data, capture_output=True, text=True, env=env)
        if run.returncode != 0 or not run.stdout.strip():
            print(json.dumps({"program": t["program"], "status": "FAIL", "error": run.stderr.strip()}, indent=2))
            ok = False
            continue
        out = json.loads(run.stdout)
        # Flexible matching: exact, result equality, expectKeys existence, or expectContains substrings
        match = False
        if expected is None:
            match = True
        elif out == expected or out.get("result") == (expected or {}).get("result"):
            match = True
        else:
            keys = t.get("expectKeys") or []
            if keys:
                match = all(_get_by_path(out, k) is not None for k in keys)
            contains = t.get("expectContains") or {}
            if not match and contains:
                ok = True
                for path, substr in contains.items():
                    val = _get_by_path(out, path)
                    if not isinstance(val, str) or str(substr) not in val:
                        ok = False
                        break
                match = ok
        status = "OK" if match else "FAIL"
        print(json.dumps({"program": t["program"], "status": status, "output": out}, indent=2))
        if not match:
            ok = False
    sys.exit(0 if ok else 1)
else:
    # Check if this is a UI program by looking for ui_launch operations
    is_ui_program = False
    try:
        with open(program_path, 'r') as f:
            content = f.read()
            if 'ui_launch' in content or 'ui_create' in content:
                is_ui_program = True
    except:
        pass
    
    if is_ui_program:
        # For UI programs, don't capture output so the interface can display
        print(f"🚀 Launching UI program: {program_path}")
        print("📱 The web interface will open shortly...")
        print("🛑 Press Ctrl+C to stop the server")
        print()
        subprocess.run([sys.executable, vm_path, program_path])
    else:
        # For regular programs, capture output as before
        completed = subprocess.run([sys.executable, vm_path, program_path], capture_output=True, text=True)
        print(completed.stdout)
        if completed.stderr:
            print(completed.stderr)