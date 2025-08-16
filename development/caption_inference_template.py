#!/usr/bin/env python3
"""
Caption Models Inference Script

This script should be placed in your external caption models directory 
(e.g., ../vlmCaptionModels/inference.py) with a virtual environment containing
the necessary dependencies for your chosen caption models.

Directory structure should be:
vlmCaptionModels/
├── .venv/                    # Virtual environment with transformers, torch, etc.
├── inference.py              # This script
├── requirements.txt          # Optional: model dependencies
├── models/                   # Optional: downloaded models cache
└── .cache/                   # Optional: transformers cache

The main process will call this script via subprocess with:
python inference.py --provider qwen2.5-vl --model auto --image /path/to/image.png

Expected JSON output format:
{
    "caption": "A detailed description of the image",
    "model": "qwen2.5-vl-7b-instruct",
    "provider": "qwen2.5-vl"
}
"""

import argparse
import json
import sys
import logging
from pathlib import Path
from PIL import Image

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_qwen2vl_model(model_name: str):
    """Load Qwen2.5-VL model."""
    try:
        from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
        import torch
        
        if model_name == "auto" or model_name == "default":
            model_name = "Qwen/Qwen2.5-VL-7B-Instruct"
        
        logger.info(f"Loading Qwen2.5-VL model: {model_name}")
        
        model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.bfloat16,
            device_map="auto"
        )
        processor = AutoProcessor.from_pretrained(model_name)
        
        return model, processor, model_name
        
    except ImportError as e:
        logger.error("Failed to import Qwen2VL dependencies. Install with: pip install transformers torch qwen-vl-utils")
        raise
    except Exception as e:
        logger.error(f"Failed to load Qwen2.5-VL model: {e}")
        raise

def load_llava_next_model(model_name: str):
    """Load LLaVA-NeXT model."""
    try:
        from transformers import LlavaNextProcessor, LlavaNextForConditionalGeneration
        import torch
        
        if model_name == "auto" or model_name == "default":
            model_name = "llava-hf/llava-v1.6-mistral-7b-hf"
        
        logger.info(f"Loading LLaVA-NeXT model: {model_name}")
        
        processor = LlavaNextProcessor.from_pretrained(model_name)
        model = LlavaNextForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            device_map="auto"
        )
        
        return model, processor, model_name
        
    except ImportError as e:
        logger.error("Failed to import LLaVA-NeXT dependencies. Install with: pip install transformers torch")
        raise
    except Exception as e:
        logger.error(f"Failed to load LLaVA-NeXT model: {e}")
        raise

def load_blip2_model(model_name: str):
    """Load BLIP2 model."""
    try:
        from transformers import Blip2Processor, Blip2ForConditionalGeneration
        import torch
        
        if model_name == "auto" or model_name == "default":
            model_name = "Salesforce/blip2-opt-2.7b"
        
        logger.info(f"Loading BLIP2 model: {model_name}")
        
        processor = Blip2Processor.from_pretrained(model_name)
        model = Blip2ForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            device_map="auto"
        )
        
        return model, processor, model_name
        
    except ImportError as e:
        logger.error("Failed to import BLIP2 dependencies. Install with: pip install transformers torch")
        raise
    except Exception as e:
        logger.error(f"Failed to load BLIP2 model: {e}")
        raise

def generate_qwen2vl_caption(model, processor, image, model_name: str) -> str:
    """Generate caption using Qwen2.5-VL."""
    import torch
    
    # Prepare conversation message
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "Describe this image in detail."}
            ]
        }
    ]
    
    # Apply chat template
    text = processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
    
    # Process inputs
    image_inputs, video_inputs = process_vision_info(messages)
    inputs = processor(
        text=[text],
        images=image_inputs,
        videos=video_inputs,
        padding=True,
        return_tensors="pt"
    )
    inputs = inputs.to(model.device)
    
    # Generate response
    with torch.no_grad():
        generated_ids = model.generate(**inputs, max_new_tokens=200)
    
    # Trim input tokens and decode
    generated_ids_trimmed = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
    ]
    
    output_text = processor.batch_decode(
        generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
    )
    
    return output_text[0].strip()

def generate_llava_next_caption(model, processor, image, model_name: str) -> str:
    """Generate caption using LLaVA-NeXT."""
    import torch
    
    prompt = "[INST] <image>\nDescribe this image in detail. [/INST]"
    
    inputs = processor(prompt, image, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        output = model.generate(**inputs, max_new_tokens=200, do_sample=False)
    
    # Decode only the new tokens (after the input)
    response = processor.decode(output[0][len(inputs.input_ids[0]):], skip_special_tokens=True)
    return response.strip()

def generate_blip2_caption(model, processor, image, model_name: str) -> str:
    """Generate caption using BLIP2."""
    import torch
    
    inputs = processor(image, return_tensors="pt").to(model.device)
    
    with torch.no_grad():
        out = model.generate(**inputs, max_new_tokens=200)
    
    caption = processor.decode(out[0], skip_special_tokens=True).strip()
    return caption

def process_vision_info(messages):
    """Process vision info for Qwen2VL."""
    image_inputs = []
    video_inputs = []
    
    for message in messages:
        if isinstance(message.get("content"), list):
            for content in message["content"]:
                if content.get("type") == "image":
                    image_inputs.append(content["image"])
                elif content.get("type") == "video":
                    video_inputs.append(content["video"])
    
    return image_inputs, video_inputs

def generate_caption(provider: str, model_name: str, image_path: str) -> dict:
    """Generate caption for an image using the specified provider."""
    
    # Load image
    image = Image.open(image_path).convert('RGB')
    logger.info(f"Loaded image: {image_path} ({image.size})")
    
    # Load model and generate caption based on provider
    if provider == "qwen2.5-vl":
        model, processor, actual_model_name = load_qwen2vl_model(model_name)
        caption = generate_qwen2vl_caption(model, processor, image, actual_model_name)
    elif provider == "llava-next":
        model, processor, actual_model_name = load_llava_next_model(model_name)
        caption = generate_llava_next_caption(model, processor, image, actual_model_name)
    elif provider == "blip2":
        model, processor, actual_model_name = load_blip2_model(model_name)
        caption = generate_blip2_caption(model, processor, image, actual_model_name)
    else:
        raise ValueError(f"Unknown provider: {provider}")
    
    logger.info(f"Generated caption: {caption[:100]}...")
    
    return {
        "caption": caption,
        "model": actual_model_name,
        "provider": provider
    }

def main():
    parser = argparse.ArgumentParser(description="Generate image captions using various VLM models")
    parser.add_argument("--provider", required=True, choices=["qwen2.5-vl", "llava-next", "blip2"],
                        help="Caption model provider to use")
    parser.add_argument("--model", default="auto", 
                        help="Model name or 'auto' for default")
    parser.add_argument("--image", required=True,
                        help="Path to input image")
    
    args = parser.parse_args()
    
    try:
        result = generate_caption(args.provider, args.model, args.image)
        print(json.dumps(result))
    except Exception as e:
        logger.error(f"Caption generation failed: {e}")
        error_result = {
            "error": str(e),
            "provider": args.provider,
            "model": args.model
        }
        print(json.dumps(error_result))
        sys.exit(1)

if __name__ == "__main__":
    main()
