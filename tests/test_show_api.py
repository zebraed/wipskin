import ast
import os
import sys
import unittest

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
PARENT = os.path.join(REPO_ROOT, "python")
if PARENT not in sys.path:
    sys.path.insert(0, PARENT)


def _function_param_names(path, function_name):
    with open(path, encoding="utf-8") as handle:
        module = ast.parse(handle.read())
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return [arg.arg for arg in node.args.args]
    return []


class TestShowApi(unittest.TestCase):

    def test_show_window_accepts_dockable(self):
        ui_path = os.path.join(PARENT, "wipskin", "ui", "window.py")
        params = _function_param_names(ui_path, "show_window")
        self.assertIn("dockable", params)

    def test_show_forwards_dockable_keyword(self):
        init_path = os.path.join(PARENT, "wipskin", "__init__.py")
        with open(init_path, encoding="utf-8") as handle:
            source = handle.read()
        self.assertIn("dockable", source)
        tree = ast.parse(source)
        show_node = None
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "showUI":
                show_node = node
                break
        self.assertIsNotNone(show_node)
        show_params = [arg.arg for arg in show_node.args.args]
        self.assertIn("dockable", show_params)

        call_keywords = []
        for node in ast.walk(show_node):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "show_window":
                    call_keywords = [keyword.arg for keyword in node.keywords]
        self.assertIn("dockable", call_keywords)
