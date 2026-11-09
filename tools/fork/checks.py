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
from one_dragon.base.geometry.point import Point
from one_dragon.base.matcher.match_result import MatchResult
from one_dragon.base.operation.operation_round_result import OperationRoundResult, OperationRoundResultEnum
from one_dragon.utils import i18_utils
from zzz_od.application import npc_interaction
from zzz_od.application.hou_hou_bakery.hou_hou_bakery_app import HouHouBakeryApp
from zzz_od.application.random_play.random_play_app import RandomPlayApp
from zzz_od.application.random_play.random_play_config import RANDOM_AGENT_NAME, RandomPlayTransportPoint
from zzz_od.application.scratch_card.scratch_card_app import ScratchCardApp
from zzz_od.controller.zzz_pc_controller import ZPcController
from zzz_od.game_data.agent import AgentEnum

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


@pytest.mark.parametrize('scan_codes', [False, True])
def test_npc_controller_checks_focus_and_uses_configured_backend(scan_codes: bool) -> None:
    ctrl = object.__new__(ZPcController)
    ctrl.action_keys = {'interact': 'f'}
    ctrl.background_mode = False
    ctrl.game_win = SimpleNamespace(is_win_active=False)
    ctrl.btn_controller = ctrl.keyboard_controller = Mock(use_scan_codes=scan_codes)
    assert not ctrl.press_npc_interact()
    ctrl.keyboard_controller.press.assert_not_called()
    ctrl.game_win.is_win_active = True
    assert ctrl.press_npc_interact()
    ctrl.keyboard_controller.press.assert_called_once_with('f', 0.2)


def test_random_promoter_waits_for_fresh_confirmation_and_business_screen() -> None:
    app = make_app(RandomPlayApp)
    app.config = SimpleNamespace(agent_name_1=RANDOM_AGENT_NAME, agent_name_2=RANDOM_AGENT_NAME)
    app.run_record = Mock()
    app.run_record.get_current_dt.return_value = '20261108'
    app._promoter_confirmation_sent = False
    app.round_by_click_area = Mock(return_value=SUCCESS)
    app.round_by_find_and_click_area.return_value = SUCCESS
    visible = {'选择宣传员'}
    app.round_by_find_area.side_effect = lambda _, screen, area: SUCCESS if area in visible else RETRY
    assert app.choose_promoter().is_success
    app.round_by_click_area.assert_called_once_with('影像店营业', '宣传员-1', retry_wait=1)
    app.round_by_find_and_click_area.assert_not_called()
    assert app.confirm_promoter().result is OperationRoundResultEnum.RETRY
    assert app.confirm_promoter().result is OperationRoundResultEnum.RETRY
    app.round_by_find_and_click_area.assert_called_once_with(app.last_screenshot, '影像店营业', '确认')
    visible.clear()
    assert app.confirm_promoter().result is OperationRoundResultEnum.RETRY
    visible.add('经营状况')
    assert app.confirm_promoter().is_success


def test_named_promoters_use_original_names_and_report_unavailable_agents() -> None:
    app = make_app(RandomPlayApp)
    p, v = AgentEnum.PROMEIA.value, AgentEnum.VELINA.value
    assert (p.agent_name, v.agent_name) == ('普罗米娅', '维琳娜')
    assert i18_utils.gt(p.agent_name, lang='ru') == 'Промея'
    assert i18_utils.gt(v.agent_name, lang='ru') == 'Велина Эйргид'
    app.config = SimpleNamespace(agent_name_1=p.agent_name, agent_name_2=v.agent_name)
    app.run_record = Mock()
    app.run_record.get_current_dt.return_value = '20261108'
    app._store_area_visible = lambda name: name == '选择宣传员'
    app._try_select_agent = Mock(side_effect=[False, True])
    app.round_by_click_area = Mock()
    assert app.choose_promoter().status == v.agent_name
    assert [args.args[0] for args in app._try_select_agent.call_args_list] == [p.agent_name, v.agent_name]
    app._try_select_agent.side_effect = None
    app._try_select_agent.return_value = False
    app.node_retry_times = 2
    assert app.choose_promoter().is_fail
    app.round_by_click_area.assert_not_called()


def test_velina_uses_second_avatar_and_checks_click(monkeypatch: pytest.MonkeyPatch) -> None:
    app = make_app(RandomPlayApp)
    area = SimpleNamespace(rect=object(), left_top=Point(20, 40))
    app.ctx.screen_loader.get_area.return_value = area
    app.ctx.tm = Mock()
    app.ctx.tm.match_one_by_feature.side_effect = [None, MatchResult(1, 4, 6, 8, 10)]
    app.ctx.controller.click.return_value = False
    monkeypatch.setattr('zzz_od.application.random_play.random_play_app.cv2_utils.crop_image_only', Mock())
    assert not app._try_select_agent('维琳娜', area)
    assert [args.args[2] for args in app.ctx.tm.match_one_by_feature.call_args_list] == [
        'avatar_velina', 'avatar_velina_shade_of_leisure',
    ]
    assert app.ctx.controller.click.call_args.args[0].tuple() == (28, 51)


def test_video_theme_clicks_ocr_center_and_shelf_waits_for_evidence() -> None:
    app = make_app(RandomPlayApp)
    app._all_video_themes = ['喜剧']
    app._need_video_themes = ['喜剧']
    app._current_idx = 1
    app.ctx.screen_loader.get_area.return_value = SimpleNamespace(rect=object(), left_top=Point(20, 40))
    app.ctx.ocr = Mock()
    app.ctx.ocr.crop_and_run_ocr.return_value = {'喜剧': SimpleNamespace(max=MatchResult(1, 4, 6, 8, 10))}
    assert app.choose_theme().is_success
    assert app.ctx.controller.click.call_args.args[0].tuple() == (28, 51)
    app.round_by_find_and_click_area.return_value = SUCCESS
    assert app.choose_onshelf().result is OperationRoundResultEnum.RETRY
    app.round_by_find_and_click_area.return_value = RETRY
    assert app.choose_onshelf().result is OperationRoundResultEnum.RETRY
    app.round_by_find_area.return_value = SUCCESS
    assert app.choose_onshelf().is_success
    assert app.round_by_find_and_click_area.call_count == 2


def test_video_store_recovery_keeps_the_failure_and_leaves_known_screens() -> None:
    app = make_app(RandomPlayApp)
    app._previous_node = None
    app._previous_round_result = OperationRoundResult(OperationRoundResultEnum.FAIL, '未找到配置的宣传员')
    app.check_and_update_current_screen = Mock(return_value=None)
    app._store_area_visible = lambda name: name == '选择宣传员'
    result = app.recover_store_failure()
    assert result.result is OperationRoundResultEnum.RETRY
    app.round_by_find_and_click_area.assert_called_once_with(app.last_screenshot, '影像店营业', '返回')
    app.check_and_update_current_screen.return_value = '大世界-普通'
    result = app.recover_store_failure()
    assert result.is_fail and result.status == '未找到配置的宣传员'


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
