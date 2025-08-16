#!/usr/bin/env python3
"""
Smart Caption Inference Script with Local Models
Tries Qwen2.5-VL first, falls back to BLIP2 if it fails.
Uses local model directories instead of downloading from Hugging Face.
"""

import json
import sys
import base64
import io
from pathlib import Path
from typing import Dict, Any, Optional
import torch
from PIL import Image

# Global model instances
current_model = None
model_type = None

# Get the directory where this script is located
SCRIPT_DIR = Path(__file__).parent
LOCAL_MODELS_DIR = SCRIPT_DIR / "models"

def try_load_qwen25vl():
    """Try to load Qwen2.5-VL model from local directory."""
    try:
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        from qwen_vl_utils import process_vision_info
        
        print("Attempting to load Qwen2.5-VL from local directory...", file=sys.stderr)
        
        # Use local model path
        model_path = LOCAL_MODELS_DIR / "qwen2.5-vl-3b-instruct"
        if not model_path.exists():
            print(f"❌ Local Qwen2.5-VL model not found at {model_path}", file=sys.stderr)
            return None
            
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load processor first
        processor = AutoProcessor.from_pretrained(str(model_path), trust_remote_code=True)
        
        # Load model
        model = Qwen2VLForConditionalGeneration.from_pretrained(
            str(model_path),
            torch_dtype="auto",
            device_map="auto" if device == "cuda" else "cpu",
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        
        model.eval()
        
        print("✅ Qwen2.5-VL loaded successfully from local directory!", file=sys.stderr)
        return {
            'model': model,
            'processor': processor,
            'device': device,
            'type': 'qwen2.5-vl',
            'model_id': 'qwen2.5-vl-3b-instruct-local'
        }
    except Exception as e:
        print(f"❌ Qwen2.5-VL failed to load: {e}", file=sys.stderr)
        return None

def try_load_blip2():
    """Try to load BLIP2 model from local directory."""
    try:
        from transformers import Blip2Processor, Blip2ForConditionalGeneration
        
        print("Attempting to load BLIP2 from local directory...", file=sys.stderr)
        
        # Use local model path
        model_path = LOCAL_MODELS_DIR / "blip2-opt-2.7b"
        if not model_path.exists():
            print(f"❌ Local BLIP2 model not found at {model_path}", file=sys.stderr)
            return None
            
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load processor
        processor = Blip2Processor.from_pretrained(str(model_path))
        
        # Load model
        model = Blip2ForConditionalGeneration.from_pretrained(
            str(model_path),
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None
        )
        
        if device == "cpu":
            model = model.to(device)
            
        model.eval()
        
        print("✅ BLIP2 loaded successfully from local directory!", file=sys.stderr)
        return {
            'model': model,
            'processor': processor,
            'device': device,
            'type': 'blip2',
            'model_id': 'blip2-opt-2.7b-local'
        }
    except Exception as e:
        print(f"❌ BLIP2 failed to load: {e}", file=sys.stderr)
        return None

def load_best_available_model():
    """Load the best available model."""
    global current_model, model_type
    
    # Try Qwen2.5-VL first
    current_model = try_load_qwen25vl()
    if current_model:
        model_type = current_model['type']
        return current_model
    
    # Fall back to BLIP2
    current_model = try_load_blip2()
    if current_model:
        model_type = current_model['type']
        return current_model
    
    # No models available
    print("❌ No caption models could be loaded", file=sys.stderr)
    return None

def load_image_from_path_or_url(image_path: str) -> Optional[Image.Image]:
    """Load image from file path or URL."""
    try:
        if image_path.startswith(('http://', 'https://')):
            import requests
            response = requests.get(image_path, timeout=30)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
        else:
            image = Image.open(image_path)
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        return image
    except Exception as e:
        print(f"Error loading image: {e}", file=sys.stderr)
        return None

def load_image_from_base64(base64_data: str) -> Optional[Image.Image]:
    """Load image from base64 string."""
    try:
        # Remove data URL prefix if present
        if base64_data.startswith('data:image'):
            base64_data = base64_data.split(',', 1)[1]
        
        image_bytes = base64.b64decode(base64_data)
        image = Image.open(io.BytesIO(image_bytes))
        
        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')
        
        return image
    except Exception as e:
        print(f"Error loading image from base64: {e}", file=sys.stderr)
        return None

def generate_caption_qwen25vl(image: Image.Image, prompt: str) -> str:
    """Generate caption using Qwen2.5-VL model."""
    try:
        from qwen_vl_utils import process_vision_info
        
        model_data = current_model
        model = model_data['model']
        processor = model_data['processor']
        device = model_data['device']
        
        # Create conversation format
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        
        # Process the conversation
        text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        
        # Prepare inputs
        inputs = processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        
        # Move to device
        inputs = inputs.to(device)
        
        # Generate
        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=256,
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )
        
        # Decode response
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        output_text = processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]
        
        return output_text.strip()
        
    except Exception as e:
        raise Exception(f"Qwen2.5-VL caption generation failed: {e}")

