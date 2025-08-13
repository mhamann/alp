"""Gradio UI integration for ALP."""
import os
import json
import threading
import time
from typing import Dict, Any, Optional
from pathlib import Path

# Store UI state globally (for this session)
_ui_state = {
    "interface": None,
    "components": {},
    "handlers": {},
    "running": False
}

def register(reg):
    """Register Gradio UI operations."""
    
    def ui_wait(a, ctx):
        """Wait for UI to be closed or for a specified duration.
        
        Args:
            timeout: Optional timeout in seconds (default: wait forever)
        """
        timeout = a.get("timeout")
        
        if not _ui_state.get("running"):
            return {"waited": False, "reason": "No UI running"}
        
        try:
            if timeout:
                time.sleep(timeout)
                return {"waited": True, "timeout": timeout}
            else:
                # Wait forever (until Ctrl+C)
                while _ui_state.get("running"):
                    time.sleep(1)
                return {"waited": True, "closed": True}
        except KeyboardInterrupt:
            return {"waited": True, "interrupted": True}
    
    def ui_create(a, ctx):
        """Create a Gradio interface configuration.
        
        Args:
            title: UI title
            description: UI description
            theme: Gradio theme (default, soft, glass)
        """
        try:
            import gradio as gr
        except ImportError:
            return {"error": "Gradio not installed. Run: pip install gradio"}
        
        title = a.get("title", "ALP Interface")
        description = a.get("description", "")
        theme = a.get("theme", "default")
        
        # Create interface configuration
        config = {
            "title": title,
            "description": description,
            "theme": theme,
            "components": [],
            "handlers": []
        }
        
        _ui_state["config"] = config
        return {"created": True, "config": config}
    
    def ui_add_input(a, ctx):
        """Add an input component to the UI.
        
        Args:
            name: Component identifier
            type: Component type (textbox, number, slider, dropdown)
            label: Display label
            default: Default value
            options: Options for dropdown
            min/max: For number/slider
        """
        if "config" not in _ui_state:
            return {"error": "UI not created. Call ui_create first"}
        
        component = {
            "name": a.get("name"),
            "type": a.get("type", "textbox"),
            "label": a.get("label", ""),
            "default": a.get("default"),
            "options": a.get("options"),
            "min": a.get("min"),
            "max": a.get("max"),
            "step": a.get("step"),
            "lines": a.get("lines"),
            "placeholder": a.get("placeholder"),
            "is_input": True
        }
        
        _ui_state["config"]["components"].append(component)
        return {"added": True, "component": component}
    
    def ui_add_output(a, ctx):
        """Add an output component to the UI.
        
        Args:
            name: Component identifier
            type: Component type (textbox, json, markdown, dataframe)
            label: Display label
        """
        if "config" not in _ui_state:
            return {"error": "UI not created. Call ui_create first"}
        
        component = {
            "name": a.get("name"),
            "type": a.get("type", "textbox"),
            "label": a.get("label", ""),
            "is_input": False
        }
        
        _ui_state["config"]["components"].append(component)
        return {"added": True, "component": component}
    
    def ui_set_handler(a, ctx):
        """Set the handler function for the UI.
        
        Args:
            function: ALP function ID to call
            inputs: List of input component names
            outputs: List of output component names
        """
        if "config" not in _ui_state:
            return {"error": "UI not created. Call ui_create first"}
        
        handler = {
            "function": a.get("function"),
            "inputs": a.get("inputs", []),
            "outputs": a.get("outputs", [])
        }
        
        _ui_state["config"]["handlers"].append(handler)
        # Store the full context so we can execute functions
        _ui_state["handlers"][a.get("function")] = {
            "ctx": {
                "fns": ctx.get("fns", {}),
                "shapes": ctx.get("shapes", {}),
                "tools": ctx.get("tools", {}),
                "env": ctx.get("env", {})
            },
            "handler": handler
        }
        
        return {"set": True, "handler": handler}
    
    def ui_launch(a, ctx):
        """Launch the Gradio interface.
        
        Args:
            port: Port to run on (default 7860)
            share: Create public link (default False)
            debug: Debug mode (default False)
        """
        if "config" not in _ui_state:
            return {"error": "UI not created. Call ui_create first"}
        
        try:
            import gradio as gr
        except ImportError:
            return {"error": "Gradio not installed. Run: pip install gradio"}
        
        config = _ui_state["config"]
        port = a.get("port", 7860)
        share = a.get("share", False)
        debug = a.get("debug", False)
        
        # Build Gradio components
        inputs = []
        outputs = []
        component_map = {}
        
        for comp in config["components"]:
            gr_comp = _create_gradio_component(comp)
            component_map[comp["name"]] = gr_comp
            
            if comp.get("is_input", False):
                inputs.append(gr_comp)
            else:
                outputs.append(gr_comp)
        
        # Create handler function
        def process(*args):
            # Support multiple handlers for orchestrator pattern
            handlers = config.get("handlers", [])
            if not handlers:
                return json.dumps({"error": "No handler configured"})
            
            handler = handlers[0]  # Use first handler
            
            # Get the function to call
            fn_id = handler["function"]
            handler_ctx = _ui_state["handlers"].get(fn_id, {})
            ctx = handler_ctx.get("ctx", {})
            
            # Convert inputs to dict based on handler input names
            input_values = {}
            for i, input_name in enumerate(handler["inputs"]):
                if i < len(args):
                    input_values[input_name] = args[i]
            
            # Try to execute the ALP function if it exists in context
            fns = ctx.get("fns", {})
            if fn_id in fns:
                try:
                    # Import the VM module to execute the ALP function
                    from runtime.vm import exec_fn, OPS, register_op
                    
                    # Ensure operations are registered (only happens once)
                    if len(OPS) == 0:
                        from runtime.stdlib import register_all
                        register_all(OPS, register_op)
                    
                    # Prepare inbound data based on function's input declaration
                    fn_def = fns[fn_id]
                    declared_inputs = fn_def.get("in") or {}
                    
                    # Determine how to pass the input based on function signature
                    if isinstance(declared_inputs, str):
                        # Function expects a single typed input (e.g., "in": "CalcInput")
                        inbound_data = input_values
                    elif isinstance(declared_inputs, dict):
                        if len(declared_inputs) == 0:
                            inbound_data = None
                        elif len(declared_inputs) == 1:
                            # Single named input
                            if len(input_values) == 1:
                                input_name = next(iter(declared_inputs.keys()))
                                if input_name in input_values:
                                    inbound_data = input_values
                                else:
                                    ui_value = next(iter(input_values.values()))
                                    inbound_data = {input_name: ui_value}
                            else:
                                inbound_data = input_values
                        else:
                            inbound_data = input_values
                    else:
                        inbound_data = input_values
                    
                    # Execute the function with the properly formatted input
                    result, _ = exec_fn(
                        fn_def, 
                        ctx.get("shapes", {}), 
                        fns, 
                        inbound=inbound_data,
                        tools=ctx.get("tools", {})
                    )
                    
                    # Format output
                    output_names = handler.get("outputs", [])
                    
                    # Always return valid JSON for first output
                    if result is None:
                        formatted_result = json.dumps({"result": "null"})
                    elif isinstance(result, dict):
                        formatted_result = json.dumps(result, indent=2)
                    elif isinstance(result, (int, float, bool)):
                        formatted_result = json.dumps({"result": result})
                    elif isinstance(result, str):
                        formatted_result = json.dumps({"result": result})
                    else:
                        formatted_result = json.dumps({"result": str(result)})
                    
                    # Handle multiple outputs
                    if len(output_names) <= 1:
                        return formatted_result
                    else:
                        return [formatted_result] + [""] * (len(output_names) - 1)
                        
                except Exception as e:
                    # Return error as valid JSON
                    error_result = json.dumps({
                        "error": str(e),
                        "function": fn_id,
                        "inputs": input_values
                    }, indent=2)
                    
                    # Return correct number of outputs for error case too
                    output_names = handler.get("outputs", [])
                    if len(output_names) <= 1:
                        return error_result
                    else:
                        return [error_result] + ["Error occurred"] * (len(output_names) - 1)
            else:
                # Fallback - show available functions
                fallback_result = json.dumps({
                    "error": f"Function '{fn_id}' not found",
                    "inputs": input_values,
                    "available_functions": list(fns.keys())
                }, indent=2)
                
                # Return correct number of outputs
                output_names = handler.get("outputs", [])
                if len(output_names) <= 1:
                    return fallback_result
                else:
                    return [fallback_result] + ["Function not found"] * (len(output_names) - 1)
        
        # Create Gradio interface
        interface = gr.Interface(
            fn=process,
            inputs=inputs,
            outputs=outputs,
            title=config["title"],
            description=config["description"],
            theme=config["theme"]
        )
        
        # Store interface
        _ui_state["interface"] = interface
        _ui_state["running"] = True
        
        # Launch in a non-daemon thread so it keeps running
        def launch_thread():
            interface.launch(
                server_port=port,
                share=share,
                debug=debug,
                prevent_thread_lock=False,
                inbrowser=False
            )
        
        # Use non-daemon thread so the server stays alive
        thread = threading.Thread(target=launch_thread, daemon=False)
        thread.start()
        
        # Give it a moment to start
        time.sleep(3)
        
        return {
            "launched": True,
            "url": f"http://localhost:{port}",
            "share": share
        }
    
    def _create_gradio_component(comp):
        """Create a Gradio component from config."""
        import gradio as gr
        
        comp_type = comp["type"]
        label = comp.get("label", "")
        
        if comp_type == "textbox":
            return gr.Textbox(
                label=label,
                value=comp.get("default", ""),
                lines=comp.get("lines", 1),
                placeholder=comp.get("placeholder", "")
            )
        elif comp_type == "number":
            return gr.Number(
                label=label,
                value=comp.get("default", 0),
                minimum=comp.get("min"),
                maximum=comp.get("max")
            )
        elif comp_type == "slider":
            return gr.Slider(
                label=label,
                value=comp.get("default", 0),
                minimum=comp.get("min", 0),
                maximum=comp.get("max", 100),
                step=comp.get("step", 1)
            )
        elif comp_type == "dropdown":
            return gr.Dropdown(
                label=label,
                choices=comp.get("options", []),
                value=comp.get("default")
            )
        elif comp_type == "json":
            return gr.JSON(label=label)
        elif comp_type == "markdown":
            return gr.Markdown(label=label)
        else:
            return gr.Textbox(label=label)
    
    # Register all UI operations
    reg("ui_create", ui_create)
    reg("ui_add_input", ui_add_input)
    reg("ui_add_output", ui_add_output)
    reg("ui_set_handler", ui_set_handler)
    reg("ui_launch", ui_launch)
    reg("ui_wait", ui_wait)