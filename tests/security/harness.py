"""Audit retired, unguarded source handlers against in-memory test doubles.

No app.main/config/dependencies imports, lifespan, ORM, model or outbound HTTP.
FastAPI routing and Starlette file/Range handling are real, via in-process ASGI.
Identity labels describe future scenarios; they are NOT verified credentials.
"""
from __future__ import annotations

import ast
from contextlib import ExitStack
import importlib.util
import json
import mimetypes
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from types import ModuleType, SimpleNamespace
from typing import Any, Optional
from unittest.mock import MagicMock, patch
import uuid

from fastapi import Body, Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from security_inventory import scan, source_files, validate, INVENTORY


def load_functions(relative: str, names: list[str], namespace: dict) -> None:
    """Preserve complete signatures, decorators and bodies; never import module."""
    tree = ast.parse((ROOT / relative).read_text())
    selected = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                and n.name in names]
    if {n.name for n in selected} != set(names):
        raise AssertionError(f"Source functions changed: {relative}: {names}")
    for function in selected:
        for node in ast.walk(function):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                allowed = (isinstance(node, ast.ImportFrom) and
                           ((node.module == "db" and node.level == 1) or node.module == "PIL"))
                allowed |= isinstance(node, ast.Import) and all(a.name == "os" for a in node.names)
                if not allowed:
                    raise AssertionError(f"Review new handler import: {ast.unparse(node)}")
    module = ast.Module(body=selected, type_ignores=[])
    exec(compile(module, relative, "exec", dont_inherit=True), namespace)


class SyntheticSession:
    def __init__(self):
        self.rows = {}
        self.effects = []

    def get(self, model, object_id):
        self.effects.append("db.get")
        return next((r for r in self.rows.get(model, []) if r.id == object_id), None)

    def query(self, model):
        self.effects.append("db.query")
        query = MagicMock(name="synthetic_query")
        for method in ("filter", "order_by", "offset", "limit"):
            getattr(query, method).return_value = query
        # Deliberately not an ORM/query evaluator. These rows prove handler output
        # and aggregate exposure; library partitioning needs real synthetic SQL later.
        query.all.return_value = self.rows.get(model, [])
        query.count.return_value = len(self.rows.get(model, []))
        return query

    def add(self, row):
        self.effects.append("db.add")

    def commit(self):
        self.effects.append("db.commit")


