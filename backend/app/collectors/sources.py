"""来源登记。许可信息供路由列出，采集适配器只引用 source_id。"""

from __future__ import annotations

from app.domain.models import Source

MOHRSS = Source(
    id="mohrss",
    name="人社部中国公共招聘网",
    license="政府公开招聘信息",
    requires_login=False,
    is_leading_indicator=False,
)

MOKA = Source(
    id="moka",
    name="Moka ATS 公开招聘官网",
    license="招聘官网公开接口（免鉴权职位列表）",
    requires_login=False,
    is_leading_indicator=False,
)

LIEPIN = Source(
    id="liepin",
    name="猎聘",
    license="登录态 Playwright 采集；开发默认关闭",
    requires_login=True,
    is_leading_indicator=False,
)

ZHIPIN = Source(
    id="zhipin",
    name="BOSS直聘",
    license="登录态 CDP/Playwright 采集；开发默认关闭",
    requires_login=True,
    is_leading_indicator=False,
)

GREENHOUSE = Source(
    id="greenhouse",
    name="Greenhouse Job Board API",
    license="招聘官网公开接口（免鉴权职位列表）",
    requires_login=False,
    is_leading_indicator=False,
)

LEVER = Source(
    id="lever",
    name="Lever 公开职位接口",
    license="招聘官网公开接口（免鉴权职位列表）",
    requires_login=False,
    is_leading_indicator=False,
)

ASHBY = Source(
    id="ashby",
    name="Ashby Job Board API",
    license="招聘官网公开接口（免鉴权职位列表）",
    requires_login=False,
    is_leading_indicator=False,
)

ALL_SOURCES: tuple[Source, ...] = (
    MOHRSS,
    MOKA,
    LIEPIN,
    ZHIPIN,
    GREENHOUSE,
    LEVER,
    ASHBY,
)

SOURCES_BY_ID: dict[str, Source] = {s.id: s for s in ALL_SOURCES}
