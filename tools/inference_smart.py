#!/usr/bin/env python3
"""
Smart Caption Inference Script
Tries Qwen2.5-VL first, falls back to BLIP2 if it fails.
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

def try_load_qwen25vl():
    """Try to load Qwen2.5-VL model."""
    try:
        from transformers import Qwen2VLForConditionalGeneration, AutoProcessor
        from qwen_vl_utils import process_vision_info
        
        print("Attempting to load Qwen2.5-VL...", file=sys.stderr)
        
        model_id = "Qwen/Qwen2.5-VL-3B-Instruct"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load processor first
        processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
        
        # Load model
        model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype="auto",
            device_map="auto" if device == "cuda" else "cpu",
            trust_remote_code=True,
            low_cpu_mem_usage=True
        )
        
        model.eval()
        
        print("✅ Qwen2.5-VL loaded successfully!", file=sys.stderr)
        return {
            'model': model,
            'processor': processor,
            'device': device,
            'type': 'qwen2.5-vl',
            'model_id': model_id
        }
    except Exception as e:
        print(f"❌ Qwen2.5-VL failed to load: {e}", file=sys.stderr)
        return None

def try_load_blip2():
    """Try to load BLIP2 model."""
    try:
        from transformers import Blip2Processor, Blip2ForConditionalGeneration
        
        print("Attempting to load BLIP2...", file=sys.stderr)
        
        model_id = "Salesforce/blip2-opt-2.7b"
        device = "cuda" if torch.cuda.is_available() else "cpu"
        
        # Load processor
        processor = Blip2Processor.from_pretrained(model_id)
        
        # Load model
        model = Blip2ForConditionalGeneration.from_pretrained(
            model_id,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None
        )
        
        if device == "cpu":
            model = model.to(device)
            
        model.eval()
        
        print("✅ BLIP2 loaded successfully!", file=sys.stderr)
        return {
            'model': model,
            'processor': processor,
            'device': device,
            'type': 'blip2',
            'model_id': model_id
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
        model_type = 'qwen2.5-vl'
        return True
    
    # Fall back to BLIP2
    current_model = try_load_blip2()
    if current_model:
        model_type = 'blip2'
        return True
    
    # No model available
    print("❌ No caption models could be loaded", file=sys.stderr)
    model_type = 'stub'
    return False

def generate_caption_qwen25vl(image_path: str, prompt: Optional[str] = None) -> str:
    """Generate caption using Qwen2.5-VL."""
    try:
        from qwen_vl_utils import process_vision_info
        
        # Load image
        image = Image.open(image_path).convert('RGB')
        
        # Default prompt
        if prompt is None:
            prompt = "Describe this image in detail."
        
        # Prepare messages
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": prompt}
                ]
            }
        ]
        
        # Process inputs
        text = current_model['processor'].apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = current_model['processor'](
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        
        inputs = inputs.to(current_model['device'])
        
        # Generate
        with torch.no_grad():
            generated_ids = current_model['model'].generate(
                **inputs,
                max_new_tokens=256,
                do_sample=True,
                temperature=0.7,
                top_p=0.9
            )
        
        # Decode
        generated_ids_trimmed = [
            out_ids[len(in_ids):] 
            for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        response = current_model['processor'].batch_decode(
            generated_ids_trimmed, 
            skip_special_tokens=True, 
            clean_up_tokenization_spaces=False
        )[0]
        
        return response.strip()
        
    except Exception as e:
        return f"Error with Qwen2.5-VL: {str(e)}"

def generate_caption_blip2(image_path: str, prompt: Optional[str] = None) -> str:
    """Generate caption using BLIP2."""
    try:
        # Load image
        image = Image.open(image_path).convert('RGB')
        
        # Process image
        inputs = current_model['processor'](image, return_tensors="pt").to(current_model['device'])
        
        # Generate
        with torch.no_grad():
            generated_ids = current_model['model'].generate(
                **inputs,
                max_length=100,
                num_beams=5,
                early_stopping=True
            )
        
        # Decode
        caption = current_model['processor'].decode(generated_ids[0], skip_special_tokens=True)
        
        return caption.strip()
        
    except Exception as e:
        return f"Error with BLIP2: {str(e)}"

def generate_caption(image_path: str, prompt: Optional[str] = None) -> str:
    """Generate caption using the loaded model."""
    if model_type == 'qwen2.5-vl':
        return generate_caption_qwen25vl(image_path, prompt)
    elif model_type == 'blip2':
        return generate_caption_blip2(image_path, prompt)
    else:
        return "A photo (no caption model available)"

def main():
    """Main function for JSON communication."""
    global current_model, model_type
    
    # Send loading signal
    print(json.dumps({"status": "loading"}), flush=True)
    
    # Load model
    success = load_best_available_model()
    
    if success:
        print(json.dumps({
            "status": "ready", 
            "model_type": model_type,
            "model_id": current_model['model_id']
        }), flush=True)
    else:
        print(json.dumps({
            "status": "ready", 
            "model_type": "stub",
            "message": "No models available, using stub mode"
        }), flush=True)
    
    # Process requests
    try:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
                
            try:
                request = json.loads(line)
                
                if request.get("action") == "caption":
                    image_path = request.get("image_path")
                    prompt = request.get("prompt")
                    
                    if not image_path or not Path(image_path).exists():
                        response = {
                            "status": "error",
                            "message": f"Image not found: {image_path}"
                        }
                    else:
                        caption = generate_caption(image_path, prompt)
                        response = {
                            "status": "success",
                            "caption": caption,
                            "model_used": model_type
                        }
                
                elif request.get("action") == "health":
                    response = {
                        "status": "healthy",
                        "model_type": model_type,
                        "model_id": current_model['model_id'] if current_model else "none",
                        "device": current_model['device'] if current_model else "none"
                    }
                
                elif request.get("action") == "exit":
                    response = {"status": "goodbye"}
                    print(json.dumps(response), flush=True)
                    break
                
                else:
                    response = {
                        "status": "error",
                        "message": f"Unknown action: {request.get('action')}"
                    }
                
                print(json.dumps(response), flush=True)
                
            except json.JSONDecodeError as e:
                error_response = {
                    "status": "error",
                    "message": f"Invalid JSON: {str(e)}"
                }
                print(json.dumps(error_response), flush=True)
            
    except KeyboardInterrupt:
        print(json.dumps({"status": "interrupted"}), flush=True)
    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}), flush=True)


if __name__ == "__main__":
    main()
