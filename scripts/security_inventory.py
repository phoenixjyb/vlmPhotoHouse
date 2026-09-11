"""Source-only access inventory guard. Never imports the application or settings.

The reviewed topology is pinned: changes to constructors, includes or middleware
require review, including registration syntax this scanner cannot resolve.
This checks inventory coverage, NOT authorization enforcement.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "docs/security/route_capabilities.json"
HTTP = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
META_REGISTRATION = {"middleware", "add_middleware", "exception_handler", "add_exception_handler", "on_event"}
REGISTRATION = HTTP | {"route", "api_route", "websocket", "websocket_route",
                       "add_route", "add_api_route", "add_websocket_route",
                       "add_api_websocket_route", "mount", "include_router"}


# These two existing harness expressions execute guarded, selected legacy AST in
# synthetic namespaces. Pin exact expressions and topology; no file-wide bypass.
REVIEWED_EXEC = {
    ("tests/security/harness.py", "exec(compile(module, relative, 'exec', dont_inherit=True), namespace)"),
    ("tests/security/harness.py", "exec(compile(ast.Module(body=[constructor], type_ignores=[]), 'synthetic-app', 'exec'), namespace)"),
}


def source_files(root: Path) -> list[Path]:
    # Include untracked source too; do not traverse ignored data/env directories.
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z", "--", "*.py"],
        cwd=root, check=True, capture_output=True,
    )
    return [root / p for p in sorted(set(result.stdout.decode().split("\0"))) if p]


def scan(files: list[Path], root: Path) -> dict:
    routes, topology = [], []
    for path in files:
        source = path.relative_to(root).as_posix()
        code = path.read_text(encoding="utf-8-sig")
        # Some unrelated legacy CLI scripts are syntactically invalid. Scan every
        # source for HTTP declarations/imports, then parse every candidate strictly.
        candidate = re.search(r"fastapi|starlette|FastAPI|APIRouter|include_router|add_api_route|@\w+\.(?:get|post|put|patch|delete|head|options|route|websocket)\s*\(", code)
        actions = "|".join(sorted(REGISTRATION | META_REGISTRATION))
        reflective = re.search(r"getattr\s*\([^,]+,\s*['\"](?:" + actions + r")[ '\"]", code)
        reference = re.search(r"\b\w+\s*=\s*\w+\.(?:" + actions + r")\s*(?:$|#)", code, re.MULTILINE)
        if not (candidate or reflective or reference):
            continue
        tree = ast.parse(code, filename=source)
        decorators = {d for f in ast.walk(tree)
                      if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))
                      for d in f.decorator_list}
        factories = {"FastAPI", "APIRouter"}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "fastapi":
                factories.update(a.asname or a.name for a in node.names
                                 if a.name in {"FastAPI", "APIRouter"})
        owners = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.Assign, ast.AnnAssign)) and isinstance(node.value, ast.Call):
                call = node.value
                name = ast.unparse(call.func)
                if name not in factories and name.rsplit(".", 1)[-1] not in {"FastAPI", "APIRouter"}:
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                    raise ValueError(f"Review unsupported factory assignment: {source}:{node.lineno}")
                owner = targets[0].id
                owners[owner] = name
                topology.append({"source": source, "expression": ast.unparse(node)})
                if name.endswith("FastAPI") or name in {
                    a.asname for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                    and n.module == "fastapi" for a in n.names if a.name == "FastAPI"
                }:
                    config = {k.arg: ast.literal_eval(k.value) for k in call.keywords
                              if k.arg in {"openapi_url", "docs_url", "redoc_url", "swagger_ui_oauth2_redirect_url"}}
                    if config.get("openapi_url", "/openapi.json"):
                        automatic = [(config.get("openapi_url", "/openapi.json"), "openapi")]
                        if config.get("docs_url", "/docs"):
                            automatic += [(config.get("docs_url", "/docs"), "swagger_ui"),
                                          (config.get("swagger_ui_oauth2_redirect_url", "/docs/oauth2-redirect"), "swagger_redirect")]
                        automatic += [(config.get("redoc_url", "/redoc"), "redoc")]
                        for url, handler in automatic:
                            if url:
                                for method in ("GET", "HEAD"):
                                    routes.append(dict(source=source, owner=owner, method=method,
                                                       path=url, handler=f"<framework:{handler}>"))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(ast.unparse(base) in factories
                    or ast.unparse(base).rsplit('.', 1)[-1] in {'FastAPI', 'APIRouter'} for base in node.bases):
                raise ValueError(f"Review custom HTTP factory: {source}:{node.lineno}")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in {'exec', 'eval'}:
                    expression = ast.unparse(node)
                    if (source, expression) not in REVIEWED_EXEC:
                        raise ValueError(f"Review executable registration code: {source}:{node.lineno}")
                    topology.append({'source': source, 'expression': expression})
                if node.func.id == 'getattr' and len(node.args) >= 2:
                    attribute = node.args[1].value if isinstance(node.args[1], ast.Constant) else None
                    known_owner = ast.unparse(node.args[0]) in owners
                    reflective_method = (attribute in REGISTRATION | META_REGISTRATION
                                         if isinstance(attribute, str) else known_owner)
                    if reflective_method:
                        raise ValueError(f"Review reflective registration: {source}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in REGISTRATION | META_REGISTRATION:
                parent = parents.get(node)
                called = isinstance(parent, ast.Call) and parent.func is node
                known_owner = ast.unparse(node.value) in owners
                assigned = isinstance(parent, (ast.Assign, ast.AnnAssign)) and parent.value is node
                if not called and (known_owner or assigned):
                    raise ValueError(f"Review registration method reference: {source}:{node.lineno}")
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            receiver, action = ast.unparse(node.func.value), node.func.attr
            if receiver not in owners:
                # New registrations on imported/aliased routers must not vanish.
                if action in REGISTRATION - HTTP:
                    raise ValueError(f"Review unresolved registration: {source}:{node.lineno}")
                continue
            if action in HTTP:
                if node not in decorators:
                    raise ValueError(f"Review non-decorator HTTP registration: {source}:{node.lineno}")
            if action not in HTTP:
                topology.append({"source": source, "expression": ast.unparse(node)})
                if action in REGISTRATION - {"include_router"}:
                    raise ValueError(f"Review unsupported registration: {source}:{node.lineno}")
                if action == "add_middleware" and node.args and ast.unparse(node.args[0]) == "CORSMiddleware":
                    routes.append(dict(source=source, owner=receiver, method="OPTIONS", path="/*",
                                       handler="<middleware:cors-preflight>"))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                    continue
                action = decorator.func.attr
                if action not in HTTP:
                    continue
                receiver = ast.unparse(decorator.func.value)
                if receiver not in owners:
                    raise ValueError(f"Review unresolved HTTP decorator: {source}:{node.lineno}")
                path_node = (decorator.args[0] if decorator.args else
                             next((k.value for k in decorator.keywords if k.arg == "path"), None))
                if path_node is None:
                    raise ValueError(f"Missing route path: {source}:{node.lineno}")
                url = ast.literal_eval(path_node)
                if not isinstance(url, str) or not url.startswith("/"):
                    raise ValueError(f"Nonliteral route: {source}:{node.lineno}")
                routes.append(dict(source=source, owner=receiver, method=action.upper(),
                                   path=url, handler=node.name))
    key = lambda r: (r["source"], r["owner"], r["path"], r["method"], r["handler"])
    return {"routes": sorted(routes, key=key),
            "topology": sorted(topology, key=lambda t: (t["source"], t["expression"]))}


def validate(discovered: dict, inventory: dict) -> list[str]:
    errors = []
    fields = ("source", "owner", "method", "path", "handler")
    identity = lambda r: tuple(r[k] for k in fields)
    actual = [identity(r) for r in discovered["routes"]]
    reviewed = [identity(r) for r in inventory["routes"]]
    registered = [(r["surface"], r["method"], r["path"]) for r in inventory["routes"]]
    if (len(reviewed) != len(set(reviewed)) or len(actual) != len(set(actual))
            or len(registered) != len(set(registered))):
        errors.append("Duplicate route identity; review registration order/shadowing")
    for route in sorted(set(actual) - set(reviewed)):
        errors.append(f"UNINVENTORIED: {route}")
    for route in sorted(set(reviewed) - set(actual)):
        errors.append(f"STALE: {route}")
    if discovered["topology"] != inventory["topology"]:
        errors.append("TOPOLOGY CHANGED: review app defaults, prefixes, includes, middleware and methods")
    for route in inventory["routes"]:
        for field in ("surface", "scope", "current_control", "gap"):
            if not route.get(field):
                errors.append(f"Missing {field}: {identity(route)}")
        caps = route.get("capabilities", [])
        if not caps or any(c not in inventory["capabilities"] for c in caps):
            errors.append(f"Unreviewed capability: {identity(route)}")
        if "public.ui" in caps and route["source"] != "backend/app/routers/ui.py":
            errors.append(f"Public exception outside reviewed UI shell: {identity(route)}")
        if 'home.feed.read' in caps and (route['source'] != 'backend/app/home_feed.py' or route['surface'] != 'home-feed'):
            errors.append(f"Home feed exception outside reviewed surface: {identity(route)}")
        if 'home.catalog.read' in caps and (route['source'] != 'backend/app/home_catalog.py' or route['surface'] != 'home-catalog'):
            errors.append(f"Home catalog exception outside reviewed surface: {identity(route)}")
        if 'home.discovery.read' in caps and (route['source'] != 'backend/app/home_discovery.py' or route['surface'] != 'home-discovery'):
            errors.append(f"Home discovery exception outside reviewed surface: {identity(route)}")
    return errors


def main() -> int:
    try:
        inventory = json.loads(INVENTORY.read_text())
        discovered = scan(source_files(ROOT), ROOT)
        errors = validate(discovered, inventory)
    except (ValueError, KeyError, SyntaxError) as exc:
        print(f"INVENTORY FAIL: {exc}")
        return 1
    for error in errors:
        print(error)
    if errors:
        return 1
    print(f"Inventory complete: {len(discovered['routes'])} method/path entries. "
          "Active app closed by default; retired and standalone gaps remain inventoried.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
