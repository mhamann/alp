# Artificial Logic Protocol (ALP)

A programming language designed specifically for Large Language Models (LLMs).

## Why ALP?

LLMs need a programming language that matches how they process information - as structured data flows rather than imperative step-by-step instructions. Traditional programming languages were designed for humans and CPUs, but LLMs operate differently:

- **JSON-native**: LLMs excel at producing valid JSON, making it the ideal syntax
- **Declarative**: Define what should happen, not how - perfect for LLM reasoning
- **Graph-based**: Natural representation of data dependencies and parallel operations
- **Type-safe**: Strong typing with validation prevents common LLM errors
- **Sandboxed**: Security-first design prevents unintended system access

ALP bridges the gap between natural language and computation, giving LLMs a reliable way to express complex logic, orchestrate API calls, and process data - all while maintaining safety and predictability.

## Run

```bash
uv run python main.py           # runs examples/hello_world.alp
uv run python main.py examples/calculator.alp
ALP_HTTP_ALLOWLIST=example.com uv run python main.py examples/io_example.alp
```

## Language features

- `@def` — declares type aliases, unions, literals, and constrained types
- `@shape` — declares simple structs with fields and primitive types (`str`, `int`, `float`, `bool`, `ts`)
- `@tool` — declares external tool definitions for command, HTTP, and Python integrations
- `@fn` — function node with optional `in`, `out`, `@const`, `@op`, `@llm`, `@expect`, `@retry`
- `@flow` — list of edges `[src, dst, meta]`

### Type definitions with `@def`

The `@def` construct supports advanced type definitions beyond basic structs:

- **Type aliases**: `{"kind":"@def","id":"UserId","type":"str"}`
- **Union types**: `{"kind":"@def","id":"StringOrNumber","type":"str | int"}`
- **Literal enums**: `{"kind":"@def","id":"Status","type":["pending","success","error"]}`
- **Constrained types**: `{"kind":"@def","id":"Email","type":"str","constraint":{"pattern":"^[^@]+@[^@]+$"}}`

Supported constraints: `minLength`, `maxLength`, `pattern` (regex), `min`, `max` for numbers.

### External tool integration with `@tool`

The `@tool` construct enables integration with external systems:

- **Command tools**: Execute shell commands with argument substitution
  ```json
  {"kind":"@tool","id":"git_status","implementation":{"type":"command","command":"git status --porcelain"}}
  ```

- **HTTP tools**: Make REST API calls with URL templating
  ```json
  {"kind":"@tool","id":"weather","implementation":{"type":"http","url":"https://api.weather.com/v1/current?q={city}","method":"GET"}}
  ```

- **Python tools**: Call Python functions from whitelisted modules
  ```json
  {"kind":"@tool","id":"analyze","implementation":{"type":"python","module":"mytools","function":"analyze_data"}}
  ```

Use tools via the `tool_call` operation: `["tool_call", {"tool": "tool_id", "args": {"param": "value"}}]`

**Security**: Tools require explicit allowlists via environment variables (`ALP_TOOL_ALLOW_COMMANDS`, `ALP_HTTP_ALLOWLIST`, `ALP_TOOL_PYTHON_MODULES`).

### Stable vocabulary (tokens <-> concept IDs)

- The VM accepts either textual tokens or stable concept IDs (CIDs) shipped with the SDK for core constructs.
- Supported tokens: `@def`, `@fn`, `@op`, `@llm`, `@tool`, `@flow`, `@in`, `@out`, `@expect`, `@shape`, `@intent`, `@emb`, `@pkg`, `@caps`, `@const`, `@var`, `@err`, `@retry`, `@cache`, `@idemp`, `@trace`, `@hash`, `@ver`, `@meta`, `@test`.
- Keys `@in`/`@out` normalize to `in`/`out` fields for compatibility with existing programs.
- See `runtime/vocab.py` for the token->CID mapping and meanings, and to export the list for SDKs.

### Built-in ops

#### Math Operations
- `add({ a, b }) -> number`
- `sub({ a, b }) -> number`
- `mul({ a, b }) -> number`
- `div({ a, b }) -> number` — raises on division by zero
- `pow({ a, b }) -> number`
- `neg({ x }) -> number`
- `calc_eval({ expr }) -> { value }` — safe arithmetic evaluator supporting `+ - * / // % **`, parentheses, and `^` as exponent.
- `min({ a, b } | { items }) -> number`, `max({ a, b } | { items }) -> number`, `abs({ x }) -> number`, `round({ x, ndigits? }) -> number`
- `sum({ items:list<number> }) -> number`, `avg({ items:list<number> }) -> number`

#### String Operations
- `concat({ a, b } | { items }) -> string`, `join({ items, sep }) -> string`, `split({ text, sep }) -> list<string>`
- `regex_match({ text, pattern, flags? }) -> { matched, text, groups, start, end }` — regex pattern matching
- `regex_replace({ text, pattern, replacement, flags?, count? }) -> { result, count }` — regex substitution
- `replace({ text, find, replace, count? }) -> { result, count }` — simple string replacement
- `format({ template, values, safe? }) -> { result }` — string formatting with {key} placeholders
- `trim({ text, mode?, chars? }) -> { result }` — remove whitespace or specified chars
- `case({ text, mode }) -> { result }` — case conversion (upper, lower, title, capitalize, snake, camel)
- `substring({ text, start, end?|length? }) -> { result }` — extract substring
- `encode_decode({ text, operation, format }) -> { result }` — encode/decode (base64, url, hex, html)
- `hash({ text, algorithm }) -> { hash }` — generate hash (md5, sha1, sha256, sha512)

