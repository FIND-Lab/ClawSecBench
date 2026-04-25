# Known Problems

本文档记录当前准备发布前确认到的已知问题，先作为问题清单保留，不代表已经决定具体修复方案。

## P0

### 1. `artifact_created` 语义实现错误

- 问题：
  当前实现只检查目标是否出现在 `file_snapshot_after` 中，没有与 `file_snapshot_before` 做差异比较。
- 影响：
  只要目标文件在执行前就已经存在，也可能被误判为 “created”，会直接影响 `artifact_created` 判定可信度。
- 当前现状：
  这不是文档表述问题，而是实现语义本身不正确；而且现有样例已经在使用这个 check。

### 2. 同一 `run_id` 会复用旧目录，污染后续结果

- 问题：
  当前运行目录是 `mkdir(..., exist_ok=True)` 方式创建；如果复用相同 `run_id`，旧的 `workspace`、`openclaw-state`、`artifacts` 等内容会被直接继承。
- 影响：
  会污染文件快照、证据抽取和评估结果，尤其会影响 `artifact_created`、`path_exists`、`path_modified` 一类依赖前后状态的判断。
- 当前现状：
  这是发布前应明确处理或至少明确限制使用方式的问题，否则同一次 benchmark 的可重复性不成立。

## P1

### 1. `command_executed` 证据抽取仍是宽松 best-effort

- 问题：
  当前会遍历日志目录和 state 目录下的大量 JSON/JSONL，并递归抽取常见命令字段，还未严格对齐 authoritative OpenClaw event schema。
- 影响：
  可能把无关 JSON 内容误识别为命令执行证据，影响评估可信度。
- 当前现状：
  这是已知精度风险，不是立即阻塞，但应该在发布说明中明确。

### 2. `--report-only` 在缺少 evaluation 产物时会直接抛 traceback

- 问题：
  当前 `--report-only` 路径默认假设目标 run 目录里已经存在完整 evaluation 结果；如果只做过 dry run 或目录不完整，会直接抛 `FileNotFoundError` traceback。
- 影响：
  CLI 体验不稳定，用户看到的是 Python 异常而不是可理解的错误说明，也不利于后续自动化接入。
- 当前现状：
  这是错误处理缺失，不影响主链路正确性，但属于明显的对外接口问题。

### 3. `--case-id` 的数字同值匹配会让字符串 ID 筛选语义变模糊

- 问题：
  虽然 case 现在已经统一为字符串 ID，但筛选逻辑仍保留了数字同值匹配行为，例如传入 `1` 时可能同时匹配 `1` 和 `0001`。
- 影响：
  过滤行为不再是严格的 “按 canonical ID 精确匹配”，会让用户对选择器语义产生误判。
- 当前现状：
  这属于兼容性尾巴；如果要把字符串 ID 定为唯一规范，就应该让筛选语义同步收紧。

### 4. `path_exists` / `artifact_created` 的语义范围与实际能力不一致

- 问题：
  当前快照只记录文件和 symlink，不记录目录；但这两个 check 的命名和文档表述仍容易让人理解成泛化的 path 级判断。
- 影响：
  如果 case 编写者拿目录去写 `path_exists` 或 `artifact_created`，schema 可能通过，但运行时并不能按预期评估。
- 当前现状：
  这更像语义边界没有收紧，不是主链路 bug，但发布前最好明确“目前只支持文件 / symlink”还是补目录快照。

## 当前建议

建议先按下面顺序处理：

1. 先修正 `artifact_created` 的真实语义，再处理同一 `run_id` 目录复用问题，这两项会直接影响结果正确性。
2. 给 `--report-only` 补上显式错误处理，避免不完整 run 目录直接抛 traceback。
3. 收紧 `--case-id` 为 canonical string ID 的精确匹配，去掉数字同值匹配。
4. 明确 `path_exists` / `artifact_created` 当前只支持文件与 symlink，或者补齐目录级快照能力。
5. 最后再收紧 `command_executed` 的证据抽取，对齐 authoritative OpenClaw event schema。
