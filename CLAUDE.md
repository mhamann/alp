# ALP Development Guide for Claude

## Project Overview
ALP (Artificial Logic Protocol) is a JSON-based declarative programming language designed specifically for LLMs. It uses line-delimited JSON where each line is a complete JSON object.

## Architecture

### Core Components
- **VM** (`runtime/vm.py`) - Main execution engine
- **Stdlib** (`runtime/stdlib/`) - Standard library operations
- **Extras** (`runtime/extras/`) - Optional modules like UI

### Key Concepts
1. **Shapes** - Type definitions for data structures
2. **Functions** - Declarative operations with @op chains
3. **Flows** - Execution graphs connecting functions
4. **Imports** - Reuse code from other .alp files
5. **Tools** - External command/HTTP/Python integrations

## Building UI Applications

### Architecture Principles
**IMPORTANT**: Maintain strict separation of concerns:
- **UI Layer** (`examples/ui/*.alp`) - ONLY handles interface and orchestration
- **Logic Layer** (`examples/*.alp`) - Contains actual business logic
- **Never duplicate logic** - Always use @import to reuse existing functions

### UI Development Pattern
```json
// 1. Import logic modules
{"kind":"@import","path":"../calculator.alp"}

// 2. Create UI handler that orchestrates imported functions
{"kind":"@fn","id":"ui_handler","in":"UserInput","out":"Result",
  "@op":[["calc_entry", {"expr":"$in.expression"}]]}

// 3. Build UI and connect handler
{"kind":"@fn","id":"create_ui","@op":[
  ["ui_create",{"title":"My App"}],
  ["ui_add_input",{"name":"expression","type":"textbox"}],
  ["ui_add_output",{"name":"result","type":"json"}],
  ["ui_set_handler",{"function":"ui_handler","inputs":["expression"],"outputs":["result"]}],
  ["ui_launch",{"port":7860}],
  ["ui_wait",{}]
]}
```

### UI Operations (in extras)
- `ui_create` - Initialize UI with title and theme
- `ui_add_input` - Add input components (textbox, number, slider, dropdown)
- `ui_add_output` - Add output displays (textbox, json, markdown)
- `ui_set_handler` - Connect ALP function to UI events
- `ui_launch` - Start Gradio server on specified port
- `ui_wait` - Keep server running

### Best Practices
1. **Import, don't duplicate** - UI files should import logic modules
2. **Clear naming** - Prefix UI functions with `ui_` or `create_*_ui`
3. **Pure orchestration** - UI functions only coordinate, never calculate
4. **Port management** - Use different ports for concurrent UIs (7860, 7861, 7862)

## Testing

### Running Examples
```bash
# Regular programs
uv run python main.py examples/calculator.alp

# UI programs (auto-detected and launched)
uv run python main.py examples/ui/simple_calculator.alp
```

### Test Suite
```bash
uv run python main.py --test tests.jsonl
```

## Common Operations

### Math & Calculation
- Basic: `add`, `sub`, `mul`, `div`, `pow`, `neg`
- Advanced: `min`, `max`, `abs`, `round`, `sum`, `avg`
- Expression evaluation: `calc_eval` (safe arithmetic evaluator)

### String Operations
- `concat`, `join`, `split` - Basic string manipulation
- All extended string operations are in stdlib/strings.py

### JSON Operations  
- `json_parse`, `json_get` - Parse and access JSON
- All extended JSON operations are in stdlib/jsonlib.py

### File I/O
- `read_file`, `write_file` - Basic file operations
- All extended file operations are in stdlib/io.py
- Security: Sandboxed to ALP_IO_ROOT

### HTTP
- `http` - Generic HTTP client
- Security: Requires ALP_HTTP_ALLOWLIST

### Conditionals
- `if` - Conditional execution with then/else branches
- `switch` - Multi-case branching
- `try_catch` - Error handling with optional finally

## Environment Variables

### Core Settings
- `ALP_IO_ROOT` - Root directory for file operations
- `ALP_IO_ALLOW_WRITE` - Enable write operations (0/1)
- `ALP_HTTP_ALLOWLIST` - Comma-separated allowed hostnames
- `ALP_EXPLAIN` - Debug mode to print execution steps

### LLM Providers
- `ALP_MODEL_PROVIDER` - mock|openai|anthropic
- `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` - API credentials

## Code Style Guidelines

### ALP Files
1. One JSON object per line
2. Use descriptive IDs for shapes and functions
3. Document complex operations with clear naming
4. Group related operations in functions

### Python Extensions
1. Operations must be pure functions
2. Return dictionaries for structured data
3. Handle errors gracefully with try/catch
4. Include type hints and docstrings

## Common Patterns

### Error Handling
```json
{"kind":"@fn","id":"safe_operation","@op":[
  ["try_catch",{
    "try":[["risky_op",{}]],
    "catch":[["log_error",{"msg":"$error"}]],
    "finally":[["cleanup",{}]]
  }]
]}
```

### Data Pipeline
```json
{"kind":"@fn","id":"pipeline","@op":[
  ["read_file",{"path":"data.json"},{"as":"raw"}],
  ["json_parse",{"text":"$raw.text"},{"as":"data"}],
  ["process",{"input":"$data"},{"as":"result"}],
  ["write_file",{"path":"output.json","text":"$result"}]
]}
```

### UI with Logic Separation
```json
// logic.alp
{"kind":"@fn","id":"calculate","@op":[["calc_eval",{"expr":"$in"}]]}

// ui.alp
{"kind":"@import","path":"logic.alp"}
{"kind":"@fn","id":"ui_handler","@op":[["calculate","$in.expr"]]}
```

## Debugging Tips

1. Use `ALP_EXPLAIN=1` to see execution steps
2. Check file permissions for I/O operations
3. Verify allowlists for HTTP requests
4. Test functions independently before UI integration
5. Use meaningful error messages in try/catch blocks

## Performance Considerations

1. Minimize file I/O operations
2. Cache computed results when possible
3. Use efficient data structures (avoid deep nesting)
4. Import only needed functions from modules
5. Keep UI handlers lightweight - delegate to logic functions