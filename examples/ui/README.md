# ALP UI Examples

This directory demonstrates how to build user interfaces in ALP with proper separation of concerns.

## ✨ Key Principles

- **🎯 Separation of Concerns**: UI files handle interface only, logic lives elsewhere
- **📦 Import & Reuse**: UI imports logic modules rather than duplicating code
- **🔌 Pure Orchestration**: UI functions route events to imported logic functions
- **📱 Gradio Integration**: Web-based UIs powered by the extras/ui_gradio module

## 📁 Example

### simple_calculator.alp
A clean calculator interface demonstrating proper architecture:
- **Imports** `../calculator.alp` for core math logic
- **Delegates** all calculations to imported functions
- **Handles** only UI setup and event routing
- **Zero business logic** in the UI file itself

## 🚀 Usage

```bash
# Run the calculator UI (default port 7860)
uv run python main.py examples/ui/simple_calculator.alp
```

The UI will be available at the specified port (default: 7860).

## 🛠 UI Operations Reference

### Core Operations
- `ui_create(title, description, theme)` - Initialize UI configuration
- `ui_add_input(name, type, label, default, options)` - Add input component
- `ui_add_output(name, type, label)` - Add output component  
- `ui_set_handler(function, inputs, outputs)` - Connect ALP function
- `ui_launch(port, share, debug)` - Start Gradio server
- `ui_wait(timeout)` - Keep server running

### Input Component Types
- `textbox` - Text input with optional multiline support
- `number` - Numeric input with min/max validation
- `slider` - Range slider with step control
- `dropdown` - Selection from predefined options

### Output Component Types  
- `textbox` - Plain text display
- `json` - Formatted JSON with syntax highlighting
- `markdown` - Rich text with formatting support

## 🎯 Best Practices

### Separation of Concerns
1. **UI files** (`examples/ui/*.alp`) - Handle ONLY user interface and orchestration
2. **Logic files** (`examples/*.alp`) - Contain actual business logic and computations  
3. **Use `@import`** - UI files import logic modules rather than duplicating functionality

### Implementation Guidelines
1. **No Logic in UI**: UI files should not contain calculation or processing logic
2. **Import Core Modules**: Use `{"kind":"@import","path":"../calculator.alp"}` to reuse existing logic
3. **UI as Orchestrator**: UI functions orchestrate calls to imported logic functions
4. **Clear Naming**: Prefix UI-specific functions with `ui_` or use descriptive names
5. **Function Mapping**: Ensure UI input names match your ALP function's input shape
6. **Error Handling**: UI system gracefully handles function execution errors
7. **Port Management**: Use different ports for multiple concurrent UIs
8. **Resource Cleanup**: `ui_wait` ensures proper server lifecycle management

### Example Pattern

The `simple_calculator.alp` demonstrates the correct pattern:

```json
// 1. Import the logic module
{"kind":"@import","path":"../calculator.alp"}

// 2. Define UI-specific shapes for input/output
{"kind":"@shape","id":"UICalcInput","fields":{"expression":"str"}}
{"kind":"@shape","id":"UICalcResult","fields":{"result":"str","expression":"str"}}

// 3. Create handler that calls imported logic
{"kind":"@fn","id":"ui_calculator_handler","in":"UICalcInput","out":"UICalcResult",
  "@op":[["calc_eval",{"expr":"$in.expression"},{"as":"result"}]],
  "@expect":{"result":"$result.value","expression":"$in.expression"}}

// 4. Build UI and connect handler
{"kind":"@fn","id":"create_calculator_ui",
  "@op":[
    ["ui_create",{"title":"🧮 ALP Calculator"}],
    ["ui_add_input",{"name":"expression","type":"textbox"}],
    ["ui_add_output",{"name":"result","type":"json"}],
    ["ui_set_handler",{"function":"ui_calculator_handler","inputs":["expression"],"outputs":["result"]}],
    ["ui_launch",{"port":7860}],
    ["ui_wait",{}]
  ]}
```

### Anti-Pattern to Avoid

```json
// BAD: UI file contains business logic directly
{"kind":"@fn","id":"calculator",
  "@op":[["calc_eval",{"expr":"$in.expression"}]]  // ❌ Logic in UI
}
```

Always import and delegate to logic modules instead!

## 🔧 Architecture

The UI system uses a declarative approach where:
1. **Configuration Phase**: Build UI structure with operations
2. **Handler Registration**: Connect ALP functions to UI events  
3. **Runtime Phase**: Gradio server executes ALP functions on user interaction
4. **Result Processing**: Automatic JSON formatting and error handling