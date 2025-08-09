# Artificial Logic Protocol (ALP)
A programming language/protocol designed specifically for LLMs

## Run

```bash
uv run python main.py           # runs examples/hello_world.alp
uv run python main.py examples/calculator.alp
ALP_HTTP_ALLOWLIST=example.com uv run python main.py examples/io_example.alp
```

## Language features

- `@shape` — declares simple structs with fields and primitive types (`str`, `int`, `float`, `bool`, `ts`)
- `@fn` — function node with optional `in`, `out`, `@const`, `@op`, `@llm`, `@expect`, `@retry`
- `@flow` — list of edges `[src, dst, meta]`

### Stable vocabulary (tokens <-> concept IDs)

- The VM accepts either textual tokens or stable concept IDs (CIDs) shipped with the SDK for core constructs.
- Supported tokens: `@def`, `@fn`, `@op`, `@llm`, `@tool`, `@flow`, `@in`, `@out`, `@expect`, `@shape`, `@intent`, `@emb`, `@pkg`, `@caps`, `@const`, `@var`, `@err`, `@retry`, `@cache`, `@idemp`, `@trace`, `@hash`, `@ver`, `@meta`, `@test`.
- Keys `@in`/`@out` normalize to `in`/`out` fields for compatibility with existing programs.
- See `runtime/vocab.py` for the token->CID mapping and meanings, and to export the list for SDKs.

### Built-in ops
- `add({ a, b }) -> number`
- `sub({ a, b }) -> number`
- `mul({ a, b }) -> number`
- `div({ a, b }) -> number` — raises on division by zero
- `pow({ a, b }) -> number`
- `neg({ x }) -> number`
- `calc_eval({ expr }) -> { value }` — safe arithmetic evaluator supporting `+ - * / // % **`, parentheses, and `^` as exponent.
- `min({ a, b } | { items }) -> number`, `max({ a, b } | { items }) -> number`, `abs({ x }) -> number`, `round({ x, ndigits? }) -> number`
- `sum({ items:list<number> }) -> number`, `avg({ items:list<number> }) -> number`
- Strings: `concat({ a, b } | { items }) -> string`, `join({ items, sep }) -> string`, `split({ text, sep }) -> list<string>`
- File I/O: `read_file({ path, encoding? }) -> { text }`, `write_file({ path, text, encoding?, append? }) -> { ok }`
- HTTP: Generic `http({ method, url, headers?, json?|data? }) -> { status:int, text:str }`
 - Stdin: `read_stdin({ mode?: "all"|"line", max_bytes? }) -> { text }` (requires `ALP_STDIN_ALLOW=1`)

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
