# π（Pi Adaptive Controller）交付报告

> 生成时间：2026-10-23 · 运行环境：DSH Desktop `0.2.1-rc.2` · 工作目录 `D:\π`

---

## 0. 一句话结论

**π 已经作为第 5 个 Agent Preset 注册进当前 Harness，并已真实挂载（21 行插件全部激活，有审计日志为证）。**
它的两个自定义工具经过 15 项单元测试与 171 项跨语言一致性校验；数学控制层的 5 项验证全部通过；
四臂对照实验（3600 次运行）的结论是**否定性的**：在这套一阶模型里，π 确定性探索不如无探索，也略差于随机探索。
报告如实保留这个结论，并给出实验证据与替代方案。

---

## 1. 环境核查（实测，非推断）

| 项目 | 实测值 | 来源 |
|---|---|---|
| Harness / Cordis 版本 | `@deepseek-ai/*` `0.2.1-rc.2` | bundle 清单、`Config.listConfigs.packageDir` |
| 运行时 | Electron node `v24.21.0`，profile `desktop` | 激活日志 `node` 字段 |
| 预设机制 | bundle patch 声明 `@deepseek-ai/dsh-agent-preset` 行；`config.id/name/description/order/plugins`；注册即 eager 挂载、失败仍留在花名册 | 包 README + 实际样例（`standard/ptc/minimal/cordis` 四个 patch） |
| 现有预设 | `standard`(order 1)、`ptc`(2)、`minimal`(3)、`cordis`(Creator, 4) | `Config.listConfigs name=@deepseek-ai/dsh-agent-preset` |
| Loader 条目 | 195（安装 π 之前 194） | `plugin_manager list_plugins` |
| 可用能力 | 工具注册表（scoped）、prompt section、skill provider、subagent、jobs、schedule、compaction、session 日志 | `Service.listService` / `Event.listEvents` |
| 权限 | 本会话审批提示已关闭（never）；文件策略 danger-full-access | 会话运行时上下文 |
| 预设目录 | 不存在历史 `$DSH_HOME/.agent-presets/<id>/`；预设只能通过 bundle 安装 | 目录核查 + registry README |

**结论**：当前版本只支持“bundle patch 声明预设”这一条路径，没有 `preset.yml`/`agent.cordis.yml` 的旧式目录机制
（旧机制已被移除）。π 因此以 bundle 形式交付。

---

## 2. 交付物清单

| 路径 | 内容 |
|---|---|
| `D:\π\pi-preset\cordis.patch.yml` | 预设声明（21 行组合，含完整系统提示词与预算配置） |
| `D:\π\pi-preset\control.js` | `pi_control` + `pi_guard` 两个模型可见工具（零依赖） |
| `D:\π\pi-preset\selfcheck.js` | 组合挂载审计（最后一行） |
| `D:\π\pi-preset\package.json` / `index.js` / `locale\*.json` / `icon.svg` | bundle 清单、Host 空实现、插件元数据、图标 |
| `D:\π\pi-preset\README.md` | 预设说明、安装/卸载、配置、限制 |
| `D:\π\pi-lab\pi_model.py` | 数学控制器的独立 Python 参考实现 |
| `D:\π\pi-lab\experiment.py` | 测试 B（数学控制）+ 测试 C（四臂对照） |
| `D:\π\pi-lab\signal_study.py` / `golden_study.py` | π 信号性质、辨识实验、φ 替代方案 |
| `D:\π\pi-lab\crosscheck.py` + `emit_js.mjs` | JS 与 Python 的逐点一致性校验 |
| `D:\π\tests\control.test.mjs` | 15 项单元测试 |
| `D:\π\pi-lab\results\*.md` / `*.csv` / `*.json` | 全部真实结果 |
| `D:\π\logs\pi-preset-activation.jsonl` | 激活审计日志 |

---

## 3. 预设结构与系统提示词

### 3.1 组合（21 行）

```
persona → agent-instructions → time-context
        → tool-pwsh(Windows)/tool-bash(other) → tool-fs → tool-fs-search → tool-jobs
        → tool-schedule → tool-todo → tool-goal → command-goal → tool-ask-user
        → tool-web → skill-filesystem → tool-skill → present
        → compaction{compaction-basic, command-compact, tool-result-pruner}
        → delegation{subagent, subagent_fork, subagent-control, list-agents}
        → pi-control → pi-selfcheck
```

