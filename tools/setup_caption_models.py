#!/usr/bin/env python3
"""
Setup script for external caption models directory.

This script helps set up a separate directory for caption models with
their own virtual environment, similar to the LVFace setup.

Usage:
    python setup_caption_models.py --dir ../vlmCaptionModels --provider qwen2-vl

This will create:
    ../vlmCaptionModels/
    ├── .venv/               # Virtual environment 
    ├── inference.py         # Inference script
    ├── requirements.txt     # Model dependencies
    └── README.md           # Setup instructions
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

REQUIREMENTS_TEMPLATES = {
    "qwen2.5-vl": [
        "torch>=2.0.0",
        "torchvision",
        "transformers>=4.37.0",
        "qwen-vl-utils",
        "pillow",
        "numpy",
        "accelerate",
    ],
    "llava-next": [
        "torch>=2.0.0", 
        "transformers>=4.37.0",
        "pillow",
        "numpy",
        "accelerate",
    ],
    "blip2": [
        "torch>=2.0.0",
        "transformers>=4.37.0", 
        "pillow",
        "numpy",
        "accelerate",
    ],
    "all": [
        "torch>=2.0.0",
        "transformers>=4.37.0",
        "qwen-vl-utils",
        "pillow",
        "numpy", 
        "accelerate",
    ]
}

README_TEMPLATE = """# VLM Caption Models

This directory contains the external caption models setup for the VLM Photo Engine.

## Setup

This directory was created with the setup script and contains:

- `.venv/` - Python virtual environment with model dependencies
- `inference.py` - Caption generation script  
- `requirements.txt` - Model dependencies
- `models/` - Optional: downloaded model cache
- `.cache/` - Optional: transformers cache directory

## Configuration

To use this external setup, set the environment variable:
```bash
export CAPTION_EXTERNAL_DIR={caption_dir}
export CAPTION_PROVIDER={provider}
```

Or in your .env file:
```
CAPTION_EXTERNAL_DIR={caption_dir}
CAPTION_PROVIDER={provider}
```

## Supported Providers

- `qwen2-vl` - Qwen2.5-VL models (recommended for latest performance)
- `llava-next` - LLaVA-NeXT models  
- `blip2` - BLIP2 baseline models

## Manual Setup

If you need to manually install additional dependencies:

```bash
cd {caption_dir}
source .venv/bin/activate  # or .venv\\Scripts\\activate on Windows
pip install <additional-packages>
```

## Testing

Test the setup with:
```bash
cd {caption_dir}
.venv/bin/python inference.py --provider {provider} --model auto --image /path/to/test/image.jpg
```

## Model Storage

Models will be automatically downloaded to:
- `models/` directory (if created)
- `.cache/` directory (transformers default)
- Or system-wide cache directory

Large models (7B+) require significant disk space and memory.
"""

def create_virtual_env(caption_dir: Path):
    """Create Python virtual environment."""
    venv_dir = caption_dir / ".venv"
    
    print(f"Creating virtual environment: {venv_dir}")
    subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
    
    # Get python executable path
    if os.name == 'nt':  # Windows
        python_exe = venv_dir / "Scripts" / "python.exe"
        pip_exe = venv_dir / "Scripts" / "pip.exe"
    else:  # Unix/Linux/macOS
        python_exe = venv_dir / "bin" / "python"
        pip_exe = venv_dir / "bin" / "pip"
    
    # Upgrade pip
    print("Upgrading pip...")
    subprocess.run([str(python_exe), "-m", "pip", "install", "--upgrade", "pip"], check=True)
    
    return python_exe, pip_exe

def install_requirements(pip_exe: Path, requirements: list):
    """Install requirements in virtual environment."""
    print(f"Installing requirements: {', '.join(requirements)}")
    subprocess.run([str(pip_exe), "install"] + requirements, check=True)

def copy_inference_script(caption_dir: Path):
    """Copy inference script template."""
    inference_path = caption_dir / "inference.py"
    template_path = Path(__file__).parent / "caption_inference_template.py"
    
    if template_path.exists():
        print(f"Copying inference script: {inference_path}")
        with open(template_path, 'r') as f:
            content = f.read()
        with open(inference_path, 'w') as f:
            f.write(content)
    else:
        print(f"Warning: Template not found at {template_path}")
        print("You'll need to create inference.py manually")

def create_requirements_file(caption_dir: Path, provider: str):
    """Create requirements.txt file."""
    requirements_path = caption_dir / "requirements.txt"
    requirements = REQUIREMENTS_TEMPLATES.get(provider, REQUIREMENTS_TEMPLATES["all"])
    
    print(f"Creating requirements.txt: {requirements_path}")
    with open(requirements_path, 'w') as f:
        for req in requirements:
            f.write(f"{req}\n")

def create_readme(caption_dir: Path, provider: str):
    """Create README.md file."""
    readme_path = caption_dir / "README.md"
    
    print(f"Creating README.md: {readme_path}")
    content = README_TEMPLATE.format(
        caption_dir=str(caption_dir.absolute()),
        provider=provider
    )
    
    with open(readme_path, 'w') as f:
        f.write(content)

def main():
    parser = argparse.ArgumentParser(description="Set up external caption models directory")
    parser.add_argument("--dir", required=True, help="Directory to create for caption models")
    parser.add_argument("--provider", default="qwen2.5-vl", 
                        choices=["qwen2.5-vl", "llava-next", "blip2", "all"],
                        help="Primary caption provider to set up")
    parser.add_argument("--skip-install", action="store_true",
                        help="Skip installing dependencies (just create structure)")
    
    args = parser.parse_args()
    
    caption_dir = Path(args.dir).resolve()
    
    print(f"Setting up caption models directory: {caption_dir}")
    print(f"Primary provider: {args.provider}")
    
    # Create directory
    caption_dir.mkdir(parents=True, exist_ok=True)
    
    # Create subdirectories
    (caption_dir / "models").mkdir(exist_ok=True)
    (caption_dir / ".cache").mkdir(exist_ok=True)
    
    # Create virtual environment
    python_exe, pip_exe = create_virtual_env(caption_dir)
    
    # Copy inference script
    copy_inference_script(caption_dir)
    
    # Create requirements file
    create_requirements_file(caption_dir, args.provider)
    
    # Create README
    create_readme(caption_dir, args.provider)
    
    # Install requirements
    if not args.skip_install:
        requirements = REQUIREMENTS_TEMPLATES.get(args.provider, REQUIREMENTS_TEMPLATES["all"])
        install_requirements(pip_exe, requirements)
    
    print("\n" + "="*60)
    print("Caption models directory setup complete!")
    print(f"Directory: {caption_dir}")
    print(f"Python: {python_exe}")
    print("\nTo use this setup, set environment variables:")
    print(f"export CAPTION_EXTERNAL_DIR={caption_dir}")
    print(f"export CAPTION_PROVIDER={args.provider}")
    print("\nOr add to your .env file:")
    print(f"CAPTION_EXTERNAL_DIR={caption_dir}")
    print(f"CAPTION_PROVIDER={args.provider}")

if __name__ == "__main__":
    main()