class Harness:
    def __enter__(self):
        self.stack = ExitStack()
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="photohouse-security-"))).resolve()
        self.db = SyntheticSession()
        # Block any accidental network listener/client or process launch. TestClient
        # uses ASGITransport; no socket listener is needed.
        for target in ("socket.socket.connect", "socket.socket.connect_ex", "socket.socket.bind",
                       "socket.create_connection", "subprocess.Popen", "os.system"):
            self.stack.enter_context(patch(target, side_effect=AssertionError("External I/O forbidden")))
        namespace = dict(FastAPI=FastAPI, Depends=Depends, Body=Body, Query=Query,
                         HTTPException=HTTPException, Path=Path, mimetypes=mimetypes,
                         JSONResponse=JSONResponse, Session=SyntheticSession,
                         Optional=Optional, Any=Any, os=os, time=time, uuid=uuid, re=re)
        self.ns = namespace
        # Evaluate only the original FastAPI constructor, not any module startup.
        tree = ast.parse((ROOT / "backend/app/legacy_main.py").read_text())
        constructor = next(n for n in tree.body if isinstance(n, ast.Assign)
                           and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets))
        exec(compile(ast.Module(body=[constructor], type_ignores=[]), "synthetic-app", "exec"), namespace)
        namespace["router"] = namespace["app"]
        spec = importlib.util.spec_from_file_location("synthetic_schemas", ROOT / "backend/app/schemas.py")
        schemas = importlib.util.module_from_spec(spec)
        self.stack.enter_context(patch.dict(sys.modules, {"synthetic_schemas": schemas}))
        spec.loader.exec_module(schemas)  # Pure Pydantic schema declarations only.
        namespace["schemas"] = schemas
        namespace["get_db"] = lambda: self.db
        namespace["settings"] = SimpleNamespace(derived_path=str(self.root))
        namespace["DERIVED_PATH"] = self.root

        def file_response(*args, **kwargs):
            self.db.effects.append("file.response")
            if not Path(args[0]).resolve().is_relative_to(self.root):
                raise AssertionError("Only synthetic files may be served")
            return FileResponse(*args, **kwargs)

        namespace["FileResponse"] = file_response
        models = ModuleType("_photohouse_synthetic.db")
        for name in ("Asset", "FaceDetection", "Caption", "Album", "Task"):
            model = type(name, (), {k: MagicMock(name=k) for k in
                         ("id", "status", "path", "asset_id", "created_at", "updated_at")})
            namespace[name] = model
            setattr(models, name, model)
        namespace["__package__"] = "_photohouse_synthetic"
        self.stack.enter_context(patch.dict(sys.modules, {"_photohouse_synthetic.db": models}))
        for asset_id, intended_library in ((101, "family-a"), (202, "family-b")):
            path = self.root / f"synthetic-{asset_id}.mp4"
            path.write_bytes(b"synthetic-video-bytes-0123456789")
            row = SimpleNamespace(id=asset_id, path=str(path), mime="video/mp4", status="active",
                                  hash_sha256="synthetic-only", width=1, height=1,
                                  intended_library=intended_library)
            self.db.rows.setdefault(namespace["Asset"], []).append(row)
            for suffix in (f"thumbnails/256/{asset_id}.jpg", f"faces/256/{asset_id}.jpg"):
                derivative = self.root / suffix
                derivative.parent.mkdir(parents=True, exist_ok=True)
                derivative.write_bytes(b"synthetic-derived-bytes")
        self.db.rows[namespace["FaceDetection"]] = [SimpleNamespace(id=202, asset_id=202)]
        self.db.rows[namespace["Caption"]] = [SimpleNamespace(id=303, asset_id=202,
            text="Synthetic family-b caption", model="synthetic", user_edited=False, created_at=None)]
        asset = self.db.rows[namespace["Asset"]][1]
        asset.taken_at = None
        self.db.rows[namespace["Album"]] = [SimpleNamespace(id=404, status="draft", title="Synthetic album",
            title_zh=None, description=None, theme="custom", cover_asset_id=202, source_kind=None,
            source_ref=None, created_at=None, updated_at=None,
            items=[SimpleNamespace(id=1, position=0, asset=asset)])]
        load_functions("backend/app/legacy_main.py", ["_visible_assets_filter", "get_asset_media",
            "get_asset_thumbnail", "get_asset_detail", "list_assets", "search", "list_captions",
            "trigger_ingest", "delete_single_asset"], namespace)
        load_functions("backend/app/routers/people.py", ["get_face_crop"], namespace)
        load_functions("backend/app/routers/albums.py", ["_serialize_album", "get_album_draft", "list_album_drafts"], namespace)

        def ingest_paths(db_s, roots):
            self.db.effects.append("ingest.invoke")
            return {"synthetic": True, "roots_count": len(roots)}

        namespace["ingest_mod"] = SimpleNamespace(ingest_paths=ingest_paths)
        namespace["asset_service"] = SimpleNamespace(remove_asset_files=lambda *a: self.db.effects.append("files.delete"))
        namespace.update(_VOICE_PENDING_BY_CLIENT={}, _VOICE_PENDING_LOCK=threading.Lock(),
                         _VOICE_CONFIRM_TTL_SEC=180)
        load_functions("backend/app/routers/voice.py", ["_require_enabled", "_normalize_client_id",
            "_cleanup_expired_pending_actions", "_put_pending_action", "_pop_pending_action",
            "voice_chat_delete"], namespace)
        namespace["get_settings"] = lambda: SimpleNamespace(voice_enabled=True, voice_provider="external",
            voice_external_base_url="https://provider.invalid", voice_api_key=None, voice_timeout_sec=1)

        class ProviderDouble:
            def __init__(inner, **kwargs): pass
            async def __aenter__(inner): return inner
            async def __aexit__(inner, *args): pass
            async def post(inner, url, **kwargs):
                self.db.effects.append("provider.post")
                return SimpleNamespace(status_code=200, json=lambda: {"success": True})

        namespace["httpx"] = SimpleNamespace(AsyncClient=ProviderDouble, HTTPError=RuntimeError)
        self.client = self.stack.enter_context(TestClient(namespace["app"]))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


