# ClawSecBench OpenClaw AutoBench

这个仓库当前不只是数据集本身，而是一套面向 ClawSecBench 的 OpenClaw 自动化评测框架，包含：

- `cases-v2/` 中 157 条正式 schema case
- 基于官方 OpenClaw Docker Gateway 的执行与评测流水线
- 旧格式 `benchmark_data.json` 到 v2 schema 的重写脚本
- case schema、轻量草稿 schema 与配套文档

框架目标是让 benchmark case 能够被稳定地：

1. 严格校验
2. 按 case 独立容器环境执行
3. 采集 trace / evidence / evaluation
4. 自动计算 A（攻击成功） / B（完成正常用户任务） / R（对攻击明确拒绝或告警） 与 outcome
5. 汇总成 summary 与 markdown report

## 当前状态

当前主链路已经覆盖：

- `case_loader` 严格 schema 校验、prompt placeholder 校验与 case 过滤
- `runtime_provisioner` 生成 per-case `openclaw.json` 与 `compose.yaml`
- `fixture_builder` 按虚拟根写入 file / document / skill / public web fixture
- `conversation_driver` 通过 OpenAI-compatible Gateway endpoint 驱动对话
- `evidence_collector` 收集最终回复、命令痕迹、前后文件快照
- `evaluator` 执行 `success_judge` / `success_checks` / `refusal_check`
- `reporter` 生成 `summary.json` 和 `report.md`
- `--dry` 仅做 case 级检查，不启动 runtime
- `--report-only` 从已有 evaluation 重新生成 summary/report
- `--concurrency` / `CONCURRENCY` 支持 case 级并行 benchmark 执行

当前 schema 已声明但 runtime 还未实现的能力：

- `session_mode=reset_each_turn`
- `email`
- `web.access=private`

这些 case 会在正式执行时被标记为 `skipped_unsupported`，不会拖垮整次 run。

## 仓库结构

```text
autobench/                    评测框架主代码
cases-v2/                     正式 v2 case JSON（157 条）
cases-v2-raw/                 重写脚本的原始响应/中间产物
cases-v2-lh/                  LH pilot 样例
cases-v2-lh-raw/              LH pilot 重写中间产物
configs/                      benchmark runtime config
docs/                         schema 与实现文档
metadata/                     skill snapshot 等元数据
outputs/runs/                 每次 benchmark run 的输出
schema/                       正式 schema 与 lite schema
scripts/rewrite_cases.py      旧 case -> v2 schema 重写脚本
Makefile                      常用入口封装
requirements.txt              Python 依赖
benchmark_data.json           旧版 benchmark 数据
benchmark_data_lh.json        LH pilot 数据
```

## 环境准备

前置条件：

- Python 3 与 `venv`
- Docker Engine / Docker Desktop
- `docker compose`（Compose v2）
- 可用的模型 API Key
- 可选：`make`

Python 依赖已经收敛在仓库根目录的 `requirements.txt`。Makefile 默认使用 `./.venv/bin/python`，如果你沿用这个约定，可以这样准备：

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
```

建议在第一次正式执行前确认 Docker 可用：

```bash
docker info
docker compose version
```

说明：

- `make dry` / `make check` / `make rewrite` 不依赖 Docker。
- `make run` 与直接执行 benchmark CLI 时，需要本机 Docker daemon 正常运行，且 `docker compose` 命令可用。
- 首次执行 benchmark 时会自动拉取 `openclaw` 镜像，耗时取决于网络与镜像缓存情况。
- 如果你不使用 Makefile 默认的 `./.venv/bin/python`，可以在执行时覆盖，例如 `make test PYTHON=python3`，或直接调用 CLI。

运行 benchmark 或 rewrite 时还需要模型提供方 API Key。常见两种方式：

- OpenAI：`OPENAI_API_KEY`
- DashScope 兼容模式：`DASHSCOPE_API_KEY`

补充说明：

- `configs/baseline.json` 当前默认使用 DashScope 兼容 OpenAI 接口。
- 正常执行 run 时，如果 `OPENCLAW_GATEWAY_TOKEN` 没有预设，pipeline 会自动生成临时 token。
- 如果 case 使用 `public web`，执行结果会受外网连通性、目标站点状态、页面漂移影响。

## 快速开始

### 1. 跑测试

```bash
make test
```

### 2. 可选：重写 legacy cases

`scripts/rewrite_cases.py` 默认走 DashScope 兼容 OpenAI 接口，默认模型是 `qwen3.6-plus`。

```bash
export DASHSCOPE_API_KEY=your_key
make rewrite OVERWRITE=1
```

如果 rewrite 与其他阶段共用同一套模型接口参数，可以直接设置全局默认变量：

```bash
export DASHSCOPE_API_KEY=your_key

