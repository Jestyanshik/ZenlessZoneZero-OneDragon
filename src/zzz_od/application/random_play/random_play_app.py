import difflib
from typing import ClassVar

from cv2.typing import MatLike

from one_dragon.base.config.config_item import get_config_item_from_enum
from one_dragon.base.geometry.point import Point
from one_dragon.base.matcher.match_result import MatchResult
from one_dragon.base.operation.application import application_const
from one_dragon.base.operation.operation_edge import node_from
from one_dragon.base.operation.operation_node import operation_node
from one_dragon.base.operation.operation_notify import NotifyTiming, node_notify
from one_dragon.base.operation.operation_round_result import OperationRoundResult
from one_dragon.base.screen.screen_area import ScreenArea
from one_dragon.utils import cv2_utils
from one_dragon.utils.i18_utils import gt
from one_dragon.utils.log_utils import log
from zzz_od.application.npc_interaction import NPC_INTERACTION_ATTEMPTS, open_npc
from zzz_od.application.random_play import random_play_const
from zzz_od.application.random_play.random_play_config import (
    RANDOM_AGENT_NAME,
    RandomPlayConfig,
    RandomPlayTransportPoint,
)
from zzz_od.application.zzz_application import ZApplication
from zzz_od.context.zzz_context import ZContext
from zzz_od.game_data.agent import Agent, AgentEnum
from zzz_od.operation.back_to_normal_world import BackToNormalWorld
from zzz_od.operation.transport import Transport
from zzz_od.operation.turning.turn_compensation import AngleTurnCompensator
from zzz_od.operation.turning.turn_to_angle import turn_to_angle


