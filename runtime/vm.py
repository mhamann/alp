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
    tools = {}  # Store tool definitions

    def _merge(s2, f2, fl2, t2=None):
        shapes.update(s2)
        fns.update(f2)
        flow.extend(fl2)
        if t2:
            tools.update(t2)

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
                    s2, f2, fl2, t2 = load_graph(child)
                    _merge(s2, f2, fl2, t2)
                    continue
                if n.get("kind") == "@shape":
                    shape_def = {"fields": n.get("fields", {})}
                    if "defaults" in n:
                        shape_def["defaults"] = n["defaults"]
                    if "doc" in n:
                        shape_def["doc"] = n["doc"]
                    shapes[n["id"]] = shape_def
                elif n.get("kind") == "@def":
                    # Type definition - aliases, unions, literals, branded types
                    type_def = {"kind": "def"}
                    if "type" in n:
                        type_def["type"] = n["type"]
                    if "doc" in n:
                        type_def["doc"] = n["doc"]
                    if "constraint" in n:
                        type_def["constraint"] = n["constraint"]
                    shapes[n["id"]] = type_def
                elif n.get("kind") == "@tool":
                    # Tool definition - external function specification
                    tool_def = {"id": n.get("id")}
                    if "name" in n:
                        tool_def["name"] = n["name"]
                    if "description" in n:
                        tool_def["description"] = n["description"]
                    if "input_schema" in n:
                        tool_def["input_schema"] = n["input_schema"]
                    if "output_schema" in n:
                        tool_def["output_schema"] = n["output_schema"]
                    if "implementation" in n:
                        tool_def["implementation"] = n["implementation"]
                    tools[n["id"]] = tool_def
                elif n.get("kind") == "@fn":
                    fns[n["id"]] = n
                elif n.get("kind") == "@flow":
                    flow.extend(n.get("edges", []))

    _load_file(path, set())
    return shapes, fns, flow, tools


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


def _resolve_def_type(def_obj, shapes):
    """Resolve a @def type definition to a shape-like structure for validation."""
    type_spec = def_obj.get("type", "str")

    # Handle type aliases - resolve recursively
    if isinstance(type_spec, str) and type_spec in shapes:
        return _get_shape_def(type_spec, shapes)

    # Handle union types: "str | int | UserType"
    if isinstance(type_spec, str) and " | " in type_spec:
        union_types = [t.strip() for t in type_spec.split(" | ")]
        # For validation, treat unions as allowing any of the component types
        return {"fields": {}, "union": union_types, "kind": "union"}

    # Handle literal types: "success" | "error" | "pending"
    if isinstance(type_spec, str) and type_spec.startswith('"') and type_spec.endswith('"'):
        literal_value = type_spec[1:-1]  # Remove quotes
        return {"fields": {}, "literal": literal_value, "kind": "literal"}

    # Handle arrays of literals: ["success", "error", "pending"]
    if isinstance(type_spec, list):
        return {"fields": {}, "enum": type_spec, "kind": "enum"}

    # Handle constraint-based types (branded primitives)
    if isinstance(type_spec, str) and def_obj.get("constraint"):
        base_type = type_spec
        constraint = def_obj.get("constraint")
        return {"fields": {}, "base_type": base_type, "constraint": constraint, "kind": "constrained"}

    # Handle primitive type aliases
    if isinstance(type_spec, str):
        # Map to a single-field object for compatibility
        return {"fields": {"value": type_spec}}

    return {"fields": {}}


def _validate_union_type(obj, shape_def, shapes):
    """Validate against union type - obj must match at least one of the union types."""
    union_types = shape_def.get("union", [])
    for union_type in union_types:
        try:
            if union_type in shapes:
                validate_against_shape(obj, union_type, shapes)
                return True
            else:
                # Try primitive type validation
                if union_type == "str" and isinstance(obj, str):
                    return True
                elif union_type == "int" and isinstance(obj, int):
                    return True
                elif union_type == "float" and isinstance(obj, (int, float)):
                    return True
                elif union_type == "bool" and isinstance(obj, bool):
                    return True
        except AssertionError:
            continue
    raise AssertionError(f"Value does not match any type in union: {union_types}")


def _validate_literal_type(obj, shape_def):
    """Validate against literal type - obj must exactly match the literal value."""
    literal_value = shape_def.get("literal")
    if obj != literal_value:
        raise AssertionError(f"Value '{obj}' does not match literal '{literal_value}'")
    return True


def _validate_enum_type(obj, shape_def):
    """Validate against enum type - obj must be one of the allowed values."""
    enum_values = shape_def.get("enum", [])
    if obj not in enum_values:
        raise AssertionError(f"Value '{obj}' not in enum {enum_values}")
    return True


