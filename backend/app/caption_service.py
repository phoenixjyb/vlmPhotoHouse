"""Vision-Language Models for Image Captioning."""
import os
import time
import logging
from functools import lru_cache
from typing import Protocol, Optional
from PIL import Image
import json

logger = logging.getLogger(__name__)

class CaptionProvider(Protocol):
    def generate_caption(self, image: Image.Image, prompt: Optional[str] = None) -> str: ...
    def get_model_name(self) -> str: ...

class StubCaptionProvider:
    """Stub caption provider that generates heuristic captions."""
    
    def __init__(self):
        self.model_name = "stub-heuristic"
    
    def generate_caption(self, image: Image.Image, prompt: Optional[str] = None) -> str:
        # Simple heuristic based on image properties
        width, height = image.size
        mode = image.mode
        
        if width > height * 1.5:
            orientation = "landscape"
        elif height > width * 1.5:
            orientation = "portrait"
        else:
            orientation = "square"
        
        if width * height < 500 * 500:
            size = "small"
        elif width * height > 2000 * 2000:
            size = "large"
        else:
            size = "medium"
        
        return f"A {size} {orientation} photo"
    
    def get_model_name(self) -> str:
        return self.model_name

class LlavaNextCaptionProvider:
    """LLaVA-NeXT (LLaVA-1.6) caption provider."""
    
    def __init__(self, model_name: str = "llava-hf/llava-v1.6-mistral-7b-hf", device: str = "cpu"):
        try:
            from transformers import LlavaNextProcessor, LlavaNextForConditionalGeneration
            import torch
        except ImportError as e:
            raise RuntimeError("LLaVA dependencies not available. Install with 'pip install transformers torch pillow'") from e
        
        self.device = device
        self.model_name = model_name
        
        logger.info(f"Loading LLaVA-NeXT model: {model_name}")
        t0 = time.time()
        
        self.processor = LlavaNextProcessor.from_pretrained(model_name)
        self.model = LlavaNextForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            low_cpu_mem_usage=True
        ).to(device)
        
        load_time = time.time() - t0
        logger.info(f"LLaVA-NeXT model loaded in {load_time:.1f}s")
        
        # Log metrics if available
        try:
            import app.metrics as m
            m.face_embedding_model_load_seconds.labels('llava').observe(load_time)
        except Exception:
            pass
    
    def generate_caption(self, image: Image.Image, prompt: Optional[str] = None) -> str:
        """Generate caption for image using LLaVA-NeXT."""
        import torch
        
        # Default prompt for captioning
        if prompt is None:
            prompt = "USER: <image>\\nDescribe this image in detail. ASSISTANT:"
        
        # Prepare inputs
        inputs = self.processor(prompt, image, return_tensors="pt").to(self.device)
        
        # Generate caption
        with torch.no_grad():
            output = self.model.generate(
                **inputs,
                max_new_tokens=200,
                do_sample=True,
                temperature=0.7,
                pad_token_id=self.processor.tokenizer.eos_token_id
            )
        
        # Decode response
        response = self.processor.decode(output[0], skip_special_tokens=True)
        
        # Extract just the assistant's response
        if "ASSISTANT:" in response:
            caption = response.split("ASSISTANT:")[-1].strip()
        else:
            caption = response.strip()
        
        return caption
    
    def get_model_name(self) -> str:
        return self.model_name

class Qwen2VLCaptionProvider:
    """Qwen2-VL caption provider - state-of-the-art as of Aug 2024."""
    
    def __init__(self, model_name: str = "Qwen/Qwen2-VL-7B-Instruct", device: str = "cpu"):
        try:
            from transformers import Qwen2VLForConditionalGeneration, AutoTokenizer, AutoProcessor
            import torch
        except ImportError as e:
            raise RuntimeError("Qwen2-VL dependencies not available. Install with 'pip install transformers torch pillow qwen-vl-utils'") from e
        
        self.device = device
        self.model_name = model_name
        
        logger.info(f"Loading Qwen2-VL model: {model_name}")
        t0 = time.time()
        
        self.model = Qwen2VLForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype="auto" if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None
        )
        
        self.processor = AutoProcessor.from_pretrained(model_name)
        
        load_time = time.time() - t0
        logger.info(f"Qwen2-VL model loaded in {load_time:.1f}s")
    
    def generate_caption(self, image: Image.Image, prompt: Optional[str] = None) -> str:
        """Generate caption using Qwen2-VL."""
        import torch
        
        # Prepare conversation format
        if prompt is None:
            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": "Describe this image in detail."}
                    ]
                }
            ]
        else:
            messages = [
                {
                    "role": "user", 
                    "content": [
                        {"type": "image", "image": image},
                        {"type": "text", "text": prompt}
                    ]
                }
            ]
        
        # Prepare inputs
        text = self.processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        image_inputs, video_inputs = process_vision_info(messages)
        inputs = self.processor(
            text=[text],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt"
        )
        inputs = inputs.to(self.device)
        
        # Generate
        with torch.no_grad():
            generated_ids = self.model.generate(**inputs, max_new_tokens=200)
        
        # Trim input tokens and decode
        generated_ids_trimmed = [
            out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, generated_ids)
        ]
        
        output_text = self.processor.batch_decode(
            generated_ids_trimmed, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )
        
        return output_text[0].strip()
    
    def get_model_name(self) -> str:
        return self.model_name