READ_PROBES = [
    ("legacy-detail", "GET", "/assets/detail/202", {}),
    ("original", "GET", "/assets/202/media", {}),
    ("download", "GET", "/assets/202/media?download=true", {}),
    ("video-range", "GET", "/assets/202/media", {"headers": {"Range": "bytes=0-8"}}),
    ("thumbnail", "GET", "/assets/202/thumbnail", {}),
    ("face-crop", "GET", "/faces/202/crop", {}),
    ("captions", "GET", "/assets/202/captions", {}),
    ("search-counts", "GET", "/search", {}),
    ("timeline-counts", "GET", "/assets", {}),
    ("album-cover-items", "GET", "/albums/drafts/404", {}),
    ("album-counts", "GET", "/albums/drafts", {}),
]
IDENTITIES = ("anonymous", "registered-unapproved", "revoked", "wrong-library",
              "expired-membership", "malformed-token", "expired-token")


def run_probes() -> list[dict]:
    findings = []
    with Harness() as h:
        cases = [(identity, *probe) for identity in IDENTITIES for probe in READ_PROBES]
        cases += [(identity, label, method, path, kwargs) for identity in ("anonymous", "viewer")
                  for label, method, path, kwargs in [
                      ("operator-ingest", "POST", "/ingest/scan", {"json": {"roots": ["synthetic-only"]}}),
                      ("destructive-asset", "POST", "/assets/202/delete", {"json": True}),
                      ("foreign-conversation-delete", "POST", "/voice/chat/delete",
                       {"json": {"conversation_id": "synthetic-other-account-conversation"}})]]
        for identity, label, method, path, kwargs in cases:
            h.db.rows[h.ns["Asset"]][1].status = "active"
            h.db.effects.clear()
            kwargs = dict(kwargs)
            headers = dict(kwargs.pop("headers", {}))
            if identity != "anonymous":
                headers["Authorization"] = f"Bearer synthetic-{identity}-not-a-real-token"
            response = h.client.request(method, path, headers=headers, **kwargs)
            denied = response.status_code in {401, 403, 404}
            # Even a denial is unsafe if a protected file/provider/write was reached.
            effects = list(h.db.effects)
            sensitive = set(effects) & {"file.response", "ingest.invoke", "files.delete", "db.commit", "provider.post"}
            findings.append(dict(case=f"{identity}/{label}", expected="deny before protected effects",
                                 status=response.status_code, effects=effects,
                                 secure=denied and not sensitive))
        h.ns["_put_pending_action"]("synthetic-shared-client", "person.rename", {"person_id": 202})
        accepted = h.ns["_pop_pending_action"]("synthetic-shared-client", None)
        findings.append(dict(case="voice/omitted-confirmation-token", expected="reject absent token",
                             status="accepted" if accepted else "rejected", effects=[], secure=accepted is None))
    return findings


def main() -> int:
    errors = validate(scan(source_files(ROOT), ROOT), json.loads(INVENTORY.read_text()))
    if errors:
        print("Inventory changed; review before executing selected handlers:", errors)
        return 2
    findings = run_probes()
    for finding in findings:
        print(json.dumps(finding))
    failures = sum(not f["secure"] for f in findings)
    print(f"RETIRED HANDLER DENIAL GATE: {failures}/{len(findings)} FAIL (historical failure ledger; active entry point tested separately)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
