import math
import re
import sys

import cv2
import numpy as np
import torch
from PIL import Image, ImageOps
from transformers import AutoModel, AutoTokenizer

from .config import (
    DEFAULT_MAX_NEW_TOKENS,
    DEFAULT_NGRAM_WINDOW,
    DEFAULT_NO_REPEAT_NGRAM_SIZE,
    DEFAULT_OCR_PROMPT,
    MODEL_DIR,
)
from .device import detect_device

def bgr_to_pil(frame):
    return Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))


_DET_RE = re.compile(r"<\|det\|>([^<\s]+)(?:\s*\[[^\]]*\])?\s*<\|/det\|>(.*)", re.DOTALL)


def strip_det_markup(text):
    blocks = []
    for line in text.splitlines():
        line = line.rstrip()
        if not line:
            continue
        m = _DET_RE.match(line)
        if m:
            category, content = m.group(1).strip(), m.group(2).strip()
            if category == "image":
                continue
            if content:
                blocks.append(content)
        else:
            blocks.append(line)
    return "\n".join(blocks).strip()


IMAGE_TOKEN = "<image>"
IMAGE_TOKEN_ID = 128815
PATCH_SIZE = 16
DOWNSAMPLE_RATIO = 4
STOP_STR = "<｜end▁of▁sentence｜>"


