# vm.py — ALP core VM (ops are provided by stdlib modules via a registry)
import json
import hashlib
import time
import sys
import os

# Ensure project root is on sys.path when running this file directly
if __package__ is None or __package__ == "":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Global op registry: name -> callable(args: dict, ctx: dict) -> any
OPS: dict[str, object] = {}


def register_op(name: str, func):
    OPS[name] = func


def load_graph(path):
    base_dir = os.path.dirname(os.path.abspath(path))
    shapes, fns, flow = {}, {}, []

    def _merge(s2, f2, fl2):
        shapes.update(s2)
        fns.update(f2)
        flow.extend(fl2)

    def _load_file(pth, visited):
        ap = os.path.abspath(pth)
        if ap in visited:
            return
        visited.add(ap)
        with open(ap) as f:
            for line in f:
                if not line.strip():
                    continue
                n = json.loads(line)
                try:
                    from runtime.vocab import normalize_node as _normalize_node
                    n = _normalize_node(n)
                except Exception:
                    pass
                if n.get("kind") == "@import":
                    rel = n.get("path")
                    if not isinstance(rel, str) or not rel:
                        continue
                    child = os.path.join(os.path.dirname(ap), rel)
                    s2, f2, fl2 = load_graph(child)
                    _merge(s2, f2, fl2)
                    continue
                if n.get("kind") == "@shape":
                    shape_def = {"fields": n.get("fields", {})}
                    if "defaults" in n:
                        shape_def["defaults"] = n["defaults"]
                    if "doc" in n:
                        shape_def["doc"] = n["doc"]
                    shapes[n["id"]] = shape_def
                elif n.get("kind") == "@fn":
                    fns[n["id"]] = n
                elif n.get("kind") == "@flow":
                    flow.extend(n.get("edges", []))

    _load_file(path, set())
    return shapes, fns, flow


def hash_obj(o):
    return "h:" + hashlib.sha256(json.dumps(o, sort_keys=True).encode()).hexdigest()[:8]


def resolve_args(args, env):
    def get_from_env(path_str):
        key = path_str[1:]
        parts = key.split(".") if "." in key else [key]
        cur = env
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return env.get(key)
        return cur

    def resolve_value(v):
        if isinstance(v, str) and v.startswith("$"):
            return get_from_env(v)
        if isinstance(v, list):
            return [resolve_value(x) for x in v]
        if isinstance(v, dict):
            return {kk: resolve_value(vv) for kk, vv in v.items()}
        return v

    return {k: resolve_value(v) for k, v in (args or {}).items()}


def _get_shape_def(shape_name, shapes):
    raw = shapes.get(shape_name, {})
    if isinstance(raw, dict) and "fields" in raw:
        return raw
    if isinstance(raw, dict):
        return {"fields": raw}
    return {"fields": {}}


def shape_to_json_schema(shape_name, shapes):
    shape_def = _get_shape_def(shape_name, shapes)
    fields = shape_def.get("fields", {})
    props = {}
    required = []
    type_map = {"str": "string", "int": "number", "float": "number", "bool": "boolean", "ts": "string"}
    for k, v in fields.items():
        opt = k.endswith("?")
        key = k[:-1] if opt else k
        if not opt:
            required.append(key)
        if isinstance(v, str) and v.startswith("enum<") and v.endswith(">"):
            vals = [x.strip() for x in v[5:-1].split(",") if x.strip()]
            props[key] = {"enum": vals}
        elif isinstance(v, str) and v.startswith("list"):
            item_type = None
            if "<" in v and v.endswith(">"):
                item_type = v[v.find("<") + 1:-1]
            item_schema = {"type": type_map.get(item_type, "number" if item_type in ("int", "float") else "string")} if item_type else {}
            props[key] = {"type": "array", "items": item_schema} if item_schema else {"type": "array"}
        elif isinstance(v, str) and v.startswith("map"):
            val_type = None
            if "<" in v and v.endswith(">"):
                val_type = v[v.find("<") + 1:-1]
            additional = {"type": type_map.get(val_type, "number" if val_type in ("int", "float") else "string")} if val_type else {}
            props[key] = {"type": "object", "additionalProperties": additional} if additional else {"type": "object"}
        else:
            props[key] = {"type": type_map.get(v, "object")}
        if v == "ts":
            props[key]["format"] = "date-time"
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": shape_name,
        "type": "object",
        "properties": props,
        "required": required,
        "additionalProperties": False,
    }


