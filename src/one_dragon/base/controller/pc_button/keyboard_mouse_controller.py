import time

from pynput import keyboard, mouse

from one_dragon.base.controller.pc_button import pc_button_utils
from one_dragon.base.controller.pc_button.pc_button_controller import PcButtonController
from one_dragon.base.controller.pc_button.scan_code_keyboard import ScanCodeKeyboard


class KeyboardMouseController(PcButtonController):

    def __init__(self):
        PcButtonController.__init__(self)
        self.keyboard = keyboard.Controller()
        self.mouse = mouse.Controller()
        self._pressed_keys: set[str] = set()  # 当前按下的键
        self.scan_keyboard: ScanCodeKeyboard = ScanCodeKeyboard()
        self.use_scan_codes: bool = False

    def set_scan_codes(self, enabled: bool) -> None:
        if self.use_scan_codes != enabled:
            self.reset()
            self.use_scan_codes = enabled

    @staticmethod
    def _keys(key: str) -> list[str]:
        return key.split('+') if len(key) > 1 else [key]

    def tap(self, key: str) -> None:
        """
        按一次按键
        :param key: 按键
        :return:
        """
        if pc_button_utils.is_mouse_button(key):
            self.mouse.click(pc_button_utils.get_mouse_button(key))
        elif self.use_scan_codes:
            self.scan_keyboard.press(self._keys(key), self.key_press_time)
        else:
            self.keyboard.tap(pc_button_utils.get_keyboard_button(key))

    def tap_combo(self, keys: list[str]) -> None:
        if self.use_scan_codes and all(not pc_button_utils.is_mouse_button(key) for key in keys):
            self.scan_keyboard.press(keys, self.key_press_time)
        else:
            super().tap_combo(keys)

    def press(self, key: str, press_time: float | None = None) -> None:
        """
        :param key: 按键
        :param press_time: 持续按键时间
        :return:
        """
        is_mouse = pc_button_utils.is_mouse_button(key)
        if self.use_scan_codes and not is_mouse:
            self.scan_keyboard.press(self._keys(key), press_time)
            return
        real_key = pc_button_utils.get_mouse_button(key) if is_mouse else pc_button_utils.get_keyboard_button(key)
        if is_mouse:
            self.mouse.press(real_key)
        else:
            self.keyboard.press(real_key)
        if press_time is None:
            self._pressed_keys.add(key)

        if press_time is not None:
            time.sleep(press_time)

            if is_mouse:
                self.mouse.release(real_key)
            else:
                self.keyboard.release(real_key)

    def release(self, key: str) -> None:
        if self.use_scan_codes and not pc_button_utils.is_mouse_button(key):
            self.scan_keyboard.release(self._keys(key))
            return
        if key not in self._pressed_keys:
            return
        self._pressed_keys.discard(key)
        is_mouse = pc_button_utils.is_mouse_button(key)
        if is_mouse:
            self.mouse.release(pc_button_utils.get_mouse_button(key))
        else:
            self.keyboard.release(pc_button_utils.get_keyboard_button(key))

    def reset(self) -> None:
        self.scan_keyboard.reset()
        for key in list(self._pressed_keys):
            self.release(key)


if __name__ == '__main__':
    _c = KeyboardMouseController()
    t1 = time.time()
    _c.press('a')
    _c.release('a')
    print('%.4f' % (time.time() - t1))