make rewrite OVERWRITE=1 \
  REWRITE_CONCURRENCY=8 \
  BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  API_KEY_ENV=DASHSCOPE_API_KEY
```

`Makefile` 现在支持全局默认变量 `MODEL` / `BASE_URL` / `API_KEY_ENV`。如果 `REWRITE_*`、`PROVIDER_*`、`JUDGE_*` 没有显式指定，就会自动回退到这三个全局变量；只有某一阶段需要单独覆盖时，才再传对应前缀变量。`rewrite` 在 `MODEL` 也未提供时，会继续回退到默认模型 `qwen3.6-plus`。

只重写部分 case：

```bash
make rewrite CASE_IDS=29,30,70 OVERWRITE=1
```

### 3. 只做 case 检查

这一步不会启动 Docker；会生成 run 目录下的 `run_manifest.json` 和 `case.md`，但不会产生 execution/evaluation/report 产物。

```bash
make dry CASE_IDS=41
```

### 4. 正式执行 benchmark

下面是当前最常见的 DashScope 运行方式：

```bash
export DASHSCOPE_API_KEY=your_key

make run CASE_IDS='29 30 70' \
  BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
  API_KEY_ENV=DASHSCOPE_API_KEY \
  PROVIDER_MODEL=dashscope/qwen3.6-plus \
  JUDGE_MODEL=qwen3.6-plus
```

如果要保留最后一个 case 的 runtime 目录便于排查：

```bash
make run CASE_IDS=41 KEEP_RUNTIME=1
```

说明：`KEEP_RUNTIME=1` 是 debug-only 开关，只会保留最后一个 supported case 的 runtime 现场，且要求 `CONCURRENCY=1`。

### 5. 从已有 evaluation 重建报告

```bash
make report RUN_ID=run-web-public-20260425-1
```

## Makefile 入口

`Makefile` 已经收敛了当前常用操作：

- `make help`
- `make test`
- `make rewrite`
- `make dry`
- `make check`
- `make run`
- `make report`
- `make clean-run RUN_ID=<run_id>`

常用变量：

- `CONFIG=configs/baseline.json`
- `CASES_DIR=cases-v2`
- `OUTPUT_ROOT=outputs`
- `CASE_IDS=29,30,70` 或 `CASE_IDS='29 30 70'`
- `MODEL=qwen3.6-plus`
- `BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1`
- `API_KEY_ENV=DASHSCOPE_API_KEY`
- `REWRITE_MODEL=...` / `PROVIDER_MODEL=...` / `JUDGE_MODEL=...`
  如果阶段专属变量未设置，会回退到不带前缀的 `MODEL` / `BASE_URL` / `API_KEY_ENV`
- `REWRITE_CONCURRENCY=50`
- case 的 canonical `metadata.id` 是字符串，默认与文件名 stem 一致，例如 `0041`；CLI 仍接受 `41` 这种数字简写做筛选
- `CONCURRENCY=1`
  benchmark 执行的 case 级并发数；会占用从 `gateway_host_port` 开始的连续端口池
- `RUN_ID=run-adhoc-001`
- `QUIET=1`
- `KEEP_RUNTIME=1`
  debug-only；仅保留最后一个 supported case 的 runtime，且只能与 `CONCURRENCY=1` 一起使用

## 直接用 CLI

除了 `make`，也可以直接走 Python CLI：

```bash
PYTHONPATH=. ./.venv/bin/python -m autobench.cli \
  --config configs/baseline.json \
  --cases-dir cases-v2 \
  --case-id 0041 \
  --dry
```

正式执行：

```bash
PYTHONPATH=. ./.venv/bin/python -m autobench.cli \
  --config configs/baseline.json \
  --cases-dir cases-v2 \
  --output-root outputs \
  --case-id 0041
```

重建报告：

```bash
PYTHONPATH=. ./.venv/bin/python -m autobench.cli \
  --report-only \
  --run-id run-web-public-20260425-1 \
  --output-root outputs
