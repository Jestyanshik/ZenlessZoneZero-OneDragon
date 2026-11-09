from __future__ import annotations

import ctypes
import gettext
from pathlib import Path
from string import Formatter
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest
import polib

from one_dragon.base.controller.pc_button import scan_code_keyboard as scan
from one_dragon.base.controller.pc_button.keyboard_mouse_controller import KeyboardMouseController
from one_dragon.base.operation.operation_round_result import OperationRoundResult, OperationRoundResultEnum
from one_dragon.utils import i18_utils
from zzz_od.application import npc_interaction
from zzz_od.application.hou_hou_bakery.hou_hou_bakery_app import HouHouBakeryApp
from zzz_od.application.random_play.random_play_app import RandomPlayApp
from zzz_od.application.random_play.random_play_config import RandomPlayTransportPoint
from zzz_od.application.scratch_card.scratch_card_app import ScratchCardApp

SUCCESS = OperationRoundResult(OperationRoundResultEnum.SUCCESS)
RETRY = OperationRoundResult(OperationRoundResultEnum.RETRY)


def test_windows_input_structure_and_physical_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    events = []

    def send(count: int, pointer: object, size: int) -> int:
        assert count == 1 and size == (40 if ctypes.sizeof(ctypes.c_void_p) == 8 else 28)
        key = ctypes.cast(pointer, ctypes.POINTER(scan.Input)).contents.data.keyboard
        events.append((key.vk, key.scan, key.flags))
        return 1

    monkeypatch.setattr(scan, '_send_input', send)
    monkeypatch.setattr(scan.time, 'sleep', Mock())
    keyboard = scan.ScanCodeKeyboard()
    for key in ('w', 'a', 's', 'd', 'F', 'e', 'q', 'r', 'esc', 'space', 'shift', 'tab', 'right'):
        keyboard.press([key], 0.02)
    assert [entry[1] for entry in events[::2]] == [
        0x11, 0x1E, 0x1F, 0x20, 0x21, 0x12, 0x10, 0x13, 0x01, 0x39, 0x2A, 0x0F, 0x4D,
    ]
    assert all(vk == 0 for vk, _, _ in events)
    assert events[-2:] == [(0, 0x4D, 9), (0, 0x4D, 11)]


