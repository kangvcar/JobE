"""来源登记。许可信息供路由列出，采集适配器只引用 source_id。"""

from __future__ import annotations

from app.domain.models import Source

MOHRSS = Source(
    id="mohrss",
    name="人社部中国公共招聘网",
    license="政府公开招聘信息，仅用于研究与统计，不采集个人信息",
    requires_login=False,
    is_leading_indicator=False,
)

MOKA = Source(
    id="moka",
    name="Moka ATS 公开招聘官网",
    license="招聘官网公开接口（免鉴权职位列表），不采集负责人联系方式",
    requires_login=False,
    is_leading_indicator=False,
)

LIEPIN = Source(
    id="liepin",
    name="猎聘",
    license="人工登录、单 IP 串行、低频只读；不突破技术措施，默认关闭（ADR 0001）",
    requires_login=True,
    is_leading_indicator=False,
)

ALL_SOURCES: tuple[Source, ...] = (MOHRSS, MOKA, LIEPIN)

SOURCES_BY_ID: dict[str, Source] = {s.id: s for s in ALL_SOURCES}