def _apply_shape_defaults(obj, shape_name, shapes):
    shape_def = _get_shape_def(shape_name, shapes)
    defaults = shape_def.get("defaults") or {}
    if not defaults:
        return obj
    out = dict(obj)
    for k, v in defaults.items():
        if k not in out:
            out[k] = v
    return out


def validate_against_shape(obj, shape_name, shapes):
    shape_def = _get_shape_def(shape_name, shapes)
    fields = shape_def.get("fields", {})
    if not isinstance(obj, dict):
        raise AssertionError("Result is not an object")
    for k in fields.keys():
        opt = k.endswith("?")
        key = k[:-1] if opt else k
        if not opt and key not in obj:
            raise AssertionError(f"Schema mismatch, missing: {key}")
    base_keys = {(k[:-1] if k.endswith("?") else k) for k in fields.keys()}
    extras = [k for k in obj.keys() if k not in base_keys]
    if extras:
        raise AssertionError(f"Schema mismatch, extra keys: {extras}")
    for k, t in fields.items():
        opt = k.endswith("?")
        key = k[:-1] if opt else k
        if key not in obj:
            continue
        v = obj[key]
        if isinstance(t, str) and t.startswith("enum<") and t.endswith(">"):
            vals = [x.strip() for x in t[5:-1].split(",") if x.strip()]
            if v not in vals:
                raise AssertionError(f"Field '{key}' not in enum {vals}")
            continue
        if t == "str" and not isinstance(v, str):
            raise AssertionError(f"Field '{key}' not str")
        if t in ("int", "float") and not isinstance(v, (int, float)):
            raise AssertionError(f"Field '{key}' not number")
        if t == "bool" and not isinstance(v, bool):
            raise AssertionError(f"Field '{key}' not bool")
        if isinstance(t, str) and t.startswith("list"):
            if not isinstance(v, list):
                raise AssertionError(f"Field '{key}' not list")
        if isinstance(t, str) and t.startswith("map"):
            if not isinstance(v, dict):
                raise AssertionError(f"Field '{key}' not map/object")
    return True


def get_provider(provider_override: str | None = None, model_override: str | None = None):
    provider = (provider_override or os.getenv("ALP_MODEL_PROVIDER") or "mock")
    provider = provider.lower() if isinstance(provider, str) else "mock"
    model = model_override or os.getenv("ALP_MODEL_NAME")
    if provider == "openai" and not model:
        model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    if provider == "anthropic" and not model:
        model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20240620")
    return provider, model


def _openai_call(task, input_obj, schema_dict, model):
    try:
        import openai  # type: ignore
    except Exception:
        raise RuntimeError("OpenAI SDK not installed. pip install openai")
    client = openai.OpenAI()
    def _msg_to_text(msg):
        # OpenAI SDK v1 returns message objects; content may be str or list of content parts
        c = getattr(msg, "content", None)
        if isinstance(c, str):
            return c
        if isinstance(c, list):
            parts = []
            for p in c:
                # p can be dict or object with .type/.text
                if isinstance(p, dict):
                    if p.get("type") == "text" and "text" in p:
                        parts.append(p["text"])
                else:
                    t = getattr(p, "type", None)
                    if t == "text":
                        parts.append(getattr(p, "text", ""))
            return "".join(parts)
        # Fallback: try mapping interface
        try:
            return msg["content"]
        except Exception:
            return ""
    def _coerce_json(text: str):
        import json as _json
        try:
            return _json.loads(text)
        except Exception:
            # Try to extract the first JSON object substring
            if not isinstance(text, str):
                raise
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                return _json.loads(text[start:end+1])
            raise
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a JSON generator. Output ONLY JSON that strictly matches the provided JSON Schema."},
                {"role": "user", "content": json.dumps({"task": task, "input": input_obj, "json_schema": schema_dict})},
            ],
            temperature=0.2,
        )
        text = _msg_to_text(resp.choices[0].message)
    except Exception:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "Return ONLY JSON. No prose."},
                {"role": "user", "content": f"Task: {task}\nInput: {json.dumps(input_obj)}\nSchema Title: {schema_dict.get('title')}\nRespond with JSON only."},
            ],
            temperature=0.2,
        )
        text = _msg_to_text(resp.choices[0].message)
    try:
        return _coerce_json(text)
    except Exception as e:
        raise AssertionError(f"Model did not return JSON: {e}")