@pytest.mark.parametrize('layout', ['ru_RU', 'en_US'])
def test_printable_bindings_do_not_use_layout_mapping(
    monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    mapper = Mock(side_effect=AssertionError(f'Layout-dependent lookup in {layout}'))
    monkeypatch.setattr(scan, '_map_virtual_key', mapper)
    assert [scan._scan_code(key) for key in ('w', 'a', 's', 'd', 'f')] == [17, 30, 31, 32, 33]
    mapper.assert_not_called()


def test_chords_and_stop_release_held_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = Mock()
    monkeypatch.setattr(scan, '_send_key', sender)
    keyboard = scan.ScanCodeKeyboard()
    keyboard.press(['w', 'd'], None)
    keyboard.press(['shift', 'f'], None)
    keyboard.suspend()
    assert sender.call_args_list == [
        call(17, up=False), call(32, up=False), call(42, up=False), call(33, up=False),
        call(33, up=True), call(42, up=True), call(32, up=True), call(17, up=True),
    ]
    with pytest.raises(InterruptedError):
        keyboard.press(['w'], None)
    keyboard.resume()
    keyboard.press(['a'], None)
    keyboard.release(['a'])
    assert sender.call_args_list[-2:] == [call(30, up=False), call(30, up=True)]


def test_windows_rejection_releases_earlier_chord_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = Mock(side_effect=[1, 0, 1])
    monkeypatch.setattr(scan, '_send_input', sender)
    keyboard = scan.ScanCodeKeyboard()
    with pytest.raises(OSError, match='keydown accepted 0/1'):
        keyboard.press(['w', 'd'], None)
    keyboard.reset()
    assert sender.call_count == 3


def test_keyup_failure_retains_key_for_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = Mock(side_effect=[1, 0, 1])
    monkeypatch.setattr(scan, '_send_input', sender)
    monkeypatch.setattr(scan.time, 'sleep', Mock())
    keyboard = scan.ScanCodeKeyboard()
    with pytest.raises(OSError, match='keyup accepted 0/1'):
        keyboard.press(['f'], 0.02)
    keyboard.reset()
    assert sender.call_count == 3


def test_timed_tap_does_not_release_existing_hold(monkeypatch: pytest.MonkeyPatch) -> None:
    sender = Mock()
    monkeypatch.setattr(scan, '_send_key', sender)
    monkeypatch.setattr(scan.time, 'sleep', Mock())
    keyboard = scan.ScanCodeKeyboard()
    keyboard.press(['w'], None)
    keyboard.press(['w', 'd'], 0.02)
    assert sender.call_args_list == [call(17, up=False), call(32, up=False), call(32, up=True)]
    keyboard.release(['w'])
    assert sender.call_args == call(17, up=True)


def test_existing_keyboard_and_mouse_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    ctrl = KeyboardMouseController()
    ctrl.keyboard = Mock()
    ctrl.mouse = Mock()
    monkeypatch.setattr(scan, '_send_key', Mock())
    monkeypatch.setattr(scan.time, 'sleep', Mock())
    ctrl.tap('f')
    ctrl.keyboard.tap.assert_called_once()
    ctrl.set_scan_codes(True)
    ctrl.press('shift+w', press_time=0.1)
    ctrl.tap('mouse_left')
    assert ctrl.keyboard.tap.call_count == 1
    ctrl.mouse.click.assert_called_once()
    assert scan._send_key.call_args_list[-2:] == [call(17, up=True), call(42, up=True)]


def make_app(app_type: type) -> object:
    app = object.__new__(app_type)
    app.app_id = app_type.__name__
    app.last_screenshot = object()
    app.node_retry_times = 0
    app.node_max_retry_times = 10
    app.ctx = SimpleNamespace(controller=Mock(standard_width=1920, standard_height=1080), screen_loader=Mock())
    app._after_round_wait = Mock()
    app.round_by_find_area = Mock(return_value=RETRY)
    app.round_by_ocr = Mock(return_value=RETRY)
    app.round_by_ocr_and_click = Mock(return_value=RETRY)
    app.round_by_find_and_click_area = Mock(return_value=RETRY)
    app._box_attempts = 0
    app.claimed = False
    return app


@pytest.mark.parametrize('app_type', [ScratchCardApp, HouHouBakeryApp])
def test_daily_tasks_require_an_observed_screen(
    monkeypatch: pytest.MonkeyPatch, app_type: type
) -> None:
    app = make_app(app_type)
    monkeypatch.setattr(npc_interaction.time, 'sleep', Mock())
    for attempt in range(3):
        app.node_retry_times = attempt
        assert app.move_and_interact().result is OperationRoundResultEnum.RETRY
    app.node_retry_times = 3
    assert app.move_and_interact().is_fail
    assert app.ctx.controller.press_npc_interact.call_count == 3
    app.round_by_find_area.return_value = SUCCESS
    app.round_by_ocr.return_value = SUCCESS
    assert app.move_and_interact().is_success
    assert app.ctx.controller.press_npc_interact.call_count == 3
    assert app.ctx.controller.move_w.call_count == int(app_type is ScratchCardApp)


def test_scratch_card_checks_title_before_click() -> None:
    app = make_app(ScratchCardApp)
    assert app.click_scratch_card().status == '刮刮卡界面未继续'
    assert app.round_by_find_and_click_area.call_args.args[2] == '嗷呜标题'


def test_bakery_bounds_box_actions() -> None:
    app = make_app(HouHouBakeryApp)
    app.round_by_ocr.side_effect = lambda _, word, **kw: SUCCESS if word == '查看今天' else RETRY
    for _ in range(3):
        assert app.collect().result is OperationRoundResultEnum.WAIT
    assert app.collect().is_fail
    assert app.ctx.controller.click.call_count == 2
    app.ctx.controller.press_npc_interact.assert_called_once()


@pytest.mark.parametrize('point', list(RandomPlayTransportPoint))
def test_video_store_waits_for_scene_then_business(
    monkeypatch: pytest.MonkeyPatch, point: RandomPlayTransportPoint
) -> None:
    app = make_app(RandomPlayApp)
    app.config = SimpleNamespace(transport_point=point.value.value)
    monkeypatch.setattr(npc_interaction.time, 'sleep', Mock())
    assert app.open_interaction().result is OperationRoundResultEnum.RETRY
    app.ctx.controller.press_npc_interact.assert_called_once()
    app.node_retry_times = 1
    if point is RandomPlayTransportPoint.POINT_1:
        app.round_by_find_area.return_value = SUCCESS
    else:
        word = '查看经营状况' if point is RandomPlayTransportPoint.POINT_2 else '层层安检'
        app.round_by_ocr.side_effect = lambda _, target, **kw: SUCCESS if target == word else RETRY
    assert app.open_interaction().is_success
    assert app.ctx.controller.press_npc_interact.call_count == 1
    if point is not RandomPlayTransportPoint.POINT_1:
        app.round_by_click_area = Mock(return_value=SUCCESS)
        assert app.handle_interaction_dialog().result is OperationRoundResultEnum.RETRY
        assert app.round_by_click_area.call_count == int(point is RandomPlayTransportPoint.POINT_3)
        app.round_by_find_area.return_value = SUCCESS
    assert app.handle_interaction_dialog().is_success


def test_video_store_has_bounded_failure() -> None:
    app = make_app(RandomPlayApp)
    app.node_retry_times = 3
    app.config = SimpleNamespace(transport_point=RandomPlayTransportPoint.POINT_1.value.value)
    assert app.open_interaction().is_fail
    app.ctx.controller.press_npc_interact.assert_not_called()
    app.node_retry_times = 10
    assert app.handle_interaction_dialog().is_fail
    assert app.wait_run().is_fail


def test_russian_catalog_and_game_domain() -> None:
    assert i18_utils.gt('设置', lang='ru') == 'Настройки'
    assert i18_utils.gt('键盘控制方式', lang='ru') == 'Способ управления с клавиатуры'
    assert i18_utils.gt('查看经营状况', model='game', lang='ru') == '查看经营状况'


def test_gettext_catalog_is_complete_and_matches_binary() -> None:
    root = Path(__file__).resolve().parents[2] / 'assets/text'
    catalog = polib.pofile(root / 'ui/ru.po')
    keys = {entry.msgid for entry in catalog}
    assert len(catalog) == len(keys) and len(keys) >= 1698
    with (root / 'output/ru/LC_MESSAGES/ui.mo').open('rb') as stream:
        compiled = gettext.GNUTranslations(stream)
    for entry in catalog:
        assert entry.msgstr and compiled.gettext(entry.msgid) == entry.msgstr
        if '{' in entry.msgid:
            source = sorted(field for _, field, _, _ in Formatter().parse(entry.msgid) if field is not None)
            target = sorted(field for _, field, _, _ in Formatter().parse(entry.msgstr) if field is not None)
            assert source == target


def test_snapshot_does_not_sync_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from one_dragon.envs import git_service
    from one_dragon.launcher import runtime_launcher

    (tmp_path / 'fork-build.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(runtime_launcher.sys, 'executable', str(tmp_path / 'launcher.exe'))
    monkeypatch.setattr(git_service.os_utils, 'get_work_dir', lambda: str(tmp_path))
    # These methods return before reaching any repository or environment services.
    runtime_launcher.RuntimeLauncher._sync_code(None)
    status, _ = git_service.GitService.fetch_latest_code(None)
    assert status is git_service.GitSyncStatus.LOCAL_CHANGES
    git_service.GitService.update_remote(None)
    assert not git_service.GitService.reset_to_commit(None, 'unused')[0]