#### Control Flow
- `if({ condition, then, else? }) -> any` — conditional execution
- `switch({ value, cases, default? }) -> any` — multi-branch selection
- `try({ do, catch, finally? }) -> { result, error, success }` — error handling

#### JSON Operations
- `json_parse({ text }) -> object` — parse JSON string
- `json_get({ obj, path }) -> any` — get value at dot path
- `json_set({ obj, path, value, create? }) -> { result, modified }` — set value at path
- `json_merge({ objects, deep? }) -> { result }` — merge multiple objects
- `json_filter({ array, field?, value?, condition?, fn? }) -> { result, count }` — filter array elements
- `json_map({ array, field?, fn?, template? }) -> { result, count }` — transform array elements
- `json_delete({ obj, path }) -> { result, deleted }` — delete path from object

#### File System Operations
- `read_file({ path, encoding? }) -> { text }` — read file contents
- `write_file({ path, text, encoding?, append? }) -> { ok }` — write file
- `list_files({ path?, pattern?, recursive?, type? }) -> { files, count }` — list directory contents
- `file_exists({ path }) -> { exists, type }` — check file/directory existence
- `glob({ pattern, root?, recursive? }) -> { matches, count }` — find files by pattern
- `file_info({ path }) -> { size, modified, created, ... }` — get file metadata
- `mkdir({ path, parents?, exist_ok? }) -> { created }` — create directory
- `copy_file({ source, destination, overwrite? }) -> { copied }` — copy file/directory
- `move_file({ source, destination, overwrite? }) -> { moved }` — move/rename file
- `delete_file({ path, recursive? }) -> { deleted }` — delete file/directory
- `path_join({ parts }) -> { path }` — join path components
- `path_split({ path }) -> { dir, base, name, ext, parts }` — split path into components

#### Other Operations
- `http({ method, url, headers?, json?|data? }) -> { status:int, text:str }` — HTTP requests
- `tool_call({ tool, args }) -> object` — call external tool defined with `@tool`
- `read_stdin({ mode?: "all"|"line", max_bytes? }) -> { text }` (requires `ALP_STDIN_ALLOW=1`)

### Variables and argument resolution

- Use `$name` to reference inputs/consts in `@op` and `@llm.input`.
- Dotted paths are supported for nested dicts, e.g., `$input.expr`.
- Arguments now resolve recursively within lists and objects.

### Named op results

- Each `@op` can include an optional third metadata object: `{ "as": "name" }` to bind the op's result into the environment.
- Example:
  ```json
  ["add", {"a":1,"b":2}, {"as":"sum"}],
  ["mul", {"a":"$sum","b":3}, {"as":"prod"}]
  ```

### Flow conditions

- `@flow` edges support `{"when": <condition>}` to branch based on the last node's output.
- Conditions support: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `and`, `or`, `not`, and direct `$value` truthiness.
- Example:
  ```json
  {"kind":"@flow","edges":[["start","pos",{"when":{"gt":["$value",0]}}]]}
  ```

### Collections in shapes

- Shapes support `list<T>`, `list`, `map<T>`, `map` primitive collections.
- Validator checks container types and primitive element types when specified.

### Shapes: optional fields, enums, defaults
### Iteration

- `map_each({ items:list<any>, fn:"FnId", param? }) -> list<any>`: calls the function `fn` for each item, passing the item as inbound.
  - If `param` is provided, the inbound will be wrapped as `{ param: item }`.

### Debugging

- Set `ALP_EXPLAIN=1` to print an env snapshot to stderr after each op.

### I/O and HTTP sandboxing

- File I/O is restricted to `ALP_IO_ROOT` (defaults to current working directory). Writes require `ALP_IO_ALLOW_WRITE=1`.
- HTTP is disabled by default. Allow specific hosts with `ALP_HTTP_ALLOWLIST=host1,host2`. Local/Private IPs are blocked unless `ALP_HTTP_BLOCK_LOCAL=0`.
 - Stdin reads are disabled by default. Enable with `ALP_STDIN_ALLOW=1`. Limit bytes with `ALP_STDIN_MAX_BYTES` or `max_bytes` arg.

- Optional fields: use `?` suffix, e.g., `"b?":"float"`.
- Enums: `"mode":"enum<fast,accurate>"` validates membership.
- Defaults: supply a `defaults` object in the `@shape` node; defaults are applied before validation.
  ```json
  {"kind":"@shape","id":"Settings","fields":{"mode":"enum<fast,accurate>","timeout?":"int"},"defaults":{"mode":"fast"}}
  ```

### LLM providers

Set env vars to enable real model calls (optional):

```bash
export ALP_MODEL_PROVIDER=openai
export OPENAI_API_KEY=sk-...
export OPENAI_MODEL=gpt-4o-mini
# or
export ALP_MODEL_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export ANTHROPIC_MODEL=claude-3-5-sonnet-20240620
```

When no provider is configured, a strict mock provider synthesizes JSON matching the schema.

Security: API keys are read from env vars only; do not hard-code keys in `.alp` files. Keep keys in your shell env or secrets manager.

## Examples

- `hello_world.alp` — greeting piped into an LLM `respond` node
- `calculator.alp` — demonstrates arithmetic and expression evaluation
- `io_example.alp` — file read and HTTP fetch with sandboxing
- `http_example.alp` — GitHub API fetch, JSON parse, and field extraction
- `doc_summarizer_openai.alp` — uses OpenAI to summarize README into `SUMMARY_OPENAI.md`

See `ALP_SPEC.json` for a machine-ingestible specification of the language and VM behavior.