def _validate_constrained_type(obj, shape_def):
    """Validate against constrained type - obj must match base type and satisfy constraint."""
    base_type = shape_def.get("base_type", "str")
    constraint = shape_def.get("constraint", {})

    # First validate base type
    if base_type == "str" and not isinstance(obj, str):
        raise AssertionError(f"Expected string, got {type(obj).__name__}")
    elif base_type == "int" and not isinstance(obj, int):
        raise AssertionError(f"Expected int, got {type(obj).__name__}")
    elif base_type == "float" and not isinstance(obj, (int, float)):
        raise AssertionError(f"Expected number, got {type(obj).__name__}")
    elif base_type == "bool" and not isinstance(obj, bool):
        raise AssertionError(f"Expected bool, got {type(obj).__name__}")

    # Then validate constraints
    if "minLength" in constraint and isinstance(obj, str):
        if len(obj) < constraint["minLength"]:
            raise AssertionError(f"String length {len(obj)} below minimum {constraint['minLength']}")
    if "maxLength" in constraint and isinstance(obj, str):
        if len(obj) > constraint["maxLength"]:
            raise AssertionError(f"String length {len(obj)} above maximum {constraint['maxLength']}")
    if "pattern" in constraint and isinstance(obj, str):
        import re
        if not re.match(constraint["pattern"], obj):
            raise AssertionError(f"String '{obj}' does not match pattern '{constraint['pattern']}'")
    if "min" in constraint and isinstance(obj, (int, float)):
        if obj < constraint["min"]:
            raise AssertionError(f"Value {obj} below minimum {constraint['min']}")
    if "max" in constraint and isinstance(obj, (int, float)):
        if obj > constraint["max"]:
            raise AssertionError(f"Value {obj} above maximum {constraint['max']}")

    return True


def _get_shape_def(shape_name, shapes):
    raw = shapes.get(shape_name, {})
    if isinstance(raw, dict) and "fields" in raw:
        return raw
    if isinstance(raw, dict) and raw.get("kind") == "def":
        # For @def types, resolve to their underlying type
        return _resolve_def_type(raw, shapes)
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

    # Handle special @def type kinds
    if shape_def.get("kind") == "union":
        return _validate_union_type(obj, shape_def, shapes)
    elif shape_def.get("kind") == "literal":
        return _validate_literal_type(obj, shape_def)
    elif shape_def.get("kind") == "enum":
        return _validate_enum_type(obj, shape_def)
    elif shape_def.get("kind") == "constrained":
        return _validate_constrained_type(obj, shape_def)

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
        # Check if field type is a custom shape or @def type
        if isinstance(t, str) and t in shapes:
            try:
                validate_against_shape(v, t, shapes)
            except AssertionError as e:
                raise AssertionError(f"Field '{key}' validation failed: {e}")
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


def call_llm_batch(task, input_list, schema_name, shapes, retries=3, provider: str | None = None, model: str | None = None):
    provider, model = get_provider(provider, model)
    schema_dict_single = shape_to_json_schema(schema_name, shapes)
    schema_dict_array = {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "title": f"{schema_name}Array",
        "type": "array",
        "items": schema_dict_single.get("properties") and {"type": "object", "properties": schema_dict_single["properties"], "required": schema_dict_single["required"], "additionalProperties": False} or {"type": "object"}
    }
    last_err = None
    for _ in range(1, (retries or 1) + 1):
        try:
            if provider == "openai":
                try:
                    import openai  # type: ignore
                except Exception:
                    raise RuntimeError("OpenAI SDK not installed. pip install openai")
                client = openai.OpenAI()
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are a JSON generator. Output ONLY JSON array where each element strictly matches the provided item JSON Schema."},
                        {"role": "user", "content": json.dumps({"task": task, "inputs": input_list, "json_schema_array": schema_dict_array})},
                    ],
                    temperature=0.2,
                )
                text = (resp.choices[0].message.content if hasattr(resp.choices[0].message, "content") else resp.choices[0].message["content"]) or "[]"
                arr = json.loads(text)
            elif provider == "anthropic":
                try:
                    import anthropic  # type: ignore
                except Exception:
                    raise RuntimeError("Anthropic SDK not installed. pip install anthropic")
                client = anthropic.Anthropic()
                msg = client.messages.create(
                    model=model,
                    max_tokens=2048,
                    temperature=0.2,
                    system="Return ONLY a JSON array of objects matching the provided JSON structure. No explanations.",
                    messages=[{"role": "user", "content": [{"type": "text", "text": "Task: " + task + "\n" + "Inputs: " + json.dumps(input_list) + "\n" + "Respond with a JSON array only."}]}],
                )
                parts = []
                for b in msg.content:
                    if hasattr(b, "type") and b.type == "text" and hasattr(b, "text"):
                        parts.append(b.text)
                    elif isinstance(b, dict) and b.get("type") == "text":
                        parts.append(b.get("text", ""))
                text = "".join(parts)
                arr = json.loads(text)
            else:
                # mock provider — synthesize list from schema
                props = schema_dict_single.get("properties", {})
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
                arr = []
                for _inp in (input_list or []):
                    obj = {k: _default_for(props.get(k)) for k in schema_dict_single.get("required", [])}
                    arr.append(obj)
            # Validate each item
            out = []
            for item in arr:
                validate_against_shape(item, schema_name, shapes)
                out.append(item)
            return out
        except Exception as e:
            last_err = e
            input_list = [{"original": x, "error": str(e)} for x in (input_list or [])]
            continue
    raise RuntimeError(f"LLM batch failed schema validation after {retries} attempts: {last_err}")


