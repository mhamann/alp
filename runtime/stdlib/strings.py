import re
import base64
import hashlib
import urllib.parse
import html


def register(reg):
    # Original string operations
    def concat(a, ctx):
        items = a.get("items")
        if items is not None:
            return "".join(str(x) for x in items)
        return str(a.get("a", "")) + str(a.get("b", ""))

    def join(a, ctx):
        items = a.get("items") or []
        sep = str(a.get("sep", ""))
        return sep.join(str(x) for x in items)

    def split(a, ctx):
        text = str(a.get("text", ""))
        sep = str(a.get("sep", ","))
        return text.split(sep)

    # Enhanced string operations
    def regex_match(a, ctx):
        """Match a string against a regular expression."""
        text = str(a.get("text", ""))
        pattern = a.get("pattern", "")
        flags_str = a.get("flags", "")
        
        # Build regex flags
        flags = 0
        if "i" in flags_str:
            flags |= re.IGNORECASE
        if "m" in flags_str:
            flags |= re.MULTILINE
        if "s" in flags_str:
            flags |= re.DOTALL
        
        try:
            match = re.search(pattern, text, flags)
            if match:
                return {
                    "matched": True,
                    "text": match.group(0),
                    "groups": list(match.groups()),
                    "start": match.start(),
                    "end": match.end()
                }
            else:
                return {"matched": False, "text": None, "groups": []}
        except re.error as e:
            return {"matched": False, "error": str(e)}
    
    def regex_replace(a, ctx):
        """Replace matches of a pattern in a string."""
        text = str(a.get("text", ""))
        pattern = a.get("pattern", "")
        replacement = a.get("replacement", "")
        flags_str = a.get("flags", "")
        count = a.get("count", 0)
        
        # Build regex flags
        flags = 0
        if "i" in flags_str:
            flags |= re.IGNORECASE
        if "m" in flags_str:
            flags |= re.MULTILINE
        if "s" in flags_str:
            flags |= re.DOTALL
        
        try:
            result, num_replacements = re.subn(pattern, replacement, text, count=count, flags=flags)
            return {"result": result, "count": num_replacements}
        except re.error as e:
            return {"result": text, "count": 0, "error": str(e)}
    
    def replace(a, ctx):
        """Simple string replacement."""
        text = str(a.get("text", ""))
        find = str(a.get("find", ""))
        replace_with = str(a.get("replace", ""))
        count = a.get("count", -1)
        
        if count == -1:
            result = text.replace(find, replace_with)
        else:
            result = text.replace(find, replace_with, count)
        
        replacements = text.count(find) if count == -1 else min(count, text.count(find))
        return {"result": result, "count": replacements}
    
    def format_string(a, ctx):
        """Format a string with placeholders."""
        template = str(a.get("template", ""))
        values = a.get("values", {})
        safe = a.get("safe", True)
        
        try:
            if safe:
                # Safe formatting - ignore missing keys
                from string import Template
                t = Template(template.replace("{", "${").replace("}", "}"))
                result = t.safe_substitute(values)
                result = result.replace("${", "{").replace("}", "}")
            else:
                result = template.format(**values)
            return {"result": result}
        except (KeyError, ValueError) as e:
            return {"result": template, "error": str(e)}
    
    def trim(a, ctx):
        """Remove whitespace from string."""
        text = str(a.get("text", ""))
        mode = a.get("mode", "both")
        chars = a.get("chars")
        
        if mode == "left":
            result = text.lstrip(chars)
        elif mode == "right":
            result = text.rstrip(chars)
        else:
            result = text.strip(chars)
        
        return {"result": result}
    
    def case_convert(a, ctx):
        """Convert string case."""
        text = str(a.get("text", ""))
        mode = a.get("mode", "lower")
        
        if mode == "upper":
            result = text.upper()
        elif mode == "lower":
            result = text.lower()
        elif mode == "title":
            result = text.title()
        elif mode == "capitalize":
            result = text.capitalize()
        elif mode == "snake":
            # Convert to snake_case
            result = re.sub(r'(?<!^)(?=[A-Z])', '_', text).lower()
            result = re.sub(r'[\s-]+', '_', result)
        elif mode == "camel":
            # Convert to camelCase
            words = re.split(r'[\s_-]+', text)
            if words:
                result = words[0].lower() + ''.join(w.capitalize() for w in words[1:])
            else:
                result = text
        else:
            result = text
        
        return {"result": result}
    
    def substring(a, ctx):
        """Extract substring from string."""
        text = str(a.get("text", ""))
        start = a.get("start", 0)
        end = a.get("end")
        length = a.get("length")
        
        if length is not None and end is None:
            end = start + length
        
        if end is None:
            result = text[start:]
        else:
            result = text[start:end]
        
        return {"result": result}
    
    def encode_decode(a, ctx):
        """Encode or decode strings."""
        text = str(a.get("text", ""))
        operation = a.get("operation", "encode")
        format_type = a.get("format", "base64")
        
        try:
            if format_type == "base64":
                if operation == "encode":
                    result = base64.b64encode(text.encode()).decode()
                else:
                    result = base64.b64decode(text).decode()
            elif format_type == "url":
                if operation == "encode":
                    result = urllib.parse.quote(text)
                else:
                    result = urllib.parse.unquote(text)
            elif format_type == "hex":
                if operation == "encode":
                    result = text.encode().hex()
                else:
                    result = bytes.fromhex(text).decode()
            elif format_type == "html":
                if operation == "encode":
                    result = html.escape(text)
                else:
                    result = html.unescape(text)
            else:
                result = text
            
            return {"result": result}
        except Exception as e:
            return {"result": text, "error": str(e)}
    
    def hash_string(a, ctx):
        """Generate hash of string."""
        text = str(a.get("text", ""))
        algorithm = a.get("algorithm", "sha256")
        
        try:
            if algorithm == "md5":
                h = hashlib.md5(text.encode())
            elif algorithm == "sha1":
                h = hashlib.sha1(text.encode())
            elif algorithm == "sha256":
                h = hashlib.sha256(text.encode())
            elif algorithm == "sha512":
                h = hashlib.sha512(text.encode())
            else:
                return {"hash": None, "error": f"Unknown algorithm: {algorithm}"}
            
            return {"hash": h.hexdigest(), "algorithm": algorithm}
        except Exception as e:
            return {"hash": None, "error": str(e)}
    
    # Register all operations
    reg("concat", concat)
    reg("join", join)
    reg("split", split)
    reg("regex_match", regex_match)
    reg("regex_replace", regex_replace)
    reg("replace", replace)
    reg("format", format_string)
    reg("trim", trim)
    reg("case", case_convert)
    reg("substring", substring)
    reg("encode_decode", encode_decode)
    reg("hash", hash_string)