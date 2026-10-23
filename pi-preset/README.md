# π Agent Preset（`@local/dsh-pi-preset`）

π（Pi Adaptive Controller）是一个 **Agent 预设**，不是一个独立应用。它以 Cordis bundle patch 的形式声明一个
`@deepseek-ai/dsh-agent-preset` 行（Loader id `preset-pi`，预设身份 `pi`），因此可以像 Standard / PTC / Minimal / Creator
一样在新建会话时被选中，也可以随时卸载回滚。

- 显示名称：`π`
- 预设 ID：`pi`
- 排序：5（排在 Creator/`cordis` 之后）
- 组成行数：21（20 个原生插件行 + 1 个自检行）

## 它由什么组成

| 类别 | 行 | 作用 |
|---|---|---|
| 身份 | `persona` | π 的系统提示词（约 2400 字符，中文）：五条公理、双层控制、六模块循环、五种模式、数学诚实条款 |
| 上下文 | `agent-instructions` / `time-context` | 工作区 AGENTS.md、当前时间 |
| 执行 | `tool-pwsh`（Windows）/ `tool-bash`（其他）、`tool-fs`、`tool-fs-search`、`tool-jobs` | 真实读写、搜索、后台作业 |
| 规划 | `tool-todo`、`tool-goal` + `command-goal`、`tool-ask-user` | 任务清单、同会话目标、向用户提问 |
| 研究 | `tool-web`、`skill-filesystem` + `tool-skill` | 检索与按需加载的 Skill |
| 交付 | `present`、`tool-schedule` | 交付物声明、提醒 |
| 上下文治理 | `compaction` 组 | 自动压缩、工具结果裁剪 |
| 委派 | `delegation` 组 | `subagent` / `subagent_fork` / 控制工具（无 `workflow`，见“限制”） |
| 控制 | `pi-control` | 自定义工具 `pi_control`、`pi_guard`（见下） |
| 自检 | `pi-selfcheck` | 组合挂载审计日志（最后一行；它跑起来 = 前面每一行都挂载成功） |

**刻意不包含**：`tool-plugin-manager`、`tool-plugin-market`、`workflow`。π 因此没有任何安装/卸载插件、
改自身预设、批量生成子 Agent 的工具——这是结构性约束，不依赖模型自觉。

## 两个自定义工具

### `pi_control`（确定性数学）

| action | 输入 | 输出 |
|---|---|---|
| `signal` | `n`, `count` | `σ(n)`、`r(n)=frac(nπ)`（20 位）、符号平衡统计。用 100 位 π 的 BigInt 精确计算 |
| `step` | `e, a, b, k, eps, sigma, w` | 一步闭环 `e_next`、`u`、`ρ=|a-bk|` |
| `simulate` | `policy` + 模型参数 | 单臂轨迹与指标：RMSE、收敛步、控制开销、饱和数、ρ 区间 |
| `gain_scan` | `a, b, rhoTarget, kmin, kmax` | 满足 `|a-bk| ≤ ρ` 的解析增益区间 |

四种 policy：`fixed` / `adaptive` / `adaptive_random` / `adaptive_pi`（π 符号探索）。

### `pi_guard`（稳定性守卫，读真实会话日志）

`status` 读取**调用方会话自己的** `tool/call` 与 `tool/result` 事件，统计：

- 工具调用总数 / 本回合调用数 / 各工具分布
- 相同 `工具 + 参数` 的最大重复次数
- 连续失败次数与最后一条错误文本
- 相邻调用名切换次数（策略振荡的粗代理）

然后给出 `ok | warn | stop`，并列出触发的规则。预算写在预设配置里，**模型无法修改**。
若会话快照 API 不可用，它会明确返回 `provenance: "unavailable"`，而不是编造数字。

`record` 动作允许模型记录自报结果，但输出会标注 `provenance: "self-reported"`，并提示这不是证据。

## 安装 / 卸载

安装（需要 Full access 或审批）：

```
plugin_manager { action: "install_bundle", target: "D:\\π\\pi-preset" }
```

替换已安装的版本时，先卸载再安装：

```
plugin_manager { action: "remove_bundle", target: "@local/dsh-pi-preset" }
plugin_manager { action: "install_bundle", target: "D:\\π\\pi-preset" }
```

卸载只是移除声明，不影响其他预设；本 bundle 不写 Host 配置、不改模型路由、不改权限预设。

安装后 `http://127.0.0.1:65233` 的会话预设列表应出现 **π**；选择它新建会话即可。

## 配置

`pi-control` 行接受以下配置（全部为正有限数，非法值会让挂载失败而不是静默取默认）：

| 字段 | 默认 | 含义 |
|---|---|---|
| `maxToolCallsPerTurn` | 60 | 单回合工具调用上限 |
| `maxToolCallsTotal` | 400 | 单会话工具调用上限 |
| `maxIdenticalRepeats` | 3 | 相同调用重复多少次判为停止 |
| `maxConsecutiveFailures` | 3 | 连续失败多少次判为停止 |
| `warnRatio` | 0.7 | 达到预算多少比例时给 `warn` |
| `scanWindow` | 5000 | 每次 `pi_guard` 扫描的最近事件数 |

## 已知限制

1. **π 探索信号不是白噪声。** `σ(n)=sign(frac(nπ)-0.5)` 是准周期方波：`7π≈21.9911`、`113π≈354.99997`，
   导致 lag 7 有 98% 位相同、lag 113 有 99.99% 位相同。实验显示它在闭环里比随机探索更差（详见 `../pi-lab/results/`）。
2. **探索在无参数辨识需求时只会增加误差。** 四臂对照中“无探索”始终最好。π 序列的价值在“可逐位复现”，
   不在“更准”。
3. **重复检测使用参数文本的前 160 字符。** 日志里 `arguments` 是原始 JSON 文本；两条长命令若前缀完全相同、
   仅尾部不同，可能被误判为重复。后果是一次 `stop` 建议（模型被要求停下并报告），不是硬阻断。
4. **没有 workflow 工具。** 避免一次调用扇出大量子 Agent；需要并行时用至多 4 个 `subagent`。
5. **`skill-filesystem` 使用默认目录**，未挂载 π 专属 skill 目录；π 的操作协议写在 persona 里（始终在上下文中）。
6. **每个进程只记录一次激活**，不是每次会话；`pi-guard` 的预算是按会话计数的。

## 审计与回滚

- 激活日志：`D:/π/logs/pi-preset-activation.jsonl`（`activated` / `disposed`，含 pid、node 版本、可见工具）。
- 版本化文件：`package.json`、`cordis.patch.yml`、`control.js`、`selfcheck.js`、`index.js`。
- 回滚：`remove_bundle` 后预设从列表消失；其余预设不受影响（已验证）。
