import difflib
from collections import Counter

DEFAULT_TEXT_SIMILARITY_THRESHOLD = 0.85


class AnalyzedFrame:
    def __init__(self, index, timestamp, text):
        self.index = index
        self.timestamp = timestamp
        self.text = text


class SubtitleCue:
    def __init__(self, start, end, text):
        self.start = start
        self.end = end
        self.text = text


def _similar(a, b, threshold):
    if not a or not b:
        return False
    return difflib.SequenceMatcher(None, a, b).ratio() >= threshold


def _pick_representative(variants):
    counts = Counter(variants)
    best_count = max(counts.values())
    tied = [text for text, count in counts.items() if count == best_count]
    return max(tied, key=len)


def build_cues(
    frames,
    video_duration=None,
    min_duration=0.0,
    text_similarity_threshold=DEFAULT_TEXT_SIMILARITY_THRESHOLD,
):
    frames = sorted(frames, key=lambda f: f.index)

    cues = []
    current_variants = []
    current_start = 0.0
    last_timestamp = 0.0

    def close_cue(end_ts):
        nonlocal current_variants
        if current_variants:
            cues.append(SubtitleCue(current_start, end_ts, _pick_representative(current_variants)))
        current_variants = []

    for frame in frames:
        if frame.text is not None:
            normalized = frame.text.strip()

            if not current_variants:
                if normalized:
                    current_start = frame.timestamp
                    current_variants.append(normalized)
            else:
                anchor = current_variants[0]
                if normalized and _similar(normalized, anchor, text_similarity_threshold):
                    current_variants.append(normalized)
                else:
                    close_cue(frame.timestamp)
                    if normalized:
                        current_start = frame.timestamp
                        current_variants.append(normalized)

        last_timestamp = frame.timestamp

    if current_variants:
        end = video_duration if video_duration is not None else last_timestamp
        close_cue(max(end, current_start))

    if min_duration > 0:
        cues = [c for c in cues if (c.end - c.start) >= min_duration]

    return cues