def _anthropic_call(task, input_obj, schema_dict, model):
    try:
        import anthropic  # type: ignore
    except Exception:
        raise RuntimeError("Anthropic SDK not installed. pip install anthropic")
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model,
        max_tokens=512,
        temperature=0.2,
        system="Return ONLY JSON matching the provided JSON structure. No explanations.",
        messages=[{"role": "user", "content": [{"type": "text", "text": "Task: " + task + "\n" + "Input: " + json.dumps(input_obj) + "\n" + "Schema Title: " + (schema_dict.get("title") or "") + "\n" + "Respond with JSON only."}]}],
    )
    parts = []
    for b in msg.content:
        if hasattr(b, "type") and b.type == "text" and hasattr(b, "text"):
            parts.append(b.text)
        elif isinstance(b, dict) and b.get("type") == "text":
            parts.append(b.get("text", ""))
    text = "".join(parts)
    try:
        return json.loads(text)
    except Exception as e:
        raise AssertionError(f"Model did not return JSON: {e}")


def call_llm(task, input_obj, schema_name, shapes, retries=3, provider: str | None = None, model: str | None = None):
    provider, model = get_provider(provider, model)
    schema_dict = shape_to_json_schema(schema_name, shapes)
    last_err = None
    for _ in range(1, (retries or 1) + 1):
        try:
            if provider == "openai":
                cand = _openai_call(task, input_obj, schema_dict, model)
            elif provider == "anthropic":
                cand = _anthropic_call(task, input_obj, schema_dict, model)
            else:
                # simple schema-based synthesis
                props = schema_dict.get("properties", {})
                def _default_for(prop):
                    t = (prop or {}).get("type")
                    if t == "string":
                        return ""
                    if t == "number":
                        return 0
                    if t == "boolean":
                        return False
                    if t == "array":
                        return []
                    if t == "object":
                        return {}
                    return None
                cand = {k: _default_for(props.get(k)) for k in schema_dict.get("required", [])}
            validate_against_shape(cand, schema_name, shapes)
            return cand
        except Exception as e:
            last_err = e
            input_obj = {"original": input_obj, "error": str(e)}
            continue
    raise RuntimeError(f"LLM failed schema validation after {retries} attempts: {last_err}")


def exec_fn(fn, shapes, fns, inbound=None):
    env, result = {}, None
    if inbound is not None:
        declared_inputs = (fn.get("in") or {})
        if declared_inputs:
            for name in declared_inputs.keys():
                env[name] = inbound

    for k, v in (fn.get("@const") or {}).items():
        env[k] = v

    explain = bool(os.getenv("ALP_EXPLAIN"))
    provenance = []
    for idx, op in enumerate((fn.get("@op") or [])):
        name, args = op[0], (op[1] if len(op) > 1 else {})
        bind_meta = (op[2] if len(op) > 2 and isinstance(op[2], dict) else {})
        a = resolve_args(args, env)
        if name not in OPS:
            raise RuntimeError(f"Unknown op: {name}")
        ctx = {
            "env": env,
            "shapes": shapes,
            "fns": fns,
            "exec_fn": lambda _fn, _inb=None: exec_fn(_fn, shapes, fns, inbound=_inb),
            "call_llm": lambda task, input_obj, schema, _shapes, retries=3, provider=None, model=None: call_llm(task, input_obj, schema, shapes, retries=retries, provider=provider, model=model),
            "get_provider": lambda provider=None, model=None: get_provider(provider, model),
            "hash": lambda o: hash_obj(o),
            "provenance": provenance,
        }
        result = OPS[name](a, ctx)
        env["result"] = result
        if isinstance(result, dict) and "value" in result:
            env["value"] = result["value"]
        elif isinstance(result, (int, float)):
            env["value"] = result
        if bind_meta.get("as"):
            env[bind_meta["as"]] = result
        if explain:
            try:
                print(json.dumps({
                    "node": fn.get("id"),
                    "op_index": idx,
                    "op": name,
                    "env_snapshot": {k: (v if isinstance(v, (int, float, str, bool)) else type(v).__name__) for k, v in env.items()},
                }, indent=2), file=sys.stderr)
            except Exception:
                pass

    if fn.get("@llm") is not None:
        spec = fn.get("@llm") or {}
        task = spec.get("task")
        inp = resolve_args(spec.get("input") or {}, env)
        if not inp and inbound is not None:
            inp = inbound
        t0 = time.time()
        result = call_llm(
            task,
            inp,
            spec.get("schema"),
            shapes,
            retries=(fn.get("@retry", {}) or {}).get("max", 3),
            provider=spec.get("provider"),
            model=spec.get("model"),
        )
        t1 = time.time()
        env["result"] = result
        if isinstance(result, dict) and "value" in result:
            env["value"] = result["value"]
        if explain:
            try:
                preview = result if not isinstance(result, dict) else {k: (v if isinstance(v, (int, float, bool)) else (v[:80] + ("…" if len(v) > 80 else "") if isinstance(v, str) else type(v).__name__)) for k, v in result.items()}
                print(json.dumps({"node": fn.get("id"), "llm_result": preview}, indent=2), file=sys.stderr)
            except Exception:
                pass
        prov = {
            "kind": "llm",
            "provider": get_provider(spec.get("provider"), spec.get("model"))[0],
            "model": get_provider(spec.get("provider"), spec.get("model"))[1],
            "input_hash": hash_obj(inp),
            "output_hash": hash_obj(result),
            "ms": int((t1 - t0) * 1000),
        }
        provenance.append(prov)

    exp_type = (fn.get("@expect") or {}).get("type")
    if exp_type:
        synth = (fn.get("@expect") or {}).get("synthesize") is True
        if synth and (result is None or not isinstance(result, dict)):
            shape_def = _get_shape_def(exp_type, shapes)
            fields = shape_def.get("fields", {})
            synthesized = {}
            for k in fields.keys():
                key = k[:-1] if k.endswith("?") else k
                if key in env:
                    synthesized[key] = env[key]
            if synthesized:
                result = synthesized
        if isinstance(result, dict):
            result = _apply_shape_defaults(result, exp_type, shapes)
        if "@llm" not in fn:
            validate_against_shape(result, exp_type, shapes)

    trace = {
        "node": fn.get("id"),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "outputs_hash": hash_obj(result),
        "status": "ok",
        "provenance": provenance if provenance else None,
    }
    return result, trace


