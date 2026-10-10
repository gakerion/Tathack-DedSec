"""Split new Python files at real function/method boundaries, without running code."""
import ast


def python_stages(filename, content):
    if not filename.lower().endswith(".py"):
        return []
    try:
        tree = ast.parse(content)
    except (SyntaxError, ValueError):
        return []
    boundaries = {}
    first_definition = None
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            start = min([node.lineno] + [d.lineno for d in node.decorator_list])
            first_definition = start if first_definition is None else first_definition
            if isinstance(node, ast.ClassDef):
                for method in node.body:
                    if isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        boundaries[method.end_lineno] = f"Add {node.name}.{method.name}()"
                boundaries.setdefault(node.end_lineno, f"Add class {node.name}")
            else:
                boundaries[node.end_lineno] = f"Add {node.name}()"
    if not boundaries:
        return []
    lines = content.splitlines(keepends=True)
    stages = [("Create file and setup", "".join(lines[:first_definition - 1]))]
    for end, title in sorted(boundaries.items()):
        prefix = "".join(lines[:end])
        try:
            ast.parse(prefix)
        except SyntaxError:
            continue
        stages.append((title, prefix))
    if stages[-1][1] != content:
        stages.append(("Finish file and entry point", content))
    return stages