class RandomPlayApp(ZApplication):

    """录像店营业:录像带店日常经营(宣传/营业/结算)。无消耗,产出菲林与丁尼。"""

    STATUS_ALL_VIDEO_CHOOSE: ClassVar[str] = '已选择全部录像带'
    STATUS_ALREADY_RUNNING: ClassVar[str] = '正在营业'

    def __init__(self, ctx: ZContext):
        ZApplication.__init__(
            self,
            ctx=ctx,
            app_id=random_play_const.APP_ID,
            op_name=random_play_const.APP_NAME,
        )

        self.config: RandomPlayConfig = self.ctx.run_context.get_config(
            app_id=self.app_id,
            instance_idx=self.ctx.current_instance_idx,
            group_id=application_const.DEFAULT_GROUP_ID,
        )

    def handle_init(self) -> None:
        """
        执行前的初始化 由子类实现
        注意初始化要全面 方便一个指令重复使用
        """
        self._all_video_themes: list[str] = [
            '纪实', '怀旧', '冒险', '幻想', '喜剧', '动作', '惊悚', '悬疑',
            '访谈', '都市', '时尚', '灾难', '悲剧', '亲情', '广告', '爱情',
        ]
        self._need_video_themes: list[str] = []
        self._current_idx: int = 0
        self.turn_compensator: AngleTurnCompensator = AngleTurnCompensator(self.ctx.controller)
        self.retried_transport: bool = False
        self._promoter_confirmation_sent: bool = False

    @node_from(from_name='确认录像店交互', success=False)
    @node_from(from_name='交互对话', success=False)
    @node_from(from_name='等待经营画面加载', success=False)
    @operation_node(name='传送', is_start_node=True)
    def transport(self) -> OperationRoundResult:
        if self.previous_node.name in {'确认录像店交互', '交互对话', '等待经营画面加载'}:
            if self.retried_transport:
                return self.round_fail(status='进入经营画面失败，重传送超限')
            self.retried_transport = True

        self.turn_compensator.clear_pending_sample()
        item = get_config_item_from_enum(RandomPlayTransportPoint, self.config.transport_point)
        op = Transport(self.ctx, item.area_name, item.tp_name)
        return self.round_by_op_result(op.execute())

    @node_from(from_name='传送')
    @operation_node(name='移动交互', node_max_retry_times=10)
    def move_and_interact(self) -> OperationRoundResult:
        """
        录像店-柜台 / 布亚斯特城区-录像店营业点：转向正东后前移再交互
        澄辉坪-录像店营业点：传送落点已正对入口，直接交互
        :return:
        """
        if self.config.transport_point in {
            RandomPlayTransportPoint.POINT_1.value.value,
            RandomPlayTransportPoint.POINT_3.value.value,
        }:
            result = turn_to_angle(self, target_angle=0, turn_status='转向正东')
            if not result.is_success:
                return result
            self.ctx.controller.move_w(press=True, press_time=1, release=True)

        return self.round_success(wait=1)

    @node_from(from_name='移动交互')
    @operation_node(name='确认录像店交互', node_max_retry_times=NPC_INTERACTION_ATTEMPTS)
    def open_interaction(self) -> OperationRoundResult:
        return open_npc(
            self, self._interaction_marker, failure='未进入录像店对话或经营界面'
        )

    def _business_marker(self) -> str | None:
        for area_name in ('经营状况', '昨日账本'):
            if self.round_by_find_area(self.last_screenshot, '影像店营业', area_name).is_success:
                return area_name
        return None

    def _narration_visible(self) -> bool:
        if self.config.transport_point != RandomPlayTransportPoint.POINT_3.value.value:
            return False
        return any(
            self.round_by_ocr(self.last_screenshot, word, lcs_percent=1).is_success
            for word in ('层层安检', '偷偷送上来')
        )

    def _interaction_marker(self) -> str | None:
        marker = self._business_marker()
        if marker is not None:
            return marker
        if self.config.transport_point != RandomPlayTransportPoint.POINT_1.value.value:
            area = self.ctx.screen_loader.get_area('影像店营业', '右侧选项区域')
            if self.round_by_ocr(self.last_screenshot, '查看经营状况', area=area, lcs_percent=1).is_success:
                return '查看经营状况'
            if self._narration_visible():
                return '阿玖旁白'
        return None

    @node_from(from_name='确认录像店交互')
    @operation_node(name='交互对话', node_max_retry_times=10)
    def handle_interaction_dialog(self) -> OperationRoundResult:
        marker = self._business_marker()
        if marker is not None:
            return self.round_success(marker)
        if self.node_retry_times >= self.node_max_retry_times:
            return self.round_fail('未进入录像店经营界面')

        area = self.ctx.screen_loader.get_area('影像店营业', '右侧选项区域')
        result = self.round_by_ocr_and_click(self.last_screenshot, '查看经营状况', area=area)
        if result.is_success:
            return self.round_retry('等待录像店经营界面', wait=1)

        if self._narration_visible():
            self.round_by_click_area('影像店营业', '对话框标题')
        return self.round_retry('等待录像店对话', wait=1)

    @node_from(from_name='交互对话')
    @operation_node(name='等待经营画面加载', node_max_retry_times=10)
    def wait_run(self) -> OperationRoundResult:
        # 每日首次。点完关闭按钮后回到本节点重判，防止昨日账本残影或未关闭
        result = self.round_by_find_area(self.last_screenshot, '影像店营业', '昨日账本')
        if result.is_success:
            self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '按钮-关闭')
            return self.round_retry(wait=1)
        # 识别到"经营状况"就点击一下以保证在该分支。二次运行时，有极低概率"无人咨询"变成"咨询中"并被默认跳转
        result = self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '经营状况')
        if result.is_success:
            return self.round_success(wait=1)

        if self.node_retry_times >= self.node_max_retry_times:
            return self.round_fail('未进入录像店经营界面')
        return self.round_retry(status='等待录像店经营界面', wait=1)

    @node_from(from_name='等待经营画面加载')
    @operation_node(name='识别营业状态')
    def check_running(self) -> OperationRoundResult:
        result = self.round_by_find_area(self.last_screenshot, '影像店营业', '正在营业')
        if result.is_success:
            return self.round_success(RandomPlayApp.STATUS_ALREADY_RUNNING)
        result = self.round_by_find_area(self.last_screenshot, '影像店营业', '开始营业')
        if result.is_success:
            return self.round_success()

        return self.round_retry(status='等待营业状态', wait=1)

    @node_from(from_name='识别营业状态', status=STATUS_ALREADY_RUNNING)
    @operation_node(name='关闭经营页面')
    def close_business_page(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '返回',
                                                 retry_wait=1)

    @node_from(from_name='识别营业状态')
    @operation_node(name='点击宣传员入口')
    def click_promoter_entry(self) -> OperationRoundResult:
        """
        在经营状况页面 点击代理人的位置
        :return:
        """
        if self._store_area_visible('选择宣传员'):
            return self.round_success('选择宣传员')
        if not self._store_area_visible('经营状况'):
            return self.round_retry('未找到 经营状况', wait=1)
        return self.round_by_click_area('影像店营业', '宣传员入口', retry_wait=1)

    def _store_area_visible(self, area_name: str) -> bool:
        return self.round_by_find_area(self.last_screenshot, '影像店营业', area_name).is_success

    @node_from(from_name='点击宣传员入口')
    @operation_node(name='选择宣传员')
    def choose_promoter(self) -> OperationRoundResult:
        """
        在经营状况页面 点击代理人的位置
        :return:
        """
        if not self._store_area_visible('选择宣传员'):
            return self.round_retry('未找到 选择宣传员', wait_round_time=1)

        # 已经选择过了 直接返回
        if self._store_area_visible('换下'):
            return self.round_success('换下')

        target_agent_name_1 = self.config.agent_name_1
        target_agent_name_2 = self.config.agent_name_2
        dt = self.run_record.get_current_dt()
        idx = (int(dt[-1]) % 2) + 1

        if RANDOM_AGENT_NAME in (target_agent_name_1, target_agent_name_2):
            # 随机选择
            return self.round_by_click_area('影像店营业', f'宣传员-{idx}', retry_wait=1)

        area = self.ctx.screen_loader.get_area('影像店营业', '宣传员列表')
        if idx == 1:
            candidates = [target_agent_name_1, target_agent_name_2]
        else:
            candidates = [target_agent_name_2, target_agent_name_1]

        # 依次尝试匹配每个候选代理人（名称 OCR → 头像匹配）
        for agent_name in dict.fromkeys(candidates):
            if self._try_select_agent(agent_name, area):
                return self.round_success(agent_name)
            log.info(f'代理人匹配失败: {agent_name}')

        if self.node_retry_times >= 2:
            log.warning('Random Play could not find either configured promoter: %s', candidates)
            return self.round_fail('未找到配置的宣传员')
        # 向下滚动并重试
        log.info('所有候选代理人匹配失败, 向下滚动重试')
        self.scroll_area('影像店营业', '宣传员列表')
        return self.round_retry(wait=0.5)

    @node_from(from_name='选择宣传员')
    @operation_node(name='确认宣传员')
    def confirm_promoter(self) -> OperationRoundResult:
        if self._store_area_visible('选择宣传员'):
            if self._store_area_visible('换下'):
                result = self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '返回')
                if result.is_success:
                    self._promoter_confirmation_sent = True
            elif not self._promoter_confirmation_sent:
                result = self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '确认')
                self._promoter_confirmation_sent = result.is_success
        elif self._promoter_confirmation_sent and self._store_area_visible('经营状况'):
            return self.round_success('经营状况')
        if self.node_retry_times >= self.node_max_retry_times:
            log.warning('Random Play did not return to business status after promoter selection: confirmation_sent=%s',
                        self._promoter_confirmation_sent)
        return self.round_retry('等待宣传员确认后返回经营状况', wait=1)

    def _try_select_agent(self, agent_name: str, area: ScreenArea) -> bool:
        """尝试通过名称 OCR 或头像匹配选择代理人"""
        result = self.round_by_ocr_and_click(self.last_screenshot, agent_name, area=area,
                                             color_range=[(230, 230, 230), (255, 255, 255)])
        if result.is_success:
            return True

        mr = self.get_pos_by_avatar(self.last_screenshot, agent_name)
        return mr is not None and self.ctx.controller.click(mr.center)

    def get_pos_by_avatar(self, screen: MatLike, target_agent_name: str) -> MatchResult | None:
        """
        根据头像匹配
        @param screen: 游戏画面
        @param target_agent_name: 需要选择的代理人名称
        @return:
        """
        agent: Agent | None = None
        for agent_enum in AgentEnum:
            if agent_enum.value.agent_name == target_agent_name:
                agent = agent_enum.value
                break

        area = self.ctx.screen_loader.get_area('影像店营业', '宣传员列表')
        part = cv2_utils.crop_image_only(screen, area.rect)

        if agent is None:
            return None

        for template_id in agent.template_id_list:
            mr = self.ctx.tm.match_one_by_feature(part, 'predefined_team', f'avatar_{template_id}')
            if mr is not None:
                mr.add_offset(area.left_top)
                return mr
        return None

    @node_from(from_name='确认宣传员')
    @operation_node(name='识别录像带主题')
    def check_video_theme(self) -> OperationRoundResult:
        result = self.round_by_find_area(self.last_screenshot, '影像店营业', '经营状况')
        if not result.is_success:
            return self.round_retry(status=result.status, wait=1)

        areas = [
            self.ctx.screen_loader.get_area('影像店营业', '录像带主题-1'),
            self.ctx.screen_loader.get_area('影像店营业', '录像带主题-2'),
            self.ctx.screen_loader.get_area('影像店营业', '录像带主题-3')
        ]

        target_list = [gt(i, 'game') for i in self._all_video_themes]
        for area in areas:
            part = cv2_utils.crop_image_only(self.last_screenshot, area.rect)
            ocr_result = self.ctx.ocr.run_ocr_single_line(part)

            results = difflib.get_close_matches(ocr_result, target_list, n=1)

            if results:
                idx = target_list.index(results[0])
                self._need_video_themes.append(self._all_video_themes[idx])

        # 识别不到 随便补充到3个主题
        for theme in self._all_video_themes:
            if len(self._need_video_themes) >= 3:
                break
            if theme in self._need_video_themes:
                continue
            self._need_video_themes.append(theme)

        log.info(f'所需主题 {self._need_video_themes}')
        return self.round_success()

    @node_from(from_name='识别录像带主题')
    @operation_node(name='点击录像带入口')
    def click_video_entry(self) -> OperationRoundResult:
        """
        在经营状况页面 点击录像带的位置
        :return:
        """
        return self.round_by_click_area('影像店营业', '录像带入口',
                                        retry_wait=1)

    @node_from(from_name='点击录像带入口')
    @operation_node(name='识别推荐上架')
    def check_recommended(self) -> OperationRoundResult:
        result = self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '推荐上架')

        if result.is_success:
            return self.round_success(status=result.status, wait=1)

        return self.round_by_find_area(self.last_screenshot, '影像店营业', '上架筛选', retry_wait=1)

    @node_from(from_name='识别推荐上架', status='上架筛选')
    @node_from(from_name='上架')
    @operation_node(name='上架筛选')
    def click_filter(self) -> OperationRoundResult:
        """
        在录像带画面 点击上架筛选
        :return:
        """
        if self._current_idx >= len(self._need_video_themes):
            return self.round_success(status=RandomPlayApp.STATUS_ALL_VIDEO_CHOOSE)

        result = self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '上架筛选')
        if result.is_success:
            self._current_idx += 1
            return self.round_success(result.status, wait=1)
        else:
            return self.round_retry(result.status, wait=1)

    @node_from(from_name='上架筛选')
    @operation_node(name='选择主题')
    def choose_theme(self) -> OperationRoundResult:
        """
        选择主题
        :return:
        """
        area = self.ctx.screen_loader.get_area('影像店营业', '主题筛选')
        ocr_results = self.ctx.ocr.crop_and_run_ocr(self.last_screenshot, area.rect)

        target_list = [gt(i, 'game') for i in self._all_video_themes]
        current_target = self._need_video_themes[self._current_idx - 1]
        for ocr_str, mrl in ocr_results.items():
            if mrl.max is None:
                continue

            results = difflib.get_close_matches(ocr_str, target_list, n=1)

            if not results:
                continue

            idx = target_list.index(results[0])
            theme = self._all_video_themes[idx]
            if theme != current_target:
                continue

            target_point = area.left_top + mrl.max.center
            if self.ctx.controller.click(target_point):
                return self.round_success(wait=1)
            else:
                return self.round_retry(wait=0.5)

        # 找不到 往下滑动
        start = area.center
        end = start + Point(0, -100)
        self.ctx.controller.drag_to(start=start, end=end)
        return self.round_retry(status=f'未找到{current_target}', wait=1)

    @node_from(from_name='选择主题')
    @operation_node(name='上架')
    def choose_onshelf(self) -> OperationRoundResult:
        """
        上架
        :return:
        """
        result = self.round_by_find_area(self.last_screenshot, '影像店营业', '下架',)
        if result.is_success:  # 已经上架了
            return self.round_success()

        # 点击可能只关闭筛选，下一轮用新画面确认是否已上架。
        click = self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '上架')
        return self.round_retry(status=click.status, wait_round_time=1)

    @node_from(from_name='识别推荐上架', status='推荐上架')
    @node_from(from_name='上架筛选', status=STATUS_ALL_VIDEO_CHOOSE)
    @operation_node(name='返回')
    def back(self) -> OperationRoundResult:
        result = self.round_by_find_area(self.last_screenshot, '影像店营业', '经营状况')
        if result.is_success:
            return self.round_success()

        return self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '返回',
                                                 retry_wait=1)

    @node_from(from_name='返回')
    @operation_node(name='开始营业')
    def start(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '开始营业',
                                                 retry_wait=1)

    @node_from(from_name='开始营业')
    @operation_node(name='确认营业')
    def confirm_business(self) -> OperationRoundResult:
        return self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '开始营业-确认',
                                                 retry_wait=1)

    @node_from(from_name='确认营业')
    @operation_node(name='营业后确认')
    def confirm(self) -> OperationRoundResult:
        if self._store_area_visible('正在营业'):
            return self.round_success(self.STATUS_ALREADY_RUNNING)
        success_dialog = self.round_by_ocr(self.last_screenshot, '生意兴隆', lcs_percent=1)
        if not success_dialog.is_success:
            return self.round_retry('未确认录像店开始营业', wait=1)
        return self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '营业后确认',
                                                 retry_wait=1)

    @node_from(from_name='识别营业状态', success=False)
    @node_from(from_name='点击宣传员入口', success=False)
    @node_from(from_name='选择宣传员', success=False)
    @node_from(from_name='确认宣传员', success=False)
    @node_from(from_name='识别录像带主题', success=False)
    @node_from(from_name='点击录像带入口', success=False)
    @node_from(from_name='识别推荐上架', success=False)
    @node_from(from_name='上架筛选', success=False)
    @node_from(from_name='选择主题', success=False)
    @node_from(from_name='上架', success=False)
    @node_from(from_name='返回', success=False)
    @node_from(from_name='开始营业', success=False)
    @node_from(from_name='确认营业', success=False)
    @node_from(from_name='营业后确认', success=False)
    @operation_node(name='录像店失败后退出')
    def recover_store_failure(self) -> OperationRoundResult:
        failure = self.previous_node.status
        if self.check_and_update_current_screen() in {'大世界-普通', '大世界-勘域'}:
            return self.round_fail(failure)

        # 只在已识别的经营页面点击返回，保留原始失败状态。
        if any(self._store_area_visible(marker) for marker in ('选择宣传员', '上架筛选', '经营状况')):
            self.round_by_find_and_click_area(self.last_screenshot, '影像店营业', '返回')
        if self.node_retry_times >= self.node_max_retry_times:
            log.warning('Random Play recovery could not confirm the world: %s', failure)
            return self.round_fail(failure)
        return self.round_retry(failure, wait=1)

    @node_from(from_name='营业后确认')
    @node_from(from_name='关闭经营页面')
    @node_notify(when=NotifyTiming.PREVIOUS_DONE)
    @operation_node(name='返回大世界')
    def back_to_world(self) -> OperationRoundResult:
        op = BackToNormalWorld(self.ctx)
        return self.round_by_op_result(op.execute())


def __debug():
    ctx = ZContext()
    ctx.init()
    ctx.run_context.start_running()
    app = RandomPlayApp(ctx)
    app.execute()


if __name__ == '__main__':
    __debug()