class BLIP2CaptionProvider:
    """BLIP2 caption provider - good baseline option."""
    
    def __init__(self, model_name: str = "Salesforce/blip2-opt-2.7b", device: str = "cpu"):
        try:
            from transformers import Blip2Processor, Blip2ForConditionalGeneration
            import torch
        except ImportError as e:
            raise RuntimeError("BLIP2 dependencies not available. Install with 'pip install transformers torch pillow'") from e
        
        self.device = device
        self.model_name = model_name
        
        logger.info(f"Loading BLIP2 model: {model_name}")
        t0 = time.time()
        
        self.processor = Blip2Processor.from_pretrained(model_name)
        self.model = Blip2ForConditionalGeneration.from_pretrained(
            model_name,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32
        ).to(device)
        
        load_time = time.time() - t0
        logger.info(f"BLIP2 model loaded in {load_time:.1f}s")
    
    def generate_caption(self, image: Image.Image, prompt: Optional[str] = None) -> str:
        """Generate caption using BLIP2."""
        import torch
        
        # BLIP2 uses different prompt format
        if prompt is None:
            # Unconditional captioning
            inputs = self.processor(image, return_tensors="pt").to(self.device)
        else:
            # Conditional captioning with text prompt
            inputs = self.processor(image, text=prompt, return_tensors="pt").to(self.device)
        
        with torch.no_grad():
            generated_ids = self.model.generate(**inputs, max_new_tokens=100)
        
        caption = self.processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()
        return caption
    
    def get_model_name(self) -> str:
        return self.model_name

@lru_cache()
def get_caption_provider() -> CaptionProvider:
    """Get the configured caption provider."""
    from .config import get_settings
    
    settings = get_settings()
    provider_name = getattr(settings, 'caption_provider', 'stub').lower()
    device = getattr(settings, 'caption_device', 'cpu').lower()
    
    # In test mode, always use stub
    if settings.run_mode == 'tests':
        return StubCaptionProvider()
    
    # Auto provider selection
    if provider_name in ('auto', 'best'):
        for candidate in ('qwen2.5-vl', 'llava', 'blip2', 'stub'):
            try:
                return _build_caption_provider(candidate, device)
            except Exception as e:
                logger.warning(f"Caption provider {candidate} unavailable: {e}")
                continue
        return StubCaptionProvider()
    
    try:
        return _build_caption_provider(provider_name, device)
    except Exception as e:
        logger.warning(f"Caption provider {provider_name} failed, falling back to stub: {e}")
        return StubCaptionProvider()

def _build_caption_provider(provider: str, device: str) -> CaptionProvider:
    """Build a specific caption provider."""
    provider = provider.lower()
    
    # Check if we should use subprocess (external caption models)
    from .config import get_settings
    settings = get_settings()
    caption_external_dir = getattr(settings, 'caption_external_dir', '') or os.getenv('CAPTION_EXTERNAL_DIR', '')
    
    if caption_external_dir and provider != 'stub':
        from .caption_subprocess import (
            Qwen2VLSubprocessProvider, 
            LlavaNextSubprocessProvider, 
            BLIP2SubprocessProvider,
            CaptionSubprocessProvider
        )
        
        model_name = getattr(settings, 'caption_model', 'auto')
        if model_name == 'auto':
            model_name = 'default'
        
        if provider in ('qwen2vl', 'qwen', 'qwen2-vl', 'qwen2.5-vl'):
            return Qwen2VLSubprocessProvider(caption_external_dir, model_name)
        elif provider in ('llava', 'llava_next', 'llava-next'):
            return LlavaNextSubprocessProvider(caption_external_dir, model_name)
        elif provider == 'blip2':
            return BLIP2SubprocessProvider(caption_external_dir, model_name)
        else:
            # Generic subprocess provider for any other provider
            return CaptionSubprocessProvider(caption_external_dir, provider, model_name)
    
    # Fallback to built-in providers
    if provider == 'stub':
        return StubCaptionProvider()
    elif provider in ('llava', 'llava_next'):
        model_name = os.getenv('LLAVA_MODEL_NAME', 'llava-hf/llava-v1.6-mistral-7b-hf')
        return LlavaNextCaptionProvider(model_name, device)
    elif provider in ('qwen2vl', 'qwen', 'qwen2.5-vl'):
        model_name = os.getenv('QWEN2VL_MODEL_NAME', 'Qwen/Qwen2-VL-7B-Instruct')
        return Qwen2VLCaptionProvider(model_name, device)
    elif provider == 'blip2':
        model_name = os.getenv('BLIP2_MODEL_NAME', 'Salesforce/blip2-opt-2.7b')
        return BLIP2CaptionProvider(model_name, device)
    else:
        raise ValueError(f"Unknown caption provider: {provider}")

# Helper function for Qwen2VL (will be imported from qwen_vl_utils if available)
def process_vision_info(messages):
    """Process vision info for Qwen2VL - simplified version."""
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
