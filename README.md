# π · Pi Adaptive Controller

一个**自适应控制型 Agent Preset**：把控制系统里的"观测 → 比对基准 → 执行 → 读反馈 → 在安全边界内调整"搬进 AI Agent 的工作循环，并暴露两个模型可直接调用的工具，让每一步判断都基于可测量的数值，而不是语言上的自信。

> 一句话立场：**收敛靠反馈回路，不靠自信。**

## 两个模型可见工具

| 工具 | 动作 | 作用 |
|---|---|---|
| `pi_control` | `signal` / `step` / `simulate` / `gain_scan` | 用精确整数运算给出确定性序列 `r(n) = frac(n·π)`；推进一阶闭环 `e(t+1) = a·e(t) − b·u(t) + w(t)` 单步；按策略（fixed / adaptive / adaptive_random / adaptive_pi）跑完整仿真并返回实测指标（rmse、稳定步数、控制量、饱和次数）；解析求解满足 `\|a − b·k\| ≤ ρ` 的增益区间 |
| `pi_guard` | `status` / `record` | 读取本会话真实的工具事件，统计调用负载、相同调用重复次数、连续失败、工具名振荡，返回 `ok` / `warn` / `stop` 与触发的具体规则；预算由预设配置固定，Agent 无法自行放宽 |

两者都是零依赖实现，`control.js` 不引入任何第三方包。

## 仓库结构

| 路径 | 内容 |
|---|---|
| `pi-preset/` | 预设 bundle：`cordis.patch.yml`（21 行组合声明，含完整系统提示词）、`control.js`（两个工具的实现）、`selfcheck.js`（挂载审计）、`locale/`、`icon.svg` |
| `pi-lab/` | `pi_model.py` 数学控制器独立 Python 参考实现；`experiment.py`（数学控制 + 四臂对照）；`signal_study.py` / `golden_study.py`（π 信号性质与 φ 替代方案）；`crosscheck.py` + `emit_js.mjs`（JS↔Python 逐点一致性校验）；`results/` 全部原始结果 |
| `tests/` | `control.test.mjs`：15 项单元测试，直接跑在预设挂载的同一个模块上 |
| `REPORT.md` | 完整交付报告：环境核查、交付物清单、系统提示词全文、测试结果、状态矩阵、风险与限制 |

## 快速开始

```bash
# 单元测试（仅需 Node.js ≥ 18，无第三方依赖）
node --test tests/control.test.mjs
```

预设本身的安装依赖 DSH Harness 环境，见 [`pi-preset/README.md`](pi-preset/README.md)。`cordis.patch.yml` 引用 `@deepseek-ai/dsh-*` 系列包，**脱离 DSH Harness 无法加载**；可独立复用和阅读的是 `control.js`、`pi-lab/` 与 `tests/`。

## 请先读这一节：我们的实验结论是否定性的

这个项目最有价值的部分可能不是它提出了什么，而是它**如实记录了没成立的部分**：

- 四臂对照实验（3600 次运行）的结论是：在这套一阶模型里，**π 确定性探索不如无探索，也略差于随机探索**。
- `r(n) = frac(n·π)` 是**确定性序列，不是随机数**，在没有配对重复实验的统计证据前，不宣称它带来任何探索优势。
- 稳定性结论 `|a − b·k| ≤ ρ < 1` 只对**被建模的一阶系统**成立，不能推广到真实 AI 工作流。
- 单次实验只报告这一次的结果；跨策略比较必须同环境、同扰动、同预算做配对重复试验。

上述结论的证据与原始数据见 [`REPORT.md`](REPORT.md) 第 5 节与 `pi-lab/results/`。

## 已经验证到什么程度

严格区分（详见 `REPORT.md` 第 8 节状态矩阵）：

- **已实现**：预设 bundle、两个工具、Python 参考实现、单元测试、实验脚本。
- **已测试**：`tests/control.test.mjs` 15/15 通过（`node --test`，Node v24，约 134 ms），断言覆盖工具注册、稳定性判据、单步方程、四策略确定性、`gain_scan` 解析区间、`pi_guard` 的 warn/stop 语义与日志缺失时的降级行为。
- **未在本仓库复现**：`pi-lab/` 的 Python 实验需要 Python 3 环境，本仓库只提供脚本与**原始结果文件**，不保证在任意环境复跑出相同数值；`REPORT.md` 中的数值来自原作者环境的实际运行。
- **仅理论成立**：把一阶控制律的稳定性结论迁移到多步、非线性的 Agent 工作流——这是类比，不是定理。

## 许可证

[MIT](LICENSE)。可自由使用、修改、商用、再分发，保留版权声明即可。
