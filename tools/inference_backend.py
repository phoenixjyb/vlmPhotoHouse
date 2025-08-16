#!/usr/bin/env python3
"""
Caption Inference Script - Backend Compatible
Compatible with the vlmPhotoHouse backend subprocess interface.
Accepts command-line arguments and returns JSON response.
"""

import argparse
import json
import sys
import subprocess
from pathlib import Path

def main():
    """Main function to handle backend requests."""
    parser = argparse.ArgumentParser(description='Generate captions for images')
    parser.add_argument('--provider', type=str, default='auto', help='Caption provider (blip2, qwen2.5-vl, auto)')
    parser.add_argument('--model', type=str, default='auto', help='Model name')
    parser.add_argument('--image', type=str, required=True, help='Path to image file')
    parser.add_argument('--prompt', type=str, default='Describe this image', help='Caption prompt')
    
    args = parser.parse_args()
    
    try:
        # Get the directory where this script is located
        script_dir = Path(__file__).parent
        inference_script = script_dir / "inference.py"
        
        if not inference_script.exists():
            raise FileNotFoundError(f"Main inference script not found: {inference_script}")
        
        # Get Python executable from virtual environment
        if sys.platform == "win32":
            python_exe = script_dir / ".venv" / "Scripts" / "python.exe"
        else:
            python_exe = script_dir / ".venv" / "bin" / "python"
        
        if not python_exe.exists():
            python_exe = sys.executable  # Fallback to current Python
        
        # Prepare JSON input for the main inference script
        request_data = {
            "action": "caption",
            "image_path": args.image,
            "prompt": args.prompt
        }
        
        # Call the main inference script with JSON input
        result = subprocess.run(
            [str(python_exe), str(inference_script)],
            input=json.dumps(request_data),
            capture_output=True,
            text=True,
            timeout=600,
            cwd=str(script_dir)
        )
        
        if result.returncode != 0:
            # Return error response
            response = {
                "status": "error",
                "message": f"Inference failed: {result.stderr}"
            }
            print(json.dumps(response))
            sys.exit(1)
        
        # Parse the output lines to find the final result
        output_lines = result.stdout.strip().split('\n')
        final_response = None
        
        # Look for the final JSON response (status: success or error)
        for line in reversed(output_lines):
            line = line.strip()
            if line.startswith('{') and line.endswith('}'):
                try:
                    parsed = json.loads(line)
                    if parsed.get('status') in ['success', 'error']:
                        final_response = parsed
                        break
                except json.JSONDecodeError:
                    continue
        
        if final_response is None:
            # Fallback - try to find any valid JSON
            for line in reversed(output_lines):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    try:
                        final_response = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
        
        if final_response is None:
            response = {
                "status": "error", 
                "message": f"No valid JSON response found in output: {result.stdout[:200]}"
            }
        elif final_response.get('status') == 'success':
            # Extract caption and return in expected format
            caption = final_response.get('caption', 'No caption generated')
            response = {
                "caption": caption,
                "model_type": final_response.get('model_type', 'unknown'),
                "model_id": final_response.get('model_id', 'unknown')
            }
        else:
            # Error response from inference script
            response = {
                "status": "error",
                "message": final_response.get('message', 'Unknown error from inference script')
            }
        
        print(json.dumps(response))
        
    except Exception as e:
        # Return error response
        response = {
            "status": "error", 
            "message": str(e)
        }
        print(json.dumps(response))
        sys.exit(1)

if __name__ == "__main__":
    main()