有意缺失：`tool-plugin-manager`、`tool-plugin-market`、`workflow`。
**π 没有安装插件、改自身预设、批量扇出子 Agent 的工具**——这是结构约束，不靠提示词自觉。

### 3.2 系统提示词（`persona.prefix`，全文 2378 字符）

完整文本见 `cordis.patch.yml` 第 21–66 行（`prefix: |-` 段）。要点：

1. **五条公理**：事实与推断分离（四类标注）／基准不可伪造／权限不可自升／随时可停止／自治有边界。
2. **双层控制**：数学层只处理真实测量（延迟、token、错误率、完成率、调用次数、预算、队列、模型切换）；
   认知层用“目标→证据→计划→执行→验证→纠偏”，不得用数学符号伪装精确性。
3. **六模块循环**：Observer → Reference → Plan → Execute → Feedback → StabilityGuard，附硬红线
   （同参重复 3 次／连续失败 3 次／超预算 → 停止并请求人工接管）。
4. **五种模式**：Observe / Research / Simulate / Assist（默认）/ Control，各自边界明确。
5. **数学诚实条款**：π 序列不是随机数、不天然优于随机探索；一阶模型结论不得推广到所有 AI 工作流；
   无测量就写“未测量”；单次实验不构成策略比较。
6. **输出约定**：结论先行、数字标注来源、最终报告区分“已实现/已测试/仅理论/未实现”。

提示词是模板（`{{…}}` 变量语法），文本中没有出现 `{{`，已在 YAML 校验脚本中断言。

---

## 4. 数学控制器

### 4.1 与原始构想的关系

| 原始构想 | 实际实现 | 理由 |
|---|---|---|
| `e(t)=(y-y*)/s`、`z=π+e` | 保留为约定与提示词语义 | `z=π+e` 只是平移，对稳定性无贡献，如实写明 |
| `r(n)=frac(nπ)`、`σ(n)=±1` | `pi_control action=signal`，100 位 π 的 BigInt 精确计算 | 避免浮点在长时间运行中漂移 |
| 一阶离散系统 + `u=k·e+ε·σ` | `pi_control action=step/simulate` | 参数、限幅、扰动、投影全部显式 |
| RLS 在线估计 | **未实现于预设**；仅在实验室（`signal_study.py`）验证其可行性 | 没有可信的在线辨识对象时，把它塞进 Agent 只是装饰 |
| `|a-bk|≤ρ<1` | `pi_control action=gain_scan` 给解析区间；`simulate` 报 ρ 区间与稳定步占比 | 可计算、可反驳 |
| 双层控制 | 数学层 = 两个工具；认知层 = 提示词循环 | 不把两层混为一谈 |

### 4.2 `pi_guard` 数据来源

读取**调用方会话自己的**持久日志（`tool/call`：`turn/step/callId/name/arguments`；
`tool/result`：`turn/step/message{callId,content,isError}`），统计调用数、重复、连续失败、振荡，给出 `ok|warn|stop`。
指标统一标注 `provenance: measured:session-log`；快照 API 不可用时返回 `unavailable`，不编造数字。
预算写在预设配置里，模型无法修改。

**实测验证**：当前会话日志解压后含 871 个事件，其中 `tool/call` 150、`tool/result` 149，
字段形状与工具实现假设完全一致（见 `D:\π\tools\session-events.mjs` 的真实输出）。

---

## 5. 测试与真实结果

### 测试 A：基础 Agent 测试 — **部分验证**

| 项 | 结果 |
|---|---|
| 预设能否被当前版本加载 | ✅ 已加载：Loader 条目 `include:preset-pi`，`fiberPhase: active` |
| 组合是否真的挂载（不只是声明） | ✅ 最后一行 `pi-selfcheck` 在 pid 43696 内执行并写入审计日志 |
| 工具能否注册 | ✅ `control.js apply()` 在挂载过程中执行；若抛错，整棵组合被拒绝，自检行不会出现 |
| 端到端对话（真实模型 + 真实任务） | ❌ **未验证**：无法从会话内创建并驱动一个 π 会话 |

```
{"at":"2026-10-23T04:18:22.841Z","event":"activated","preset":"pi","module":"pi-selfcheck","pid":43696,"node":"24.21.0","visiblePiTools":[]}
```

