import ast
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_native_optimizer_execution_is_explicitly_marked():
    marked = []
    for path in (ROOT / "tests/integration").glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
                continue
            runs_optimizer = any(isinstance(call, ast.Call) and (
                isinstance(call.func, ast.Attribute) and call.func.attr == "optimize_ems"
                or isinstance(call.func, ast.Attribute) and call.func.attr == "post"
                and any(isinstance(arg, ast.Constant) and arg.value == "/v1/optimize" for arg in call.args)
            ) for call in ast.walk(node))
            if runs_optimizer:
                assert any(ast.unparse(d) == "pytest.mark.genetic_execution" for d in node.decorator_list)
                marked.append(node.name)
    assert len(marked) == 3


def test_preparation_push_and_pr_ci_explicitly_exclude_optimizer_execution():
    workflow = yaml.load((ROOT / ".github/workflows/test.yaml").read_text(), Loader=yaml.BaseLoader)
    for name in ("unit", "eos-integration"):
        selection = workflow["jobs"][name]["env"]["PYTEST_ADDOPTS"]
        assert "github.head_ref == 'release/issue-12-genetic-evidence'" in selection
        assert "github.ref_name == 'release/issue-12-genetic-evidence'" in selection
        assert "not genetic_execution" in selection
    assert any("-e PYTEST_ADDOPTS" in step.get("run", "")
               for step in workflow["jobs"]["eos-integration"]["steps"])
