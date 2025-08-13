"""Extra modules for ALP that are not part of core stdlib.

These modules provide additional functionality but may have external dependencies
or are considered experimental/optional.
"""

# Import available extra modules
try:
    from . import ui_gradio as ui
    HAS_UI = True
except ImportError:
    HAS_UI = False
    ui = None


def register_all(ops_registry: dict, register_op):
    """Register all available extra modules."""
    if HAS_UI and ui and hasattr(ui, "register"):
        ui.register(register_op)