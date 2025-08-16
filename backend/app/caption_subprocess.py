"""Caption subprocess wrapper for using external caption models installation."""
import json
import subprocess
import tempfile
import os
from pathlib import Path
from PIL import Image
import logging

logger = logging.getLogger(__name__)

class CaptionSubprocessProvider:
    """Caption provider that calls external caption models installation via subprocess.
    
    This allows using real caption models (Qwen2.5-VL, LLaVA-NeXT, etc.) while keeping dependencies isolated.
    """
    
    def __init__(self, caption_dir: str, provider_name: str, model_name: str = "auto"):
        self.caption_dir = Path(caption_dir)
        self.provider_name = provider_name
        self.model_name = model_name
        
        # Determine python executable path
        if os.name == 'nt':  # Windows
            self.python_exe = self.caption_dir / ".venv" / "Scripts" / "python.exe"
        else:  # Unix/Linux/macOS
            self.python_exe = self.caption_dir / ".venv" / "bin" / "python"
        
        # Verify the setup
        if not self.caption_dir.exists():
            raise RuntimeError(f"Caption models directory not found: {caption_dir}")
        if not self.python_exe.exists():
            raise RuntimeError(f"Caption models Python executable not found: {self.python_exe}")
        
        # Check if inference_backend.py exists (backend-compatible script)
        inference_script = self.caption_dir / "inference_backend.py"
        if not inference_script.exists():
            # Fallback to inference.py
            inference_script = self.caption_dir / "inference.py"
            if not inference_script.exists():
                raise RuntimeError(f"Caption inference script not found: {inference_script}. Please ensure the external caption directory has an inference.py or inference_backend.py script.")
    
    def generate_caption(self, image: Image.Image) -> str:
        """Generate caption using external caption models subprocess."""
        # Create temporary image file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
            # Ensure RGB format
            image = image.convert('RGB')
            image.save(tmp_path, 'PNG')
        
        try:
            # Call caption inference script - prefer backend-compatible version
            inference_script = "inference_backend.py"
            if not (self.caption_dir / inference_script).exists():
                inference_script = "inference.py"
            
            cmd = [
                str(self.python_exe),
                inference_script,
                "--provider", self.provider_name,
                "--model", self.model_name,
                "--image", tmp_path
            ]
            
            logger.debug(f"Running caption subprocess: {' '.join(cmd)} (in {self.caption_dir})")
            
            result = subprocess.run(
                cmd,
                cwd=str(self.caption_dir),
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout for model inference (includes loading)
            )
            
            if result.returncode != 0:
                error_msg = f"Caption subprocess failed (exit {result.returncode}): {result.stderr}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
            
            try:
                # Parse JSON response
                response = json.loads(result.stdout.strip())
                caption = response.get('caption', '')
                if not caption:
                    raise ValueError("Empty caption returned")
                
                logger.debug(f"Caption generated successfully: '{caption[:50]}...' (provider: {self.provider_name})")
                return caption
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse caption response JSON: {result.stdout}")
                raise RuntimeError(f"Invalid JSON response from caption subprocess: {e}")
                
        except subprocess.TimeoutExpired:
            logger.error("Caption subprocess timed out")
            raise RuntimeError("Caption generation timed out after 2 minutes")
        except Exception as e:
            logger.error(f"Caption subprocess error: {e}")
            raise
        finally:
            # Clean up temporary file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    
    def get_model_name(self) -> str:
        """Get the model name for this provider."""
        return f"{self.provider_name}-external"


class Qwen2VLSubprocessProvider(CaptionSubprocessProvider):
    """Qwen2.5-VL specific subprocess provider."""
    
    def __init__(self, caption_dir: str, model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct"):
        super().__init__(caption_dir, "qwen2.5-vl", model_name)
        
    def get_model_name(self) -> str:
        return f"qwen2.5-vl-external ({self.model_name})"


class LlavaNextSubprocessProvider(CaptionSubprocessProvider):
    """LLaVA-NeXT specific subprocess provider."""
    
    def __init__(self, caption_dir: str, model_name: str = "llava-hf/llava-v1.6-mistral-7b-hf"):
        super().__init__(caption_dir, "llava-next", model_name)
        
    def get_model_name(self) -> str:
        return f"llava-next-external ({self.model_name})"


class BLIP2SubprocessProvider(CaptionSubprocessProvider):
    """BLIP2 specific subprocess provider."""
    
    def __init__(self, caption_dir: str, model_name: str = "Salesforce/blip2-opt-2.7b"):
        super().__init__(caption_dir, "blip2", model_name)
        
    def get_model_name(self) -> str:
        return f"blip2-external ({self.model_name})"
