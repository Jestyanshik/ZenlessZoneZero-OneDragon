import time
from typing import TYPE_CHECKING

from one_dragon.utils.log_utils import log

if TYPE_CHECKING:
    from collections.abc import Callable

    from one_dragon.base.operation.operation_round_result import OperationRoundResult
    from zzz_od.application.zzz_application import ZApplication


NPC_INTERACTION_ATTEMPTS = 3


def open_npc(
    op: 'ZApplication', recognize: 'Callable[[], str | None]', *,
    move_forward: bool = False, failure: str = '未进入 NPC 交互画面',
) -> 'OperationRoundResult':
    """用最新截图确认交互画面，每轮最多按一次。"""
    if op.last_screenshot is not None:
        marker = recognize()
        if marker is not None:
            log.info('NPC screen confirmed: app=%s marker=%s', op.app_id, marker)
            return op.round_success(marker)

    if op.node_retry_times >= NPC_INTERACTION_ATTEMPTS:
        log.warning('NPC screen not confirmed: app=%s', op.app_id)
        return op.round_fail(failure)
    if op.last_screenshot is None:
        log.warning('NPC screen capture missing: app=%s', op.app_id)
        return op.round_retry('未获得 NPC 画面', wait=1)

    if op.node_retry_times == 0:
        if move_forward:
            op.ctx.controller.move_w(press=True, press_time=1, release=True)
        time.sleep(1)

    log.info(
        'NPC screen not yet confirmed: app=%s attempt=%d/%d',
        op.app_id, op.node_retry_times + 1, NPC_INTERACTION_ATTEMPTS,
    )
    submitted = op.ctx.controller.press_npc_interact()
    return op.round_retry('等待 NPC 交互画面' if submitted else '交互键发送失败', wait=2)
