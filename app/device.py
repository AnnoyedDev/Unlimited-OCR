import torch


class DeviceInfo:
    def __init__(self, device, dtype, backend, name):
        self.device = device
        self.dtype = dtype
        self.backend = backend
        self.name = name

    @property
    def is_gpu(self):
        return self.backend != "cpu"

    def __str__(self):
        return f"{self.backend.upper()} · {self.name} · {self.dtype}".replace(
            "torch.", ""
        )


def detect_device():
    if torch.cuda.is_available():
        is_rocm = getattr(torch.version, "hip", None) is not None
        backend = "rocm" if is_rocm else "cuda"
        name = torch.cuda.get_device_name(0)
        return DeviceInfo(torch.device("cuda"), torch.bfloat16, backend, name)

    return DeviceInfo(torch.device("cpu"), torch.float32, "cpu", "CPU")
