class ImageEvent:
    def __init__(self, index, start, end, image):
        self.index = index
        self.start = start
        self.end = end
        self.image = image


class ImageSetReader:
    def __init__(self, path, events):
        self.path = path
        self.events = events
        self.frame_count = len(events)
        self.width = max((e.image.shape[1] for e in events), default=0)
        self.height = max((e.image.shape[0] for e in events), default=0)
        self.duration = events[-1].end if events else 0.0

    def get_event(self, index):
        if 0 <= index < len(self.events):
            return self.events[index]
        return None

    def iter_events(self):
        yield from self.events

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