class OcrEngine:
    def __init__(
        self,
        model,
        tokenizer,
        device_info,
        format_messages,
        text_encode,
        dynamic_preprocess,
        image_transform_cls,
        ngram_processor_cls,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.device_info = device_info
        self.format_messages = format_messages
        self.text_encode = text_encode
        self.dynamic_preprocess = dynamic_preprocess
        self.image_transform_cls = image_transform_cls
        self.ngram_processor_cls = ngram_processor_cls

    @classmethod
    def load(cls, device_info=None, model_dir=MODEL_DIR):
        device_info = device_info or detect_device()

        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
        model = AutoModel.from_pretrained(
            str(model_dir),
            trust_remote_code=True,
            use_safetensors=True,
            torch_dtype=device_info.dtype,
        )
        model = model.eval().to(device_info.device)

        mod = sys.modules[type(model).__module__]

        return cls(
            model=model,
            tokenizer=tokenizer,
            device_info=device_info,
            format_messages=mod.format_messages,
            text_encode=mod.text_encode,
            dynamic_preprocess=mod.dynamic_preprocess,
            image_transform_cls=mod.BasicImageTransform,
            ngram_processor_cls=mod.SlidingWindowNoRepeatNgramProcessor,
        )

    def _prepare_sample(self, image, prompt, base_size, image_size, crop_mode):
        model_dtype = self.device_info.dtype
        image = image.convert("RGB")

        conversation = [
            {"role": "<|User|>", "content": prompt, "images": [image]},
            {"role": "<|Assistant|>", "content": ""},
        ]
        formatted_prompt = self.format_messages(
            conversations=conversation, sft_format="plain", system_prompt=""
        )

        image_transform = self.image_transform_cls(mean=(0.5, 0.5, 0.5), std=(0.5, 0.5, 0.5), normalize=True)
        text_splits = formatted_prompt.split(IMAGE_TOKEN)

        images_list, images_crop_list, images_seq_mask = [], [], []
        tokenized_str = []
        images_spatial_crop = []

        for text_sep, img in zip(text_splits, [image]):
            tokenized_sep = self.text_encode(self.tokenizer, text_sep, bos=False, eos=False)
            tokenized_str += tokenized_sep
            images_seq_mask += [False] * len(tokenized_sep)

            if crop_mode and not (img.size[0] <= 640 and img.size[1] <= 640):
                images_crop_raw, crop_ratio = self.dynamic_preprocess(img)
            else:
                images_crop_raw, crop_ratio = [], [1, 1]

            global_view = ImageOps.pad(
                img, (base_size, base_size), color=tuple(int(x * 255) for x in image_transform.mean)
            )
            images_list.append(image_transform(global_view).to(model_dtype))

            width_crop_num, height_crop_num = crop_ratio
            images_spatial_crop.append([width_crop_num, height_crop_num])

            if width_crop_num > 1 or height_crop_num > 1:
                for crop in images_crop_raw:
                    images_crop_list.append(image_transform(crop).to(model_dtype))

            num_queries = math.ceil((image_size // PATCH_SIZE) / DOWNSAMPLE_RATIO)
            num_queries_base = math.ceil((base_size // PATCH_SIZE) / DOWNSAMPLE_RATIO)

            tokenized_image = ([IMAGE_TOKEN_ID] * num_queries_base + [IMAGE_TOKEN_ID]) * num_queries_base
            tokenized_image += [IMAGE_TOKEN_ID]
            if width_crop_num > 1 or height_crop_num > 1:
                tokenized_image += ([IMAGE_TOKEN_ID] * (num_queries * width_crop_num) + [IMAGE_TOKEN_ID]) * (
                    num_queries * height_crop_num
                )
            tokenized_str += tokenized_image
            images_seq_mask += [True] * len(tokenized_image)

        tokenized_sep = self.text_encode(self.tokenizer, text_splits[-1], bos=False, eos=False)
        tokenized_str += tokenized_sep
        images_seq_mask += [False] * len(tokenized_sep)

        tokenized_str = [0] + tokenized_str
        images_seq_mask = [False] + images_seq_mask

        images_ori = torch.stack(images_list, dim=0)
        if images_crop_list:
            images_crop = torch.stack(images_crop_list, dim=0)
        else:
            images_crop = torch.zeros((1, 3, base_size, base_size), dtype=model_dtype)

        return {
            "tokenized_str": tokenized_str,
            "images_seq_mask": images_seq_mask,
            "images_ori": images_ori,
            "images_crop": images_crop,
            "spatial_crop": images_spatial_crop[0],
        }

    @torch.no_grad()
    def ocr_images_batch(
        self,
        images,
        prompt=DEFAULT_OCR_PROMPT,
        base_size=1024,
        image_size=640,
        crop_mode=True,
        max_new_tokens=DEFAULT_MAX_NEW_TOKENS,
        no_repeat_ngram_size=DEFAULT_NO_REPEAT_NGRAM_SIZE,
        ngram_window=DEFAULT_NGRAM_WINDOW,
        temperature=0.0,
    ):
        if not images:
            return []

        device = self.device_info.device
        model_dtype = self.device_info.dtype

        samples = [self._prepare_sample(img, prompt, base_size, image_size, crop_mode) for img in images]

        pad_id = self.tokenizer.pad_token_id
        if pad_id is None:
            pad_id = self.tokenizer.eos_token_id

        max_len = max(len(s["tokenized_str"]) for s in samples)
        input_ids_rows, attn_rows, seq_mask_rows = [], [], []
        for s in samples:
            pad_len = max_len - len(s["tokenized_str"])
            input_ids_rows.append([pad_id] * pad_len + s["tokenized_str"])
            attn_rows.append([0] * pad_len + [1] * len(s["tokenized_str"]))
            seq_mask_rows.append([False] * pad_len + s["images_seq_mask"])

        input_ids = torch.LongTensor(input_ids_rows).to(device)
        attention_mask = torch.LongTensor(attn_rows).to(device)
        images_seq_mask_t = torch.tensor(seq_mask_rows, dtype=torch.bool).to(device)

        images_batch = [(s["images_crop"].to(device), s["images_ori"].to(device)) for s in samples]
        images_spatial_crop_t = torch.tensor([s["spatial_crop"] for s in samples], dtype=torch.long)

        gen_kwargs = dict(
            input_ids=input_ids,
            attention_mask=attention_mask,
            images=images_batch,
            images_seq_mask=images_seq_mask_t,
            images_spatial_crop=images_spatial_crop_t,
            do_sample=temperature > 0,
            temperature=temperature if temperature > 0 else None,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=pad_id,
            max_new_tokens=max_new_tokens,
            use_cache=True,
        )
        if no_repeat_ngram_size > 0 and ngram_window > 0:
            gen_kwargs["logits_processor"] = [
                self.ngram_processor_cls(no_repeat_ngram_size, ngram_window)
            ]
        elif no_repeat_ngram_size > 0:
            gen_kwargs["no_repeat_ngram_size"] = no_repeat_ngram_size

        orig_sliding_window = getattr(self.model.config, "sliding_window_size", None) or getattr(
            self.model.config, "sliding_window", None
        )
        self.model.config._ring_window = orig_sliding_window
        self.model.config.sliding_window = None
        try:
            with torch.autocast(device_type=device.type, dtype=model_dtype, enabled=self.device_info.is_gpu):
                output_ids = self.model.generate(**gen_kwargs)
        finally:
            self.model.config.sliding_window = orig_sliding_window

        eos_id = self.tokenizer.eos_token_id
        results = []
        for i in range(len(images)):
            row = output_ids[i, input_ids.shape[1]:]
            eos_positions = (row == eos_id).nonzero(as_tuple=True)[0]
            if len(eos_positions) > 0:
                row = row[: eos_positions[0]]
            outputs = self.tokenizer.decode(row, skip_special_tokens=False)
            if outputs.endswith(STOP_STR):
                outputs = outputs[: -len(STOP_STR)]
            results.append(strip_det_markup(outputs.strip()))
        return results

    def ocr_image(self, image, **kwargs):
        return self.ocr_images_batch([image], **kwargs)[0]