def run(path):
    # load stdlib ops
    # Import stdlib ops package
    from runtime.stdlib import register_all as _register_all
    _register_all(OPS, register_op)

    shapes, fns, flow = load_graph(path)
    if not flow:
        # fallback to any no-input fn; if multiple, run the first deterministically by id
        candidates = [k for k, fn in fns.items() if not fn.get("in")]
        if candidates:
            start = sorted(candidates)[0]
            flow = [[start, None, {}]]
    if not flow:
        raise RuntimeError("No runnable nodes.")

    traces = []
    data_out = None
    last_node = None
    def resolve_from_obj(ref, obj):
        if isinstance(ref, str) and ref.startswith("$"):
            key = ref[1:]
            parts = key.split(".") if "." in key else [key]
            cur = obj
            for p in parts:
                if isinstance(cur, dict) and p in cur:
                    cur = cur[p]
                elif p == "value" and not isinstance(cur, dict):
                    cur = cur
                else:
                    return None
            return cur
        return ref

    def eval_when(cond, obj):
        if cond is None:
            return True
        if isinstance(cond, bool):
            return cond
        if isinstance(cond, str):
            val = resolve_from_obj(cond, obj)
            return bool(val)
        if isinstance(cond, dict):
            if len(cond) != 1:
                return False
            op_name, arg = next(iter(cond.items()))
            if op_name in ("and", "or") and isinstance(arg, list):
                vals = [eval_when(x, obj) for x in arg]
                return all(vals) if op_name == "and" else any(vals)
            if op_name == "not":
                return not eval_when(arg, obj)
            if isinstance(arg, list) and len(arg) == 2:
                left = resolve_from_obj(arg[0], obj)
                right = resolve_from_obj(arg[1], obj)
                if op_name == "eq":
                    return left == right
                elif op_name == "ne":
                    return left != right
                elif op_name == "gt":
                    return left > right
                elif op_name == "gte":
                    return left >= right
                elif op_name == "lt":
                    return left < right
                elif op_name == "lte":
                    return left <= right
        return False

    for src, dst, meta in flow:
        if src != last_node:
            fn = fns[src]
            result, tr = exec_fn(fn, shapes, fns, inbound=data_out)
            traces.append(tr)
            data_out = result
            last_node = src
        if dst:
            when_cond = (meta or {}).get("when") if isinstance(meta, dict) else None
            if eval_when(when_cond, data_out):
                fn2 = fns[dst]
                result2, tr2 = exec_fn(fn2, shapes, fns, inbound=data_out)
                traces.append(tr2)
                data_out = result2
                last_node = dst

    print(json.dumps({"result": data_out, "trace": traces}, indent=2))


if __name__ == "__main__":
    run(sys.argv[1])