def exec_fn(fn, shapes, fns, inbound=None, tools=None):
    env, result = {}, None
    if inbound is not None:
        declared_inputs = (fn.get("in") or {})
        if declared_inputs:
            if len(declared_inputs) == 1 and isinstance(inbound, dict):
                # Single input with dict inbound - check if dict has matching key
                input_name = next(iter(declared_inputs.keys()))
                if input_name in inbound:
                    env[input_name] = inbound[input_name]
                else:
                    env[input_name] = inbound
            elif len(declared_inputs) == 1:
                # Single input with scalar inbound - bind directly
                input_name = next(iter(declared_inputs.keys()))
                env[input_name] = inbound
            else:
                # Multiple inputs - map entire inbound to each
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
            "tools": tools or {},
            "ops": OPS,  # Pass the operations registry to operations
            "original_args": args,  # Pass original unresolved args for ops that need them
            "exec_fn": lambda _fn, _inb=None: exec_fn(_fn, shapes, fns, inbound=_inb, tools=tools),
            "call_llm": lambda task, input_obj, schema, _shapes, retries=3, provider=None, model=None: call_llm(task, input_obj, schema, shapes, retries=retries, provider=provider, model=model),
            "call_llm_batch": lambda task, items, schema, _shapes, retries=3, provider=None, model=None: call_llm_batch(task, items, schema, shapes, retries=retries, provider=provider, model=model),
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

    # Handle @expect - either as a type validation or as a result template
    expect = fn.get("@expect")
    if expect:
        exp_type = expect.get("type") if isinstance(expect, dict) else None
        
        # If @expect is a dict without a type field, use it as a template for the result
        if isinstance(expect, dict) and not exp_type:
            # Resolve the template using the environment
            result = resolve_args(expect, env)
        elif exp_type:
            # Original type-based handling
            synth = expect.get("synthesize") is True
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

    # Provenance opt-in: suppress hashes if ALP_PROVENANCE_MINIMAL=1
    minimal_prov = os.getenv("ALP_PROVENANCE_MINIMAL", "0") in ("1", "true", "yes")
    trace = {
        "node": fn.get("id"),
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "outputs_hash": None if minimal_prov else hash_obj(result),
        "status": "ok",
        "provenance": provenance if provenance else None,
    }
    return result, trace


def run(path):
    # load stdlib ops
    # Import stdlib ops package
    from runtime.stdlib import register_all as _register_all
    _register_all(OPS, register_op)

    shapes, fns, flow, tools = load_graph(path)
    if not flow:
        # fallback to any no-input fn; if multiple, run the first deterministically by id
        candidates = [k for k, fn in fns.items() if not fn.get("in")]
        if candidates:
            start = sorted(candidates)[0]
            flow = [[start, None, {}]]
    if not flow:
        raise RuntimeError("No runnable nodes.")

    traces = []
    data_out_by_node = {}
    executed = set()
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

    # Build adjacency and indegree for toposort
    adj = {k: [] for k in fns.keys()}
    indeg = {k: 0 for k in fns.keys()}
    edge_meta = {}
    for src, dst, meta in flow:
        if dst:
            adj[src].append(dst)
            indeg[dst] += 1
            edge_meta[(src, dst)] = meta or {}
        else:
            # terminal node from src
            edge_meta[(src, None)] = meta or {}
    # queue nodes with indegree 0 that are actually in the flow
    flow_nodes = set()
    for src, dst, meta in flow:
        flow_nodes.add(src)
        if dst:
            flow_nodes.add(dst)
    order = [k for k in fns.keys() if indeg.get(k, 0) == 0 and k in flow_nodes]
    # If graph has no edges, order will contain all nodes
    from collections import deque
    q = deque(order)
    last_result = None
    while q:
        node_id = q.popleft()
        if node_id in executed:
            continue
        # inbound: prefer any predecessor's data if available, else last_result
        inbound = None
        # Try to find any predecessor result
        preds = [s for (s, d) in edge_meta.keys() if d == node_id]
        for p in preds:
            if p in data_out_by_node:
                inbound = data_out_by_node[p]
                break
        if inbound is None:
            inbound = last_result
        # Evaluate this node
        result, tr = exec_fn(fns[node_id], shapes, fns, inbound=inbound, tools=tools)
        traces.append(tr)
        data_out_by_node[node_id] = result
        last_result = result
        executed.add(node_id)
        # Enqueue neighbors whose indegree is now zero
        for v in adj.get(node_id, []):
            indeg[v] -= 1
            if indeg[v] == 0:
                # Check condition on edge
                meta = edge_meta.get((node_id, v)) or {}
                if eval_when(meta.get("when"), result):
                    q.append(v)
        # If this node had a terminal edge (dst None), check its when
        term_meta = edge_meta.get((node_id, None)) or {}
        if term_meta.get("when") is not None:
            # can be used to mark this as an output
            pass

    # Result: prefer last_result, else any terminal nodes' results
    print(json.dumps({"result": last_result, "trace": traces}, indent=2))


if __name__ == "__main__":
    run(sys.argv[1])
