"""Generate a tiny dummy LVFace ONNX model for tests.

This is NOT a real face embedding model; it just returns a normalized random linear projection of the input.
Use only for CI / placeholder purposes.

Usage:
  python tools/generate_dummy_lvface_model.py models/lvface.onnx --dim 256

Requires: torch, onnx
"""
from __future__ import annotations
import argparse, os, torch, torch.nn as nn

def build(dim: int):
    # Expect input NCHW (1,3,112,112); flatten then linear -> dim then L2 normalize in inference wrapper.
    return nn.Sequential(
        nn.Flatten(),
        nn.Linear(3*112*112, dim, bias=False),
    )

def export(path: str, dim: int):
    model = build(dim)
    model.eval()
    x = torch.randn(1,3,112,112)
    torch.onnx.export(
        model, x, path,
        input_names=['input'], output_names=['embedding'],
        opset_version=12,
    )
    print(f"Dummy LVFace model written: {path} (dim={dim})")

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('out', help='Output ONNX file path (e.g., models/lvface.onnx)')
    ap.add_argument('--dim', type=int, default=256)
    args = ap.parse_args()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    export(args.out, args.dim)
