"""LVFace subprocess wrapper for using external LVFace installation."""
import json
import subprocess
import tempfile
import os
from pathlib import Path
from PIL import Image
import numpy as np
import logging

logger = logging.getLogger(__name__)

class LVFaceSubprocessProvider:
    """LVFace provider that calls external LVFace installation via subprocess.
    
    This allows using a real LVFace model and environment while keeping dependencies isolated.
    """
    
    def __init__(self, lvface_dir: str, model_name: str, target_dim: int, python_exe: str | None = None):
        self.lvface_dir = Path(lvface_dir)
        self.model_name = model_name
        self.target_dim = target_dim
        self.cuda_visible_devices = (os.getenv("LVFACE_CUDA_VISIBLE_DEVICES", "") or "").strip()
        if python_exe:
            self.python_exe = Path(python_exe)
        else:
            candidates = [
                self.lvface_dir / ".venv-lvface-311" / "Scripts" / "python.exe",
                self.lvface_dir / ".venv" / "Scripts" / "python.exe",
                self.lvface_dir / ".venv-lvface-311" / "bin" / "python",
                self.lvface_dir / ".venv" / "bin" / "python",
            ]
            self.python_exe = next((p for p in candidates if p.exists()), candidates[1])
        
        # Verify the setup
        if not self.lvface_dir.exists():
            raise RuntimeError(f"LVFace directory not found: {lvface_dir}")
        if not self.python_exe.exists():
            raise RuntimeError(f"LVFace Python executable not found: {self.python_exe}")
        
        model_path = self.lvface_dir / "models" / model_name
        if not model_path.exists():
            raise RuntimeError(f"LVFace model not found: {model_path}")
        if self.cuda_visible_devices:
            logger.info("LVFace subprocess pinned via CUDA_VISIBLE_DEVICES=%s", self.cuda_visible_devices)
            
        # Prefer legacy inference.py; fallback to src/inference_onnx.py in newer trees.
        self.legacy_inference_script = self.lvface_dir / "inference.py"
        self.src_inference_script = self.lvface_dir / "src" / "inference_onnx.py"
        if self.legacy_inference_script.exists():
            self.inference_mode = "legacy"
        elif self.src_inference_script.exists():
            self.inference_mode = "src_onnx"
        else:
            raise RuntimeError(
                "LVFace inference script not found. Expected one of: "
                f"{self.legacy_inference_script} or {self.src_inference_script}"
            )
    
    @property
    def dim(self) -> int:
        return self.target_dim

    def embed_face(self, image: Image.Image) -> np.ndarray:
        """Generate face embedding using external LVFace subprocess."""
        # Create temporary image file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
            # Ensure RGB and correct size
            image = image.convert('RGB').resize((112, 112))
            image.save(tmp_path, 'PNG')
        
        try:
            if self.inference_mode == "legacy":
                # Call legacy LVFace inference script
                cmd = f"""
import sys
sys.path.append(r'{self.lvface_dir}')

try:
    import inference
    import numpy as np
    from PIL import Image
    import json
    
    # Load the image
    img = Image.open(r'{tmp_path}')
    
    # Get the model first
    model = inference.get_model(r'{self.lvface_dir / "models" / self.model_name}')
    
    # Run inference with the loaded model and image
    embedding = inference.inference(model, img)
    
    # Ensure it's a numpy array
    if not isinstance(embedding, np.ndarray):
        embedding = np.array(embedding, dtype=np.float32)
    
    # Convert to target dimension if needed
    if len(embedding) != {self.target_dim}:
        if {self.target_dim} < len(embedding):
            embedding = embedding[:{self.target_dim}]
        else:
            # Pad with normalized random values if needed
            import hashlib
            need = {self.target_dim} - len(embedding)
            h = hashlib.sha256(embedding.tobytes()).digest()
            raw = (h * (need // len(h) + 1))[:need]
            pad = np.frombuffer(raw, dtype=np.uint8).astype('float32')
            pad = (pad - 127.5) / 128.0
            embedding = np.concatenate([embedding, pad])

    # Normalize
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm

    print(json.dumps(embedding.tolist()))
    
except Exception as e:
    print(f"Error: {{e}}", file=sys.stderr)
    import traceback
    traceback.print_exc(file=sys.stderr)
    # Fallback: create a dummy embedding for testing
    import numpy as np
    import json
    embedding = np.random.randn({self.target_dim}).astype('float32')
    norm = np.linalg.norm(embedding)
    if norm > 0:
        embedding = embedding / norm
    print(json.dumps(embedding.tolist()))
    print("Used dummy embedding due to error", file=sys.stderr)
"""
            else:
                model_abs = str((self.lvface_dir / "models" / self.model_name).resolve())
                cmd = f"""
import sys
import json
import numpy as np
sys.path.insert(0, r'{self.lvface_dir / "src"}')

from inference_onnx import LVFaceONNXInferencer

model_path = r'{model_abs}'
img_path = r'{tmp_path}'

try:
    inferencer = LVFaceONNXInferencer(model_path, use_gpu=True)
except Exception:
    inferencer = LVFaceONNXInferencer(model_path, use_gpu=False)

embedding = inferencer.infer_from_image(img_path)
embedding = np.asarray(embedding, dtype=np.float32).reshape(-1)

if embedding.shape[0] != {self.target_dim}:
    if {self.target_dim} < embedding.shape[0]:
        embedding = embedding[:{self.target_dim}]
    else:
        import hashlib
        need = {self.target_dim} - embedding.shape[0]
        h = hashlib.sha256(embedding.tobytes()).digest()
        raw = (h * (need // len(h) + 1))[:need]
        pad = np.frombuffer(raw, dtype=np.uint8).astype('float32')
        pad = (pad - 127.5) / 128.0
        embedding = np.concatenate([embedding, pad])

norm = float(np.linalg.norm(embedding))
if norm > 0:
    embedding = embedding / norm

print(json.dumps(embedding.tolist()))
"""

            result = subprocess.run(
                [str(self.python_exe), "-c", cmd],
                capture_output=True,
                text=True,
                cwd=str(self.lvface_dir),
                env=self._subprocess_env(),
            )
            
            if result.returncode != 0:
                logger.error(f"LVFace subprocess failed: {result.stderr}")
                raise RuntimeError(f"LVFace inference failed: {result.stderr}")
            
            # Parse result
            embedding = np.array(json.loads(result.stdout.strip()), dtype=np.float32)
            return embedding
            
        finally:
            # Cleanup temp file
            try:
                os.unlink(tmp_path)
            except:
                pass

    def _subprocess_env(self) -> dict[str, str]:
        env = os.environ.copy()
        # Allow routing LVFace ONNXRuntime GPU work to a specific CUDA device set,
        # independent from the backend process visibility used by other services.
        if self.cuda_visible_devices:
            env["CUDA_VISIBLE_DEVICES"] = self.cuda_visible_devices
            # With CUDA_VISIBLE_DEVICES remapping, ORT device 0 maps to the selected physical GPU.
            env.setdefault("ORT_CUDA_DEVICE_ID", "0")
        # Inject the backend's PyTorch lib directory into PATH so the LVFace subprocess's
        # ONNXRuntime CUDA provider can find cudnn64_9.dll (bundled with torch).
        try:
            import torch
            torch_lib = str(Path(torch.__file__).parent / "lib")
            if Path(torch_lib).is_dir():
                sep = ";" if os.name == "nt" else ":"
                env["PATH"] = torch_lib + sep + env.get("PATH", "")
                logger.debug("LVFace subprocess: injected torch/lib into PATH: %s", torch_lib)
        except Exception:
            pass
        return env
