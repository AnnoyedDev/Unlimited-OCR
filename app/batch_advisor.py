import torch


def detect_capacity(device_info):
    if device_info.is_gpu:
        free_bytes, total_bytes = torch.cuda.mem_get_info(device_info.device)
        return free_bytes, total_bytes
    import psutil

    vm = psutil.virtual_memory()
    return vm.available, vm.total


def start_measurement(device_info):
    if device_info.is_gpu:
        torch.cuda.reset_peak_memory_stats(device_info.device)
        return None
    import psutil

    return psutil.Process().memory_info().rss


def finish_measurement(device_info, baseline):
    if device_info.is_gpu:
        return torch.cuda.max_memory_allocated(device_info.device)
    import psutil

    rss = psutil.Process().memory_info().rss
    return max(0, rss - baseline)