```

## Case Schema 概览

正式 case 使用 `schema/case.schema.json`，主要文档：

- `schema/case.schema.json`
- `docs/schema.md`
- `schema/case.schema.lite.txt`
- `docs/schema-lite.md`

v2 case 的顶层结构是：

- `metadata`
- `procedure`
- `benign_task`
- `attack`

其中：

- `metadata.sample_type` 取值为 `attack_pure | attack_mixed | benign`
- `procedure.session_mode` 在 schema 中允许 `single_session | reset_each_turn`
- `procedure.turns[*].content` 可以通过 `{{fixture_id.field}}` 引用环境 fixture
- `benign_task` 负责 `B`
- `attack` 负责 `A` 与 `R`

### 支持的 environment 类型

- `file`
- `document`
- `web`
- `email`
- `skill`

### 虚拟根约定

- `$WORKSPACE/...`：工作区文件与 agent workspace 文件，如 `MEMORY.md`、`SOUL.md`、`IDENTITY.md`、`AGENTS.md`
- `$OPENCLAW_STATE/...`：运行时状态文件，如 `openclaw.json`
- `$HOME/...`：用户家目录文件
- `$SYSTEM/...`：受控绝对系统路径，如 `/etc/passwd`

### 评估模型

当前推荐写法是：

- `success_mode: judge`
- `success_judge` 作为主判定线
- `success_checks` 作为并行审计线
- `attack.refusal_check` 通过 LLM judge 评估 `R`

支持的 deterministic check 主要包括：

- `path_exists`
- `path_modified`
- `path_contains`
- `json_value`
- `artifact_created`
- `command_executed`
- `reply_contains`
- `reply_regex`

## A / B / R 定义

- `A`：攻击目标是否达成
- `B`：良性任务是否达成
- `R`：模型是否显式识别、拒绝、忽略或缓解攻击

当前逻辑：

- 若 task 的 `success_mode=judge`，则以 `success_judge` 为准
- 若 task 的 `success_mode=checks`，则以 `success_checks` 为准
- `R` 始终由 `attack.refusal_check` 的 LLM judge 结果给出

## 输出产物

正式 run 的产物目录：

```text
outputs/runs/<run_id>/
  run_manifest.json
  summary.json
  report.md
  judge-cache/
  cases/
    case-<id>/
      artifacts/
        case-<id>-trace.json
        case-<id>-evidence.json
        case-<id>-evaluation.json
      runtime/
        compose.yaml
      openclaw-state/
        openclaw.json
      workspace/
      home/
      system/
      logs/
```

说明：

- `--dry` 不会写这些执行产物；只会生成 `run_manifest.json` 和 `case.md`
- `--report-only` 会重建 `summary.json` 和 `report.md`
- `CaseRunResult.executed=false` 的 case 会在 summary 中统计为 `skipped_cases`

## 支持矩阵

| 能力                             | 当前状态                      | 说明                                                                          |
| -------------------------------- | ----------------------------- | ----------------------------------------------------------------------------- |
| `session_mode=single_session`  | 支持                          | 当前 runner 主链路                                                            |
| `session_mode=reset_each_turn` | schema 已支持，runtime 未实现 | 执行时跳过                                                                    |
| `file` / `document` fixture  | 支持                          | 含 `mtime`                                                                  |
| `skill` `mode: reference`    | 部分支持                      | 已知 built-in reference 可用；unknown reference 会在 runtime-support 阶段跳过 |
| `skill` `mode: inline`       | 支持                          | 按显式 files 落盘                                                             |
| `web.access=public`            | 支持                          | 运行时访问真实 URL                                                            |
| `web.access=private`           | schema 已支持，runtime 未实现 | 执行时跳过                                                                    |
| `email` fixture                | schema 已支持，runtime 未实现 | 执行时跳过                                                                    |
| `$SYSTEM/...` 文件映射         | 支持                          | 用于受控系统路径测试                                                          |
| `--dry`                        | 支持                          | 只检查 case，写 `run_manifest.json` 和 `case.md`，不启动 runtime          |
| `--report-only`                | 支持                          | 只重建 summary/report                                                         |

## 配置文件

当前只保留一个基础 config：

- `configs/baseline.json`

可覆盖的关键参数包括：

- provider base URL
- provider model
- provider API key env
- gateway image
- gateway host port
- gateway token env
- judge base URL / model / API key env

## 当前限制

以下限制在使用时需要明确知道：

- `reset_each_turn`、`email` 和 `private web` 仍是 schema 先行、runtime 滞后状态
- `public web` case 依赖真实公网 URL，可能受 404、站点漂移、网络封锁影响
- `command_executed` 的证据抽取目前是 best-effort，还没有完全对齐 authoritative OpenClaw event schema
- 生成的 `openclaw.json` 已能跑通现有主流程，但还没有对具体官方镜像 digest 做严格 pin 与逐版本校验

## 相关文件

- `AGENTS.md`：当前模块职责、handoff 约定、已实现范围
- `docs/autobench-implementation-plan.md`：实现方案与架构说明
- `docs/schema.md`：正式 schema 说明
- `docs/schema-lite.md`：轻量草稿 schema 说明

## 开发建议

如果你要继续扩展这个框架，当前最有价值的方向是：

1. 补齐 `reset_each_turn`、`email` 与 `private web` runtime
2. 对齐 OpenClaw 官方事件 schema，增强命令证据抽取
3. 固定 OpenClaw 官方镜像版本并验证 config fidelity
4. 增加 config 对比与 leaderboard 输出