`visiblePiTools` 为空是预期的：`tools.schemas()` 不带 scope 时只返回全局视图，而 π 的工具注册在预设作用域内
（正是这一点保证了它不会泄漏到 Standard 等其他预设）。它不作为工具注册失败的证据，工具激活由
“自检行能执行”本身证明——`control.js` 若抛错，整棵组合会被拒绝，自检行根本不会运行。

### 测试 B：数学控制 — **5/5 通过**

| 检查 | 关键数字 | 结果 |
|---|---|---|
| B1 正负误差对称收敛 | e0=±1 时 30 步内逐点满足 `e(+)+e(-)=0`；ρ=0.30 | 通过 |
| B2 不稳定被识别 | a=2, k=0 → ρ=2；1024 步后溢出，`finite=false`，不产出伪数值 | 通过 |
| B3 有界扰动不越界 | 理论界 `(b·ε+w)/(1-ρ)=0.2143`；200 次试验最大 0.1400 | 通过 |
| B4 动作限幅被计数 | `umax=0.2` 时 16/50 步饱和，实测 `|u|≤0.2`，误差仍收敛 | 通过 |
| B5 增益投影 | 500 步内 k 始终在 [0.5,0.7]，集合内最大 ρ=0.20<1 | 通过 |

完整输出：`pi-lab/results/test-b.md`。

### 测试 C：算法对照 — **完成，结论对 π 不利**

设置：`a=0.9, b=1, k0=0.6, μ=0.02, ε=0.05, e0=1, horizon=200, settle_tol=0.02`；
每臂每场景 300 个独立种子，共 **3600 次运行**；同一环境、同一扰动分布、同一探索预算（每步一次探索信号）。

| 场景 | A 固定 | B 自适应无探索 | C 自适应+随机 | D 自适应+π |
|---|---|---|---|---|
| 无扰动 RMSE | 0.0222 | 0.0222 | 0.0568 | **0.0593** |
| 均匀扰动 0.1 | 0.0643 | 0.0641 | 0.0828 | **0.0845** |
| 正弦扰动 0.1 | 0.1024 | 0.0993 | 0.1116 | **0.1129** |

D 相对 C：+0.00245 [+0.0023, +0.0026]、+0.00168 [+0.0011, +0.0023]、+0.00128 [+0.0008, +0.0017]。
**三个场景里 π 探索都显著差于随机探索，更差于无探索。**
参考线（不属于四臂）：已知最优固定增益 k=0.9 的 RMSE 分别为 0.0000 / 0.0576 / 0.0707 ——
说明在这个模型里，**“找到好增益”比“持续探索”重要得多**。

原因经实验定位（见测试 C 补充研究）：`frac(nπ)` 的二值化序列是**准周期方波**，
`7π≈21.9911`、`113π≈354.99997`，导致 lag 7 有 98.23% 位相同、lag 113 有 99.99% 位相同。
它不会像随机符号那样在多次试验中相互抵消，而是给闭环注入了一个相干偏置。

### 测试 C 补充：π 信号到底是什么

| 指标（n=1..100000） | 值 |
|---|---|
| σ=+1 / −1 次数 | 49998 / 50002（正号率 0.49998） |
| 最长同号游程 | 4 |
| 累计和 `|Σσ|` 最大值 | 154（亚扩散，不是随机游走也不是有界） |
| lag 1 自相关 | +0.4336（随机 ±1 为 −0.0065） |
| lag 7 一致率 | 98.23% |

**辨识实验**（`y=b·u+w`，RLS 估 b=1.3，180 步，300 次重复）：
无激励误差 0.0345、随机 ±1 误差 0.0017、π ±1 误差 0.0016。
即：**π 激励足以支撑参数辨识，但没有证据优于随机激励**（差异在噪声量级）。

**替代方案**（实验室，未发货）：用黄金比 φ=(√5−1)/2 生成同结构的 ±1 激励，
把 RMSE 从 0.0593 降到 0.0506（无扰动）、0.0845 降到 0.0789（均匀扰动），
且 lag 7 一致率从 98% 降到 34.8%。但 φ 序列**同样不是白噪声**（lag 4 自相关 −0.89）；
结论是“相位低差异 ≠ 符号白噪声”，这条区分已写入实验室报告。

完整输出：`pi-lab/results/test-c.md`、`signal-study.md`、`golden-study.md`。

### 测试 D：Harness 兼容性 — **大部分验证**

