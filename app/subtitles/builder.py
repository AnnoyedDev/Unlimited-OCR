import difflib
from collections import Counter

DEFAULT_TEXT_SIMILARITY_THRESHOLD = 0.85


class AnalyzedFrame:
    def __init__(self, index, timestamp, text, italic=False):
        self.index = index
        self.timestamp = timestamp
        self.text = text
        self.italic = italic


class SubtitleCue:
    def __init__(self, start, end, text, italic=False):
        self.start = start
        self.end = end
        self.text = text
        self.italic = italic


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
    current_italic_votes = []
    current_start = 0.0
    last_timestamp = 0.0

    def close_cue(end_ts):
        nonlocal current_variants, current_italic_votes
        if current_variants:
            italic = sum(current_italic_votes) * 2 > len(current_italic_votes)
            cues.append(
                SubtitleCue(current_start, end_ts, _pick_representative(current_variants), italic=italic)
            )
        current_variants = []
        current_italic_votes = []

    for frame in frames:
        if frame.text is not None:
            normalized = frame.text.strip()

            if not current_variants:
                if normalized:
                    current_start = frame.timestamp
                    current_variants.append(normalized)
                    current_italic_votes.append(frame.italic)
            else:
                anchor = current_variants[0]
                if normalized and _similar(normalized, anchor, text_similarity_threshold):
                    current_variants.append(normalized)
                    current_italic_votes.append(frame.italic)
                else:
                    close_cue(frame.timestamp)
                    if normalized:
                        current_start = frame.timestamp
                        current_variants.append(normalized)
                        current_italic_votes.append(frame.italic)

        last_timestamp = frame.timestamp

    if current_variants:
        end = video_duration if video_duration is not None else last_timestamp
        close_cue(max(end, current_start))

    if min_duration > 0:
        cues = [c for c in cues if (c.end - c.start) >= min_duration]

    return cues
