import json
from copy import deepcopy


def register(reg):
    # Original JSON operations
    def json_parse(a, ctx):
        text = a.get("text")
        if not isinstance(text, str):
            raise RuntimeError("json_parse requires 'text' string")
        try:
            return json.loads(text)
        except Exception as e:
            raise RuntimeError(f"json_parse failed: {e}")

    def json_get(a, ctx):
        obj = a.get("obj")
        path = a.get("path")
        if not isinstance(path, str) or not path:
            raise RuntimeError("json_get requires 'path'")
        cur = obj
        for part in path.split('.'):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list):
                try:
                    idx = int(part)
                except Exception:
                    raise RuntimeError("json_get index must be integer when traversing lists")
                if idx < 0 or idx >= len(cur):
                    raise RuntimeError("json_get index out of range")
                cur = cur[idx]
            else:
                raise RuntimeError("json_get path not found")
        return cur

    # Enhanced JSON operations
    def json_set(a, ctx):
        """Set a value at a path in a JSON object."""
        obj = deepcopy(a.get("obj", {}))
        path = a.get("path", "")
        value = a.get("value")
        create = a.get("create", True)
        
        if not path:
            return {"result": value, "modified": True}
        
        parts = path.split(".")
        current = obj
        
        # Navigate to parent of target
        for i, part in enumerate(parts[:-1]):
            if part.isdigit():
                idx = int(part)
                if isinstance(current, list):
                    while len(current) <= idx and create:
                        current.append(None)
                    current = current[idx]
                else:
                    if create:
                        current[part] = {}
                        current = current[part]
                    else:
                        return {"result": obj, "modified": False, "error": f"Path not found: {'.'.join(parts[:i+1])}"}
            else:
                if part not in current:
                    if create:
                        current[part] = {}
                    else:
                        return {"result": obj, "modified": False, "error": f"Path not found: {'.'.join(parts[:i+1])}"}
                current = current[part]
        
        # Set the final value
        final_key = parts[-1]
        if final_key.isdigit() and isinstance(current, list):
            idx = int(final_key)
            while len(current) <= idx and create:
                current.append(None)
            current[idx] = value
        else:
            current[final_key] = value
        
        return {"result": obj, "modified": True}
    
    def json_merge(a, ctx):
        """Merge multiple JSON objects together."""
        objects = a.get("objects", [])
        deep = a.get("deep", True)
        
        if not objects:
            return {"result": {}}
        
        def deep_merge(target, source):
            """Recursively merge source into target."""
            for key, value in source.items():
                if key in target and isinstance(target[key], dict) and isinstance(value, dict) and deep:
                    deep_merge(target[key], value)
                else:
                    target[key] = deepcopy(value) if deep else value
            return target
        
        result = deepcopy(objects[0]) if isinstance(objects[0], dict) else {}
        for obj in objects[1:]:
            if isinstance(obj, dict):
                if deep:
                    deep_merge(result, obj)
                else:
                    result.update(obj)
        
        return {"result": result}
    
    def json_filter(a, ctx):
        """Filter array elements based on conditions."""
        array = a.get("array", [])
        field = a.get("field")
        value = a.get("value")
        condition = a.get("condition")
        fn_id = a.get("fn")
        
        if not isinstance(array, list):
            return {"result": [], "count": 0}
        
        filtered = []
        
        for item in array:
            include = False
            
            # Function-based filtering
            if fn_id and "fns" in ctx:
                from runtime.vm import exec_fn
                fns = ctx.get("fns", {})
                if fn_id in fns:
                    result, _ = exec_fn(fns[fn_id], ctx.get("shapes", {}), fns, inbound=item)
                    include = bool(result if not isinstance(result, dict) else result.get("value", result))
            # Field-value filtering
            elif field and value is not None:
                if isinstance(item, dict) and field in item:
                    include = item[field] == value
            # Condition-based filtering
            elif condition:
                if isinstance(condition, dict):
                    if "eq" in condition:
                        check_field, check_value = condition["eq"]
                        if isinstance(item, dict):
                            include = item.get(check_field) == check_value
                    elif "ne" in condition:
                        check_field, check_value = condition["ne"]
                        if isinstance(item, dict):
                            include = item.get(check_field) != check_value
                    elif "gt" in condition:
                        check_field, check_value = condition["gt"]
                        if isinstance(item, dict):
                            include = item.get(check_field, 0) > check_value
                    elif "contains" in condition:
                        check_field, check_value = condition["contains"]
                        if isinstance(item, dict):
                            field_val = item.get(check_field, "")
                            include = check_value in str(field_val)
            else:
                # No filter specified, include all
                include = True
            
            if include:
                filtered.append(item)
        
        return {"result": filtered, "count": len(filtered)}
    
    def json_map(a, ctx):
        """Transform array elements."""
        array = a.get("array", [])
        field = a.get("field")
        fn_id = a.get("fn")
        
        # Get the original template from unresolved args if available
        original_args = ctx.get("original_args", {})
        template = original_args.get("template") if original_args else a.get("template")
        
        if not isinstance(array, list):
            return {"result": [], "count": 0}
        
        mapped = []
        
        for item in array:
            # Field extraction
            if field:
                if isinstance(item, dict):
                    mapped.append(item.get(field))
                else:
                    mapped.append(None)
            # Function transformation
            elif fn_id and "fns" in ctx:
                from runtime.vm import exec_fn
                fns = ctx.get("fns", {})
                if fn_id in fns:
                    result, _ = exec_fn(fns[fn_id], ctx.get("shapes", {}), fns, inbound=item)
                    mapped.append(result)
                else:
                    mapped.append(item)
            # Template transformation
            elif template:
                if isinstance(template, dict):
                    new_item = {}
                    for key, value in template.items():
                        if isinstance(value, str) and value.startswith("$"):
                            # Extract from item
                            path = value[1:]
                            if "." in path:
                                parts = path.split(".")
                                current = item
                                for part in parts:
                                    if isinstance(current, dict):
                                        current = current.get(part)
                                    else:
                                        current = None
                                        break
                                new_item[key] = current
                            else:
                                new_item[key] = item.get(path) if isinstance(item, dict) else None
                        else:
                            new_item[key] = value
                    mapped.append(new_item)
                else:
                    mapped.append(item)
            else:
                mapped.append(item)
        
        return {"result": mapped, "count": len(mapped)}
    
    def json_delete(a, ctx):
        """Delete a path from a JSON object."""
        obj = deepcopy(a.get("obj", {}))
        path = a.get("path", "")
        
        if not path:
            return {"result": obj, "deleted": False}
        
        parts = path.split(".")
        current = obj
        
        # Navigate to parent of target
        for part in parts[:-1]:
            if part.isdigit():
                idx = int(part)
                if isinstance(current, list) and idx < len(current):
                    current = current[idx]
                else:
                    return {"result": obj, "deleted": False, "error": "Path not found"}
            else:
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return {"result": obj, "deleted": False, "error": "Path not found"}
        
        # Delete the final key
        final_key = parts[-1]
        deleted = False
        
        if final_key.isdigit() and isinstance(current, list):
            idx = int(final_key)
            if idx < len(current):
                del current[idx]
                deleted = True
        elif isinstance(current, dict) and final_key in current:
            del current[final_key]
            deleted = True
        
        return {"result": obj, "deleted": deleted}
    
    # Register all operations
    reg("json_parse", json_parse)
    reg("json_get", json_get)
    reg("json_set", json_set)
    reg("json_merge", json_merge)
    reg("json_filter", json_filter)
    reg("json_map", json_map)
    reg("json_delete", json_delete)