def generate_caption_blip2(image: Image.Image, prompt: str) -> str:
    """Generate caption using BLIP2 model."""
    try:
        model_data = current_model
        model = model_data['model']
        processor = model_data['processor']
        device = model_data['device']
        
        # Prepare inputs
        inputs = processor(images=image, text=prompt, return_tensors="pt")
        inputs = inputs.to(device)
        
        # Generate
        with torch.no_grad():
            generated_ids = model.generate(
                **inputs,
                max_new_tokens=100,
                num_beams=5,
                length_penalty=1.0,
                early_stopping=True
            )
        
        # Decode
        caption = processor.decode(generated_ids[0], skip_special_tokens=True)
        
        # Clean up the caption (remove the prompt if it's included)
        if prompt.lower() in caption.lower():
            caption = caption.replace(prompt, "").strip()
        
        return caption.strip()
        
    except Exception as e:
        raise Exception(f"BLIP2 caption generation failed: {e}")

def process_caption_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Process a caption generation request."""
    try:
        # Extract image and prompt
        image_path = data.get('image_path')
        image_base64 = data.get('image_base64')
        prompt = data.get('prompt', 'Describe this image')
        
        # Load image
        image = None
        if image_path:
            image = load_image_from_path_or_url(image_path)
            if not image:
                return {"status": "error", "message": f"Image not found: {image_path}"}
        elif image_base64:
            image = load_image_from_base64(image_base64)
            if not image:
                return {"status": "error", "message": "Failed to decode base64 image"}
        else:
            return {"status": "error", "message": "No image provided (image_path or image_base64 required)"}
        
        # Generate caption based on model type
        if model_type == 'qwen2.5-vl':
            caption = generate_caption_qwen25vl(image, prompt)
        elif model_type == 'blip2':
            caption = generate_caption_blip2(image, prompt)
        else:
            return {"status": "error", "message": "No model loaded"}
        
        return {
            "status": "success",
            "caption": caption,
            "model_type": model_type,
            "model_id": current_model['model_id']
        }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}

def main():
    """Main function to handle requests."""
    # Initialize model
    print(json.dumps({"status": "loading"}))
    
    model = load_best_available_model()
    if not model:
        print(json.dumps({"status": "ready", "model_type": "stub", "message": "No models available, using stub mode"}))
        # Continue running in stub mode
        model_type = "stub"
    else:
        print(json.dumps({
            "status": "ready", 
            "model_type": model['type'], 
            "model_id": model['model_id']
        }))
    
    # Process requests
    try:
        if len(sys.argv) > 1:
            # File input mode
            input_file = sys.argv[1]
            with open(input_file, 'r') as f:
                data = json.load(f)
        else:
            # Stdin mode
            input_text = sys.stdin.read().strip()
            if not input_text:
                return
            data = json.loads(input_text)
        
        # Handle different actions
        action = data.get('action', 'caption')
        
        if action == 'health':
            if current_model:
                result = {
                    "status": "healthy", 
                    "model_type": current_model['type'], 
                    "model_id": current_model['model_id'],
                    "device": current_model['device']
                }
            else:
                result = {"status": "healthy", "model_type": "stub", "message": "Running in stub mode"}
        elif action == 'caption':
            if current_model:
                result = process_caption_request(data)
            else:
                result = {"status": "success", "caption": f"[STUB] This is a placeholder caption for the image", "model_type": "stub"}
        else:
            result = {"status": "error", "message": f"Unknown action: {action}"}
        
        print(json.dumps(result))
        
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted"}))
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}))

if __name__ == "__main__":
    main()
