#!/usr/bin/env python3
"""
Qwen2.5-VL Caption Inference Script
Supports JSON communication for image captioning.
"""

import json
import sys
import base64
import io
from pathlib import Path
from typing import Dict, Any, Optional
import torch
from PIL import Image
from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
from qwen_vl_utils import process_vision_info


class Qwen25VLInference:
    def __init__(self, model_id: str = "Qwen/Qwen2.5-VL-3B-Instruct"):
        """Initialize Qwen2.5-VL model for inference."""
        self.model_id = model_id
        self.device = torch.device("cuda:0") if torch.cuda.is_available() else torch.device("cpu")
        if torch.cuda.is_available():
            torch.cuda.set_device(0)
        self.model = None
        self.processor = None
        self.tokenizer = None
        
    def load_model(self):
        """Load the Qwen2.5-VL model."""
        try:
            print("Loading Qwen2.5-VL model...", file=sys.stderr)
            
            # Clear any previous cache issues
            import transformers
            transformers.utils.logging.set_verbosity_warning()
            
            # Load model with explicit configuration 
            self.processor = AutoProcessor.from_pretrained(
                self.model_id, 
                trust_remote_code=True
            )
            
            self.model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.model_id,
                torch_dtype="auto",
                device_map="auto" if self.device == "cuda" else "cpu",
                trust_remote_code=True,
                low_cpu_mem_usage=True
            )
            
            # Set to evaluation mode
            self.model.eval()
            
            print("Model loaded successfully!", file=sys.stderr)
            return True
        except Exception as e:
            print(f"Error loading model: {e}", file=sys.stderr)
            # Try fallback to stub mode
            print("Falling back to stub caption mode", file=sys.stderr)
            return False
    
    def generate_caption(self, image_path: str, prompt: Optional[str] = None) -> str:
        """Generate caption for an image."""
        try:
            # If model failed to load, use stub mode
            if self.model is None:
                return "A photo (model not available)"
            
            # Load and process image
            image = Image.open(image_path).convert('RGB')
            
            # Default prompt for captioning
            if prompt is None:
                prompt = "Describe this image in detail."
            
            # Prepare messages for the model
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
            
            # Process the inputs
            text = self.processor.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True
            )
            
            # Process vision info and prepare inputs
            image_inputs, video_inputs = process_vision_info(messages)
            inputs = self.processor(
                text=[text],
                images=image_inputs,
                videos=video_inputs,
                padding=True,
                return_tensors="pt"
            )
            
            # Move inputs to device
            inputs = inputs.to(self.device)
            
            # Generate caption with controlled parameters
            with torch.no_grad():
                generated_ids = self.model.generate(
                    **inputs,
                    max_new_tokens=256,
                    do_sample=True,
                    temperature=0.7,
                    top_p=0.9,
                    pad_token_id=self.tokenizer.eos_token_id
                )
            
            # Extract only the new tokens (response)
            generated_ids_trimmed = [
                out_ids[len(in_ids):] 
                for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
            ]
            
            # Decode the response
            response = self.processor.batch_decode(
                generated_ids_trimmed, 
                skip_special_tokens=True, 
                clean_up_tokenization_spaces=False
            )[0]
            
            return response.strip()
            
        except Exception as e:
            print(f"Error generating caption: {e}", file=sys.stderr)
            return f"Error: {str(e)}"


def main():
    """Main function for JSON communication."""
    inference = Qwen25VLInference()
    
    # Send ready signal
    print(json.dumps({"status": "loading"}), flush=True)
    
    # Load model
    if not inference.load_model():
        print(json.dumps({"status": "error", "message": "Failed to load model, using stub mode"}), flush=True)
        # Continue with stub mode
    else:
        # Send ready signal
        print(json.dumps({"status": "ready"}), flush=True)
    
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
                        caption = inference.generate_caption(image_path, prompt)
                        response = {
                            "status": "success",
                            "caption": caption
                        }
                
                elif request.get("action") == "health":
                    response = {
                        "status": "healthy",
                        "model": inference.model_id,
                        "device": inference.device
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
