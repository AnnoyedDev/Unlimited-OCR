from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
MODEL_DIR = ROOT_DIR / "models" / "Unlimited-OCR"

DEFAULT_OCR_PROMPT = "<image>Free OCR. "

DEFAULT_MAX_NEW_TOKENS = 256
DEFAULT_NO_REPEAT_NGRAM_SIZE = 20
DEFAULT_NGRAM_WINDOW = 64

DEFAULT_CROP_MIN_TILES = 1
DEFAULT_CROP_MAX_TILES = 6
