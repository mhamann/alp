import os
import sys
import glob as glob_module
import shutil
from pathlib import Path


def register(reg):
    def _io_root() -> str:
        return os.getenv("ALP_IO_ROOT", os.getcwd())

    def _io_allow_write() -> bool:
        return os.getenv("ALP_IO_ALLOW_WRITE", "0") in ("1", "true", "yes")

    def _safe_path_join(root: str, path: str) -> str:
        base = os.path.abspath(root)
        target = os.path.abspath(os.path.join(base, path))
        if not target.startswith(base + os.sep) and target != base:
            raise RuntimeError("Path escapes IO root")
        return target
    
    def _get_safe_path(path_str):
        """Ensure path is under ALP_IO_ROOT (alias for consistency)."""
        root = _io_root()
        return _safe_path_join(root, path_str)

    # Original file I/O operations
    def read_file(a, ctx):
        path = a.get("path")
        if not isinstance(path, str) or not path:
            raise RuntimeError("read_file requires 'path'")
        root = _io_root()
        abs_path = _safe_path_join(root, path)
        encoding = a.get("encoding") or "utf-8"
        with open(abs_path, "r", encoding=encoding) as f:
            text = f.read()
        return {"text": text}

    def write_file(a, ctx):
        if not _io_allow_write():
            raise RuntimeError("Writes disabled. Set ALP_IO_ALLOW_WRITE=1 to enable.")
        path = a.get("path")
        text = a.get("text", "")
        if not isinstance(path, str) or not path:
            raise RuntimeError("write_file requires 'path'")
        root = _io_root()
        abs_path = _safe_path_join(root, path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        encoding = a.get("encoding") or "utf-8"
        mode = "a" if a.get("append") else "w"
        with open(abs_path, mode, encoding=encoding) as f:
            f.write(str(text))
        return {"ok": True}

    def read_stdin(a, ctx):
        allow = os.getenv("ALP_STDIN_ALLOW", "0") in ("1", "true", "yes")
        if not allow:
            raise RuntimeError("Stdin reads disabled. Set ALP_STDIN_ALLOW=1 to enable.")
        mode = (a.get("mode") or "all").lower()
        try:
            max_bytes = int(a.get("max_bytes") or os.getenv("ALP_STDIN_MAX_BYTES", "1000000"))
        except Exception:
            max_bytes = 1000000
        if mode == "line":
            line = sys.stdin.readline()
            return {"text": line[:max_bytes]}
        data = sys.stdin.read(max_bytes)
        return {"text": data}

    # Enhanced file system operations
    def list_files(a, ctx):
        """List files in a directory."""
        path = a.get("path", ".")
        pattern = a.get("pattern", "*")
        recursive = a.get("recursive", False)
        file_type = a.get("type", "all")
        
        try:
            safe_path = _get_safe_path(path)
            
            if recursive:
                full_pattern = os.path.join(safe_path, "**", pattern)
                paths = glob_module.glob(full_pattern, recursive=True)
            else:
                full_pattern = os.path.join(safe_path, pattern)
                paths = glob_module.glob(full_pattern)
            
            # Filter by type
            result = []
            for p in paths:
                if file_type == "file" and os.path.isfile(p):
                    result.append(os.path.relpath(p, safe_path))
                elif file_type == "dir" and os.path.isdir(p):
                    result.append(os.path.relpath(p, safe_path))
                elif file_type == "all":
                    result.append(os.path.relpath(p, safe_path))
            
            return {"files": result, "count": len(result)}
        except Exception as e:
            return {"files": [], "count": 0, "error": str(e)}
    
    def file_exists(a, ctx):
        """Check if a file or directory exists."""
        path = a.get("path", "")
        
        try:
            safe_path = _get_safe_path(path)
            exists = os.path.exists(safe_path)
            
            if exists:
                is_file = os.path.isfile(safe_path)
                is_dir = os.path.isdir(safe_path)
                return {
                    "exists": True,
                    "type": "file" if is_file else "dir" if is_dir else "other",
                    "path": path
                }
            else:
                return {"exists": False, "path": path}
        except Exception as e:
            return {"exists": False, "path": path, "error": str(e)}
    
    def glob(a, ctx):
        """Find files matching a pattern."""
        pattern = a.get("pattern", "*")
        root = a.get("root", ".")
        recursive = a.get("recursive", "**" in pattern)
        
        try:
            safe_root = _get_safe_path(root)
            full_pattern = os.path.join(safe_root, pattern)
            
            matches = glob_module.glob(full_pattern, recursive=recursive)
            
            # Return relative paths
            result = [os.path.relpath(m, safe_root) for m in matches]
            
            return {"matches": result, "count": len(result)}
        except Exception as e:
            return {"matches": [], "count": 0, "error": str(e)}
    
    def file_info(a, ctx):
        """Get detailed information about a file."""
        path = a.get("path", "")
        
        try:
            safe_path = _get_safe_path(path)
            
            if not os.path.exists(safe_path):
                return {"exists": False, "path": path}
            
            stat = os.stat(safe_path)
            
            return {
                "exists": True,
                "path": path,
                "size": stat.st_size,
                "modified": stat.st_mtime,
                "created": stat.st_ctime,
                "is_file": os.path.isfile(safe_path),
                "is_dir": os.path.isdir(safe_path),
                "readable": os.access(safe_path, os.R_OK),
                "writable": os.access(safe_path, os.W_OK),
                "extension": os.path.splitext(path)[1]
            }
        except Exception as e:
            return {"exists": False, "path": path, "error": str(e)}
    
    def mkdir(a, ctx):
        """Create a directory."""
        if not _io_allow_write():
            return {"created": False, "error": "Write operations disabled"}
        
        path = a.get("path", "")
        parents = a.get("parents", True)
        exist_ok = a.get("exist_ok", True)
        
        try:
            safe_path = _get_safe_path(path)
            
            if parents:
                os.makedirs(safe_path, exist_ok=exist_ok)
            else:
                os.mkdir(safe_path)
            
            return {"created": True, "path": path}
        except FileExistsError:
            if exist_ok:
                return {"created": False, "path": path, "existed": True}
            else:
                return {"created": False, "path": path, "error": "Directory already exists"}
        except Exception as e:
            return {"created": False, "path": path, "error": str(e)}
    
    def copy_file(a, ctx):
        """Copy a file or directory."""
        if not _io_allow_write():
            return {"copied": False, "error": "Write operations disabled"}
        
        source = a.get("source", "")
        destination = a.get("destination", "")
        overwrite = a.get("overwrite", False)
        
        try:
            safe_source = _get_safe_path(source)
            safe_dest = _get_safe_path(destination)
            
            if not os.path.exists(safe_source):
                return {"copied": False, "error": "Source does not exist"}
            
            if os.path.exists(safe_dest) and not overwrite:
                return {"copied": False, "error": "Destination already exists"}
            
            if os.path.isfile(safe_source):
                shutil.copy2(safe_source, safe_dest)
            else:
                shutil.copytree(safe_source, safe_dest, dirs_exist_ok=overwrite)
            
            return {"copied": True, "source": source, "destination": destination}
        except Exception as e:
            return {"copied": False, "error": str(e)}
    
    def move_file(a, ctx):
        """Move/rename a file or directory."""
        if not _io_allow_write():
            return {"moved": False, "error": "Write operations disabled"}
        
        source = a.get("source", "")
        destination = a.get("destination", "")
        overwrite = a.get("overwrite", False)
        
        try:
            safe_source = _get_safe_path(source)
            safe_dest = _get_safe_path(destination)
            
            if not os.path.exists(safe_source):
                return {"moved": False, "error": "Source does not exist"}
            
            if os.path.exists(safe_dest) and not overwrite:
                return {"moved": False, "error": "Destination already exists"}
            
            shutil.move(safe_source, safe_dest)
            
            return {"moved": True, "source": source, "destination": destination}
        except Exception as e:
            return {"moved": False, "error": str(e)}
    
    def delete_file(a, ctx):
        """Delete a file or directory."""
        if not _io_allow_write():
            return {"deleted": False, "error": "Write operations disabled"}
        
        path = a.get("path", "")
        recursive = a.get("recursive", False)
        
        try:
            safe_path = _get_safe_path(path)
            
            if not os.path.exists(safe_path):
                return {"deleted": False, "error": "Path does not exist"}
            
            if os.path.isfile(safe_path):
                os.remove(safe_path)
            elif os.path.isdir(safe_path):
                if recursive:
                    shutil.rmtree(safe_path)
                else:
                    os.rmdir(safe_path)
            
            return {"deleted": True, "path": path}
        except Exception as e:
            return {"deleted": False, "path": path, "error": str(e)}
    
    def path_join(a, ctx):
        """Join path components."""
        parts = a.get("parts", [])
        
        if not parts:
            return {"path": ""}
        
        result = os.path.join(*[str(p) for p in parts])
        return {"path": result}
    
    def path_split(a, ctx):
        """Split a path into components."""
        path = a.get("path", "")
        
        dirname, basename = os.path.split(path)
        name, ext = os.path.splitext(basename)
        
        return {
            "dir": dirname,
            "base": basename,
            "name": name,
            "ext": ext,
            "parts": path.split(os.sep) if path else []
        }
    
    # Register all operations
    reg("read_file", read_file)
    reg("write_file", write_file)
    reg("read_stdin", read_stdin)
    reg("list_files", list_files)
    reg("file_exists", file_exists)
    reg("glob", glob)
    reg("file_info", file_info)
    reg("mkdir", mkdir)
    reg("copy_file", copy_file)
    reg("move_file", move_file)
    reg("delete_file", delete_file)
    reg("path_join", path_join)
    reg("path_split", path_split)