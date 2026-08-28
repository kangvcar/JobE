# 职途罗盘前端交付说明

## 设计方向

Reading this as: 面向新兴领域青年与在校学生的职业测量产品，不是 SaaS 仪表盘，也不是营销落地页。视觉语言按「测量仪器 / 新闻纸」来：冷静、可核对、让变化本身成为主角。

三档旋钮：VARIANCE 5 / MOTION 4 / DENSITY 7。这是日常用的数据产品，不对称但不能乱，动效只服务状态变化，密度够看清差距和趋势。

**字体。** IBM Plex Sans + IBM Plex Mono，自托管 woff2。Plex 带一点实验室和出版感，避开 Inter / Geist 那套 AI 产品默认脸。数字、时间片、证据等级走等宽。

**颜色。** 冷灰纸面 `oklch(0.968 0.007 248)`，墨色文字，单一强调色是氧化铜 `oklch(0.52 0.14 38)`。升值用强调色（中文行情里红表示向上），贬值用克制的青绿，并同时写成「升值 / 贬值」文字，不单靠颜色。没有紫蓝渐变，没有大圆角。圆角统一 4px。

**信息架构。** 主导航只有「我 / 市场 / 图谱」。诊断是「我」的延续（上传之后把差距摊开），审核是顶栏队列入口，证据是全站抽屉，不是第五个栏目。

## 图谱

Cytoscape.js 3.34，默认 WebGL，失败或用户切换时回退 Canvas（URL `?renderer=canvas`）。布局用 fcose，技能簇是 compound 节点，再点一次收起子节点。视图可按技术栈或层级切换。Mock 图谱 **334 节点 / 649 边**（20 个技能簇 + 约 40 个岗位 + 270+ 技能点）。Playwright 无头环境里 WebGL 不可用会回退 Canvas，本机 Chrome 应走 WebGL。键盘：方向键平移，`+`/`-` 缩放，Home 适配，Esc 取消选中。

统计图用 ECharts 6 的 line / heatmap，不用 graph 系列。

## Mock 数据

- 时间片 21 个：2021Q1-2026Q1
- 诊断三档完整案例：林浩然 / 高度匹配，赵昕 / 有明显差距，陈攸 / 不匹配
- 弱证据技能点、萌芽区弱信号候选（1 条证据）、AI 审核员与统计信号矛盾的待确认项

字段名与 `backend/app/domain/models.py` 保持 snake_case。默认 `VITE_USE_MOCK=true`，联调设 `false` 并换 `VITE_API_BASE`。

## 验证

ego-browser 能打开页面并读到无障碍树，但当前环境里 `Page.captureScreenshot` 在设置视口后会超时。结构检查用了 ego-browser 的 `snapshotText`；PNG 用 Playwright 写进 `frontend/screenshots/`。

验证中修掉的问题：

- 升值列被权重上限压成空的，市场位移在首屏看不见
- 证据 `fetched_at` 拼出非法日期（如 2025-19），采集时间原样漏出
- 萌芽区候选岗位一律「证据 6 条」，弱信号看起来和已发布岗位一样硬
- 诊断案例的证据落到职位文本上，简历页没有定位框

## 期望后端提供的接口

类型在 `src/api/types.ts`，HTTP 实现在 `src/api/http.ts`。

| 方法 | 路径 | 请求 | 响应 |
| --- | --- | --- | --- |
| GET | `/api/match/me` | `profile_id`, `role_id` | `MeHome` |
| POST | `/api/match/resume` | `multipart file`, `role_id` | `DiagnoseResult` |
| GET | `/api/match/cases/:id` | path `strong` / `gapped` / `mismatch` | `DiagnoseResult` |
| GET | `/api/graph/overview` | `view=stack\|level` | `GraphPayload` |
| GET | `/api/graph/roles` | | `Role[]` |
| GET | `/api/graph/roles/:id` | | `RoleDetail` |
| GET | `/api/graph/skills/:id` | | `SkillDetail` |
| GET | `/api/graph/candidates` | | `CandidateCard[]` |
| GET | `/api/graph/evidence/:id` | | `EvidenceDetail` |
| GET | `/api/graph/evidence` | `ids=` 逗号分隔 | `EvidenceDetail[]` |
| GET | `/api/evolution/market` | | `MarketOverview` |
| GET | `/api/review/queue` | | `ReviewItem[]` |
| POST | `/api/review/:id/decide` | `{ decision: confirm\|reject }` | `ReviewItem[]` |

时间片格式 `YYYYQn`。证据的 `span.bbox` 为页内归一化 `[x0,y0,x1,y1]`。匹配只返回四档 `tier`，前端不展示 `coverage` 百分比。

## 妥协

- 没有上组件库全家桶，弹层用 Radix Dialog，其余自己写
- 没有 Redux，状态是 React + URL + sessionStorage
- 技能点中文名在 HTTP 模式下仍可能落到打包进前端的目录表；联调后应由接口带 `name`
- 升值位移在 mock 里对 RAG / 智能体编排 / vLLM 做了上一时间片下调，否则权重顶格后首屏看不出「市场在动」
- ego-browser 截图通道不可用，截图文件来自 Playwright，结构核验来自 ego-browser

## 截图

- `frontend/screenshots/01-me.png` 首屏
- `frontend/screenshots/02-market.png` 市场与萌芽观察区
- `frontend/screenshots/03-graph.png` 图谱
- `frontend/screenshots/04-diagnose.png` 诊断结果
- `frontend/screenshots/05-evidence.png` 证据弹层（简历页定位框）
- `frontend/screenshots/06-review.png` 待确认队列
