"""Conditional control flow operations for ALP."""

def register(reg):
    def if_else(a, ctx):
        """Conditional execution based on condition evaluation.
        
        Args:
            condition: Boolean value or expression to evaluate
            then: Value or operation to execute if true
            else: Value or operation to execute if false (optional)
            
        Returns:
            Result of the executed branch
        """
        condition = a.get("condition")
        then_branch = a.get("then")
        else_branch = a.get("else")
        
        # Evaluate condition
        if isinstance(condition, dict):
            # Handle comparison operations
            if "eq" in condition:
                left, right = condition["eq"]
                cond_result = left == right
            elif "ne" in condition:
                left, right = condition["ne"]
                cond_result = left != right
            elif "gt" in condition:
                left, right = condition["gt"]
                cond_result = left > right
            elif "gte" in condition:
                left, right = condition["gte"]
                cond_result = left >= right
            elif "lt" in condition:
                left, right = condition["lt"]
                cond_result = left < right
            elif "lte" in condition:
                left, right = condition["lte"]
                cond_result = left <= right
            elif "and" in condition:
                cond_result = all(condition["and"])
            elif "or" in condition:
                cond_result = any(condition["or"])
            elif "not" in condition:
                cond_result = not condition["not"]
            else:
                cond_result = bool(condition)
        else:
            # Direct boolean evaluation
            cond_result = bool(condition)
        
        # Execute appropriate branch
        if cond_result:
            result = then_branch
        else:
            result = else_branch if else_branch is not None else None
            
        # If branch is an operation array, execute it
        if isinstance(result, list) and len(result) >= 2:
            # This is an operation to execute
            op_name = result[0]
            op_args = result[1] if len(result) > 1 else {}
            ops = ctx.get('ops', {})
            if op_name in ops:
                return ops[op_name](op_args, ctx)
        
        return result
    
    def switch_case(a, ctx):
        """Multi-branch conditional based on value matching.
        
        Args:
            value: Value to match against cases
            cases: Dict of value -> result/operation mappings
            default: Default result if no case matches (optional)
            
        Returns:
            Result of the matched case or default
        """
        value = a.get("value")
        cases = a.get("cases", {})
        default = a.get("default")
        
        # Find matching case
        result = cases.get(str(value), default)
        
        # If result is an operation array, execute it
        if isinstance(result, list) and len(result) >= 2:
            op_name = result[0]
            op_args = result[1] if len(result) > 1 else {}
            ops = ctx.get('ops', {})
            if op_name in ops:
                return ops[op_name](op_args, ctx)
        
        return result
    
    def try_catch(a, ctx):
        """Error handling with try/catch semantics.
        
        Args:
            do: Operation to attempt
            catch: Operation or value to use on error
            finally: Operation to always execute (optional)
            
        Returns:
            Dict with result and error status
        """
        do_op = a.get("do")
        catch_op = a.get("catch")
        finally_op = a.get("finally")
        
        error = None
        result = None
        
        # Try to execute the main operation
        try:
            if isinstance(do_op, list) and len(do_op) >= 2:
                op_name = do_op[0]
                op_args = do_op[1] if len(do_op) > 1 else {}
                ops = ctx.get('ops', {})
                if op_name in ops:
                    result = ops[op_name](op_args, ctx)
                else:
                    raise RuntimeError(f"Unknown operation: {op_name}")
            else:
                result = do_op
        except Exception as e:
            error = str(e)
            # Execute catch branch
            if catch_op is not None:
                if isinstance(catch_op, list) and len(catch_op) >= 2:
                    op_name = catch_op[0]
                    op_args = catch_op[1] if len(catch_op) > 1 else {}
                    # Add error to context for catch handler
                    catch_ctx = dict(ctx)
                    catch_ctx["error"] = error
                    ops = ctx.get('ops', {})
                    if op_name in ops:
                        result = ops[op_name](op_args, catch_ctx)
                else:
                    result = catch_op
        
        # Always execute finally block if present
        finally_result = None
        if finally_op is not None:
            try:
                if isinstance(finally_op, list) and len(finally_op) >= 2:
                    op_name = finally_op[0]
                    op_args = finally_op[1] if len(finally_op) > 1 else {}
                    ops = ctx.get('ops', {})
                    if op_name in ops:
                        finally_result = ops[op_name](op_args, ctx)
                else:
                    finally_result = finally_op
            except:
                pass  # Finally block errors are suppressed
        
        return {
            "result": result,
            "error": error,
            "success": error is None,
            "finally": finally_result
        }
    
    reg("if", if_else)
    reg("switch", switch_case)
    reg("try", try_catch)