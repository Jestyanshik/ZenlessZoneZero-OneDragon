import ctypes
import time
from ctypes import wintypes
from threading import RLock

from one_dragon.base.controller.pc_button.pc_button_utils import get_keyboard_button
from one_dragon.utils.log_utils import log


class KeyboardInput(ctypes.Structure):
    _fields_ = [
        ('vk', wintypes.WORD),
        ('scan', wintypes.WORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('extra_info', ctypes.c_size_t),
    ]


class MouseInput(ctypes.Structure):
    _fields_ = [
        ('x', wintypes.LONG),
        ('y', wintypes.LONG),
        ('data', wintypes.DWORD),
        ('flags', wintypes.DWORD),
        ('time', wintypes.DWORD),
        ('extra_info', ctypes.c_size_t),
    ]


class InputData(ctypes.Union):
    # SendInput 的联合体按最大的成员对齐。
    _fields_ = [('keyboard', KeyboardInput), ('mouse', MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [('type', wintypes.DWORD), ('data', InputData)]


_user32 = ctypes.WinDLL('user32', use_last_error=True)
_map_virtual_key = _user32.MapVirtualKeyW
_map_virtual_key.argtypes = (wintypes.UINT, wintypes.UINT)
_map_virtual_key.restype = wintypes.UINT
_send_input = _user32.SendInput
_send_input.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
_send_input.restype = wintypes.UINT


_PHYSICAL_KEYS: dict[str, int] = {
    **dict(zip('1234567890-=', range(0x02, 0x0E), strict=True)),
    **dict(zip('qwertyuiop[]', range(0x10, 0x1C), strict=True)),
    **dict(zip("asdfghjkl;'`", range(0x1E, 0x2A), strict=True)),
    **dict(zip('\\zxcvbnm,./', range(0x2B, 0x36), strict=True)),
    ' ': 0x39,
}
_SHIFTED_KEYS = dict(zip('!@#$%^&*()_+{}:"~|<>?', '1234567890-=[];\'`\\,./', strict=True))
_EXTENDED_VKS = {
    0x21, 0x22, 0x23, 0x24, 0x25, 0x26, 0x27, 0x28,  # 导航键
    0x2C, 0x2D, 0x2E, 0x5B, 0x5C, 0x5D, 0x6F, 0x90, 0xA3, 0xA5,
}


def _scan_code(key: str) -> int:
    key = key.lower()
    physical = _PHYSICAL_KEYS.get(_SHIFTED_KEYS.get(key, key))
    if physical is not None:
        return physical
    button = get_keyboard_button(key)
    vk = getattr(getattr(button, 'value', button), 'vk', None)
    if not vk or not 0 < vk <= 0xFF:
        raise ValueError(f'Unsupported physical key: {key!r}')
    scan = _map_virtual_key(vk, 4)  # MAPVK_VK_TO_VSC_EX
    if not scan or scan >> 8 not in (0, 0xE0):
        raise ValueError(f'Unsupported scan code for {key!r}: {scan:#x}')
    if scan <= 0xFF and vk in _EXTENDED_VKS:
        scan |= 0xE000
    return scan


def _send(scan: int, flags: int, action: str) -> None:
    event = Input(1, InputData(keyboard=KeyboardInput(0, scan, flags, 0, 0)))
    ctypes.set_last_error(0)
    if _send_input(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
        raise OSError(ctypes.get_last_error(), f'SendInput {action} accepted 0/1 events')


def _send_key(scan: int, *, up: bool) -> None:
    flags = 0x0008  # KEYEVENTF_SCANCODE
    if scan >> 8 == 0xE0:
        flags |= 0x0001  # KEYEVENTF_EXTENDEDKEY

    _send(scan & 0xFF, flags | (0x0002 if up else 0), 'keyup' if up else 'keydown')


class ScanCodeKeyboard:
    """管理按下的物理按键，停止时释放。"""

    def __init__(self) -> None:
        self._held: dict[int, object] = {}
        self._lock = RLock()
        self._suspended: bool = False

    def press(self, keys: list[str], duration: float | None) -> None:
        codes = [_scan_code(key) for key in keys]
        token = object()
        completed = False
        try:
            with self._lock:
                if self._suspended:
                    raise InterruptedError('Scan-code input is paused or stopped')
                for code in codes:
                    if code not in self._held:
                        _send_key(code, up=False)
                        self._held[code] = token
            if duration is not None:
                time.sleep(duration)
            completed = True
        finally:
            if duration is not None or not completed:
                self._release(codes, token)

    def release(self, keys: list[str]) -> None:
        self._release([_scan_code(key) for key in keys])

    def _release(self, codes: list[int], token: object | None = None) -> None:
        error: OSError | None = None
        with self._lock:
            for code in reversed(codes):
                if code not in self._held or (token is not None and self._held[code] is not token):
                    continue
                try:
                    _send_key(code, up=True)
                except OSError as exc:
                    log.warning('Failed to release scan code %#x: %s', code, exc)
                    error = exc
                else:
                    del self._held[code]
        if error is not None:
            raise error

    def reset(self) -> None:
        with self._lock:
            self._release(list(self._held))

    def suspend(self) -> None:
        with self._lock:
            self._suspended = True
            self.reset()

    def resume(self) -> None:
        with self._lock:
            self._suspended = False
