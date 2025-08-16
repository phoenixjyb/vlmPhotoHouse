"""Configuration validation for LVFace setup."""
import os
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

class LVFaceValidationError(Exception):
    """Raised when LVFace configuration is invalid."""
    pass

def validate_lvface_config() -> List[str]:
    """Validate LVFace configuration and return any warnings.
    
    Returns:
        List of warning messages (empty if all good)
        
    Raises:
        LVFaceValidationError: If configuration is invalid
    """
    from .config import get_settings
    
    settings = get_settings()
    warnings = []
    
    # Only validate if LVFace is actually being used
    if settings.face_embed_provider.lower() != 'lvface':
        return warnings
    
    logger.info("Validating LVFace configuration...")
    
    # Check if using external directory
    if settings.lvface_external_dir:
        external_dir = Path(settings.lvface_external_dir)
        
        # Validate external directory structure
        if not external_dir.exists():
            raise LVFaceValidationError(f"LVFace external directory not found: {external_dir}")
        
        # Check for Python executable
        python_exe = external_dir / ".venv" / "Scripts" / "python.exe"
        if not python_exe.exists():
            # Try Unix path
            python_exe = external_dir / ".venv" / "bin" / "python"
            if not python_exe.exists():
                raise LVFaceValidationError(f"LVFace Python executable not found in {external_dir}/.venv/")
        
        # Check for models directory
        models_dir = external_dir / "models"
        if not models_dir.exists():
            raise LVFaceValidationError(f"LVFace models directory not found: {models_dir}")
        
        # Check for specific model
        model_path = models_dir / settings.lvface_model_name
        if not model_path.exists():
            raise LVFaceValidationError(f"LVFace model not found: {model_path}")
        
        # Check for inference script
        inference_script = external_dir / "inference.py"
        if not inference_script.exists():
            raise LVFaceValidationError(f"LVFace inference.py not found: {inference_script}")
        
        logger.info(f"✓ External LVFace setup validated: {external_dir}")
        logger.info(f"✓ Model: {model_path}")
        logger.info(f"✓ Target dimension: {settings.face_embed_dim}")
        
    else:
        # Using built-in mode
        model_path = Path(settings.lvface_model_path)
        if not model_path.exists():
            warnings.append(f"Built-in LVFace model not found: {model_path}")
            warnings.append("Consider generating a dummy model with: python tools/generate_dummy_lvface_model.py")
        else:
            logger.info(f"✓ Built-in LVFace model found: {model_path}")
    
    return warnings

def validate_startup_config() -> None:
    """Validate overall startup configuration.
    
    Raises:
        LVFaceValidationError: If critical configuration is invalid
    """
    try:
        warnings = validate_lvface_config()
        for warning in warnings:
            logger.warning(f"LVFace: {warning}")
            
        if warnings:
            logger.warning("LVFace validation completed with warnings. System will fallback to stub provider if needed.")
        else:
            logger.info("LVFace configuration validation passed.")
            
    except LVFaceValidationError as e:
        logger.error(f"LVFace configuration error: {e}")
        logger.error("System will fallback to stub face embedding provider.")
        # Don't raise - let the system start with fallback
    except Exception as e:
        logger.error(f"Unexpected error during LVFace validation: {e}")

def get_config_summary() -> dict:
    """Get a summary of current LVFace configuration for health endpoint."""
    from .config import get_settings
    
    settings = get_settings()
    
    if settings.face_embed_provider.lower() != 'lvface':
        return {"provider": settings.face_embed_provider, "status": "not_using_lvface"}
    
    summary = {
        "provider": "lvface",
        "embed_dim": settings.face_embed_dim,
        "mode": "external" if settings.lvface_external_dir else "builtin"
    }
    
    if settings.lvface_external_dir:
        external_dir = Path(settings.lvface_external_dir)
        model_path = external_dir / "models" / settings.lvface_model_name
        summary.update({
            "external_dir": str(external_dir),
            "model_name": settings.lvface_model_name,
            "model_exists": model_path.exists(),
            "inference_script_exists": (external_dir / "inference.py").exists()
        })
    else:
        model_path = Path(settings.lvface_model_path)
        summary.update({
            "model_path": str(model_path),
            "model_exists": model_path.exists()
        })
    
    return summary