| 项 | 结果 |
|---|---|
| 新预设正常加载 | ✅ `include:preset-pi` active；`Config.listConfigs` 返回其 schema |
| 工具可调用 | ⚠️ 单元测试通过（15/15），但未在真实 π 会话中调用过 |
| 已有预设完整 | ✅ `standard/ptc/minimal/cordis` 仍全部 active |
| 不影响其他会话 | ✅ 本会话（standard）的 `Tool.listTools` 中**没有** `pi_control`/`pi_guard` |
| 异常安全处理 | ✅ 非法预算 → 挂载失败并报错；会话快照缺失 → `provenance: unavailable`；越界参数 → 明确报错 |
| 权限范围 | ✅ 未授予插件管理/市场工具；预算不可由模型修改 |
| 无后台失控 | ✅ 插件无定时器、无 spawn、无循环；扫描窗口上限 5000 事件 |
| 会话日志可追踪 | ✅ 实测 150 条 `tool/call`、149 条 `tool/result`，字段形状匹配 |

---

## 6. 依赖清单

预设不引入任何 npm 依赖；`package.json` 无 `dependencies`。它引用的是**随 Harness 发布的插件**：

| 包 | 行 | 版本 |
|---|---|---|
| `@deepseek-ai/dsh-agent-preset` | `preset-pi` | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-persona` | `persona` | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-agent-instructions` / `dsh-time-context` | 上下文 | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-tool-pwsh` / `dsh-tool-bash` | 执行 | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-tool-fs` / `dsh-tool-fs-search` / `dsh-tool-jobs` | 文件与作业 | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-tool-todo` / `dsh-tool-goal` / `dsh-command-goal` / `dsh-tool-ask-user` | 规划 | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-tool-web` / `dsh-skill-filesystem` / `dsh-tool-skill` / `dsh-tool-present` / `dsh-tool-schedule` | 研究与交付 | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-compaction-basic` / `dsh-command-compact` / `dsh-compaction-tool-result-pruner` | 上下文治理 | 0.2.1-rc.2 |
| `@deepseek-ai/dsh-tool-subagent` / `dsh-tool-subagent-control` | 委派 | 0.2.1-rc.2 |
| `@local/dsh-pi-preset/control`、`/selfcheck` | 自定义 | 本仓库 |

兼容性：预设只使用公开扩展点（工具注册、persona section、bundle patch），没有私有 API；
`control.js` 只依赖 `node:` 内置模块，不 import 任何 `@deepseek-ai/*`，因此不受包解析路径影响。

---

## 7. 使用说明与三个示例任务

**安装后**：在 `http://127.0.0.1:65233` 新建会话 → 预设选择器 → 选择 **π**。

**示例 1（Assist）**
> 用 π，在这个工作区把 `pi-lab/experiment.py` 的 `TRIALS` 从 300 提到 1000 跑一遍，比较两次的置信区间宽度，并给出是否改变结论的判断。

预期行为：todo 建三步 → 改文件 → 前台跑实验（`job` 或直接命令）→ 读结果 → 与基准（原 CI）比较 → 结论标注“测量”。

**示例 2（Simulate）**
> 用 pi_control 对比 a=1.1, b=1 下固定 k=1.0 与自适应 k0=0.4 的表现，扰动取 sine 0.2，给 200 步，解释你看到的差异。

预期行为：调 `simulate` 两次 → 引用 RMSE/ρ/饱和数 → 指出 ρ>1 的含义 → 明确声明“单次运行不代表一般结论”。

**示例 3（Guard）**
> 故意让同一条命令失败三次，然后告诉我 pi_guard 看到了什么。

预期行为：连续三次 `tool/result.isError=true` → `pi_guard status` → `verdict: stop`、规则 `consecutive-failures`、最后错误文本 → 停止并总结，不重试。

---

## 8. 状态矩阵（严格区分）

### 已实现
- 可加载、可挂载的 π Agent Preset（21 行），注册进运行时预设清单。
- 完整中文系统提示词（2378 字符），含模式、循环、红线、诚实条款。
- `pi_control`（signal / step / simulate / gain_scan）与 `pi_guard`（status / record）两个工具。
- 激活审计日志、bundle 清单、locale、图标、README。
- 独立 Python 参考实现 + 跨语言一致性校验工具链。

### 已测试（有真实输出）
- 15 项单元测试全通过；171 项跨语言断言 0 不符。
- 测试 B 的 5 项数学检查。
- 测试 C 的 3 场景 × 4 臂 × 300 种子（3600 次运行）与 bootstrap 置信区间。
- π 信号性质（平衡、游程、自相关、近周期）与 RLS 辨识对照。
- 挂载真实性（审计日志）、预设互不影响（工具列表隔离）、会话日志字段形状（871 事件）。

### 仅理论成立
- `|a−bk|≤ρ<1` 的稳定性结论只对一阶线性模型成立；对“任意 AI 工作流”无效，提示词已明示。
- `z=π+e` 不改变稳定性（只是坐标平移）。
- 用 π 序列做“受控探索”在需要**持续激励**的辨识任务里理论可行（RLS 实验支持），但在本闭环里没有优势。

### 尚未实现 / 未验证
- ❌ 与 π 的真实对话（从会话内无法创建 π 会话；无浏览器控制，未做截图级确认）。
- ❌ UI 选择器的目视确认（运行时层面已证明注册与挂载）。
- ❌ RLS 在线估计未进入工具（仅实验室）。
- ❌ φ 替代激励未发货（实验室结论）。
- ❌ π 会话内的 skill 加载、子 Agent 委派、后台作业未实测。
- ⚠️ 激活日志证明“挂载成功”，不证明“模型按提示词行事”。

---

## 9. 风险与限制

1. **π 探索有害（已实测）**：在无辨识需求时，D 臂的 RMSE 比同场景最优臂高 13.7%（正弦）到 167%（无扰动）。默认模式（Assist）不主动使用；只有 Simulate 才建议用。
2. **重复检测的 160 字符截断**：日志中 `arguments` 是原始 JSON 文本，两条长命令若前缀完全相同可能被误判为重复；后果是一条 `stop` 建议，不是硬阻断。
3. **`pi_guard` 读到的是本会话历史**：fork/子会话有各自的日志；跨会话总预算未做。
4. **每个进程激活一次**：审计日志不是每次会话一条。
5. **预设不是安全沙箱**：YAML 与插件可以执行 Host 代码（registry 官方限制）。π 的价值在于“没有自改工具”，不是“无法被改”。
6. **单会话内的预算是最软的一环**：模型可以无视 `stop` 建议继续调用；真正硬性的只有 Harness 的权限与审批。
7. **撤销方式**：`remove_bundle` 后预设立即从花名册消失；已存在的 π 会话需要重建（其日志记录了 `agent-preset/selected`）。

---

## 10. π 是否已出现在预设选择列表？

**是。**

运行时证据链：
1. `plugin_manager list_plugins` → `include:preset-pi`，`fiberPhase: active`；
2. `Config.listConfigs(name=@deepseek-ai/dsh-agent-preset)` → 5 行：standard、ptc、minimal、cordis、**pi**；
3. 组合内部真实挂载：最后一行自检插件在 Host 进程内执行并落盘审计日志；
4. 其余 4 个预设仍全部 active，且 π 的工具没有泄漏到其他预设。

**未做**：截图级的 UI 目视确认。请新建会话打开预设选择器，应看到 **π**（第 5 位，Creator 之后）。
若没有出现，请把该页面截图或 `plugin_manager list_plugins` 的 `preset-pi` 行状态发我，我据此修复。

### 重启后是否还在

结构性证据（不是推测）：

- profile 的 `package.json` 已写入依赖 `"@local/dsh-pi-preset": "link:D:/π/pi-preset"`；
- `dsh.profile.bundles` 顺序为 `dsh-base → dsh-web-app → @local/dsh-pi-preset`，即 π 的 patch 是最后一层；
- `node_modules/@local/dsh-pi-preset` 是指向 `D:\π\pi-preset` 的 Junction，通过它能读到 `cordis.patch.yml` 与 `control.js`；
- 因此下次启动会重新组合出 `preset-pi`，并在 `D:/π/logs/pi-preset-activation.jsonl` 追加一条新的 `activated`。

我没有重启进程（那会终结当前会话），所以“重启后可见”属于**机制上必然、但未在本机实测**的一项；
日志文件本身就是为了让这条结论在下次启动时可以被一眼证实。

默认预设未被改动：registry 的 `default` 仍是原值，π 只是新增选项，不会自动替换任何人的默认。
