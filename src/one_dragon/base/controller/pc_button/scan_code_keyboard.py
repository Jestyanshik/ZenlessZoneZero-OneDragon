import ctypes
import time
from ctypes import wintypes

from one_dragon.base.controller.pc_button.pc_button_utils import get_keyboard_button


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
_vk_key_scan = _user32.VkKeyScanW
_vk_key_scan.argtypes = (wintypes.WCHAR,)
_vk_key_scan.restype = ctypes.c_short
_send_input = _user32.SendInput
_send_input.argtypes = (wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int)
_send_input.restype = wintypes.UINT


def _virtual_key(key: str) -> int:
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    button = get_keyboard_button(key)
    vk = getattr(getattr(button, 'value', button), 'vk', None)
    if vk is None and len(key) == 1:
        vk = _vk_key_scan(key)
    if not vk or not 0 < vk <= 0xFF:
        raise ValueError(f'Unsupported single key: {key!r}')
    return vk


def _send(scan: int, flags: int, action: str) -> None:
    event = Input(1, InputData(keyboard=KeyboardInput(0, scan, flags, 0, 0)))
    ctypes.set_last_error(0)
    if _send_input(1, ctypes.byref(event), ctypes.sizeof(Input)) != 1:
        raise OSError(ctypes.get_last_error(), f'SendInput {action} accepted 0/1 events')


def press_scan_code(key: str, duration: float) -> int:
    """用扫描码按住单键，返回 Windows 接受的扫描码。"""
    scan = _map_virtual_key(_virtual_key(key), 4)  # MAPVK_VK_TO_VSC_EX
    if not scan or scan >> 8 not in (0, 0xE0):
        raise ValueError(f'Unsupported scan code for {key!r}: {scan:#x}')
    flags = 0x0008  # KEYEVENTF_SCANCODE
    if scan >> 8 == 0xE0:
        flags |= 0x0001  # KEYEVENTF_EXTENDEDKEY

    _send(scan & 0xFF, flags, 'keydown')
    try:
        time.sleep(duration)
    finally:
        _send(scan & 0xFF, flags | 0x0002, 'keyup')
    return scan
