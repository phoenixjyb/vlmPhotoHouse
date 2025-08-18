"""Caption models validation and setup verification."""

import os
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

class CaptionValidationError(Exception):
    """Exception raised for caption models validation errors."""
    pass

def validate_caption_external_setup() -> None:
    """Validate external caption models setup similar to LVFace validation.
    
    Raises:
        CaptionValidationError: If validation fails
    """
    from .config import get_settings
    settings = get_settings()
    
    if not settings.caption_external_dir:
        raise CaptionValidationError("CAPTION_EXTERNAL_DIR not configured")
        
    external_dir = Path(settings.caption_external_dir)
    
    # Check if directory exists
    if not external_dir.exists():
        raise CaptionValidationError(f"Caption external directory not found: {external_dir}")
    
    # Check Python virtual environment
    if os.name == 'nt':  # Windows
        python_exe = external_dir / ".venv" / "Scripts" / "python.exe"
    else:  # Unix/Linux/macOS
        python_exe = external_dir / ".venv" / "bin" / "python"
        
    if not python_exe.exists():
        raise CaptionValidationError(f"Caption Python executable not found in {external_dir}/.venv/")
    
    # Check inference script exists (prefer backend-specific but allow generic)
    inference_backend = external_dir / "inference_backend.py"
    inference_py = external_dir / "inference.py"
    if not inference_backend.exists() and not inference_py.exists():
        raise CaptionValidationError(
            f"Caption inference script not found. Expected one of: {inference_backend} or {inference_py}"
        )
    
    # Check if there's a requirements.txt file
    requirements_file = external_dir / "requirements.txt"
    if not requirements_file.exists():
        logger.warning(f"No requirements.txt found in {external_dir} - this is optional but recommended")
    
    # Check for common model directories
    models_dir = external_dir / "models"
    cache_dir = external_dir / ".cache"
    
    if not models_dir.exists() and not cache_dir.exists():
        logger.warning(f"No models/ or .cache/ directory found in {external_dir} - models may be downloaded on first use")
    
    logger.info(f"✓ External caption models setup validated: {external_dir}")

def get_caption_config_summary() -> Dict[str, Any]:
    """Get a summary of current caption configuration for health endpoint."""
    from .config import get_settings
    settings = get_settings()
    
    summary = {
        "provider": settings.caption_provider,
        "device": settings.caption_device,
        "model": settings.caption_model,
        "mode": "external" if settings.caption_external_dir else "builtin"
    }
    
    if settings.caption_external_dir:
        external_dir = Path(settings.caption_external_dir)
        if os.name == 'nt':  # Windows
            python_exe = external_dir / ".venv" / "Scripts" / "python.exe"
        else:  # Unix/Linux/macOS
            python_exe = external_dir / ".venv" / "bin" / "python"
            
        summary.update({
            "external_dir": str(external_dir),
            "python_executable": str(python_exe),
            "python_exists": python_exe.exists(),
            "dir_exists": external_dir.exists(),
            "inference_backend_exists": (external_dir / "inference_backend.py").exists(),
            "inference_script_exists": (external_dir / "inference.py").exists(),
            "requirements_exists": (external_dir / "requirements.txt").exists(),
            "models_dir_exists": (external_dir / "models").exists(),
            "cache_dir_exists": (external_dir / ".cache").exists(),
        })
        
        # Try to validate
        try:
            validate_caption_external_setup()
            summary["validation_status"] = "valid"
        except CaptionValidationError as e:
            summary["validation_status"] = "invalid"
            summary["validation_error"] = str(e)
    
    return summary
