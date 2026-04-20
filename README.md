# autodl

`autodl` 是面向脚本和 agent 的 AutoDL.com 命令行客户端。它把常见操作收敛成稳定 CLI：查询余额、查询可下单机器、创建按量实例、按配置持续蹲守 GPU，并默认输出 JSON，方便上层 agent 直接解析。

项目灵感来自 [autodl-gpuhunter](https://github.com/mfznttkx/autodl-gpuhunter)。

## 能力

- 查询账户余额，并返回元/厘（没想到吧，还有这个单位）两种金额字段。
- 查询当前可租机器，支持按区域、GPU 型号、空闲卡数、可扩容数据盘筛选。
- 按机器 ID 或首个可用匹配机器创建按量实例。
- 支持基础镜像、共享镜像、私有镜像选择。
- 支持扩容数据盘、创建多个实例、设置定时关机。
- 支持持续蹲守 GPU，输出 JSON 或 JSONL 事件流。

## 安装

本项目使用 Python 3.14+ 和 `uv`。

开发环境：

```sh
uv sync
uv run autodl --help
```

安装成当前用户可直接调用的工具：

```sh
uv tool install . --force
autodl --help
```

## 认证

先在 AutoDL 控制台获取开发者 Token，然后设置环境变量：

```sh
export AUTODL_TOKEN="你的开发者 Token"
```

也可以写入项目根目录的 `.env`：

```env
AUTODL_TOKEN=你的开发者 Token
```

## CLI 用法

查询余额：

```sh
autodl balance
autodl balance --raw
```

查询空闲机器：

```sh
autodl machines -g "RTX 4090" --idle 1 --count 5
autodl machines -g "RTX 4090" -r 西北B区 --min-disk-gb 100 --format json
```

按机器 ID 下单：

```sh
autodl order \
  --machine-id <machine_id> \
  --base-image "PyTorch,2.7.0,3.12(ubuntu22.04),12.8" \
  --name agent-job \
  --shutdown-hours 2
```

按条件查找首个可用机器并下单：

```sh
autodl order \
  -g "RTX 4090" \
  -r 西北B区 \
  --gpu-num 1 \
  --count 1 \
  --base-image "PyTorch,2.7.0,3.12(ubuntu22.04),12.8" \
  --disk-gb 100 \
  --shutdown-hours 2
```

生成蹲守配置模板：

```sh
autodl hunt --template > hunter.config.json
```

配置示例：

```json
{
  "region_names": ["西北B区"],
  "gpu_type_names": ["RTX 4090"],
  "gpu_idle_num": 1,
  "instance_num": 1,
  "base_image_labels": ["PyTorch", "2.7.0", "3.12(ubuntu22.04)", "12.8"],
  "expand_data_disk_gb": 100,
  "shutdown_instance_today": true,
  "shutdown_instance_after_hours": 0,
  "retry_interval_seconds": 30
}
```

执行一次蹲守：

```sh
autodl hunt --config hunter.config.json
```

持续蹲守并输出 JSONL：

```sh
autodl hunt --config hunter.config.json --loop --jsonl
```

限制最多尝试次数：

```sh
autodl hunt --config hunter.config.json --loop --jsonl --max-attempts 20
```

## 输出约定

所有命令默认输出 JSON。常见状态：

- `ok`：命令成功。
- `no_machine`：下单命令没有找到可用机器。
- `waiting`：蹲守还没完成，之后会继续重试。
- `finished`：蹲守目标已满足。
- `timeout`：达到最大尝试次数。
- `error`：命令失败，包含 `error_type` 和 `message`。

命令日志写入 `runtime/logs/`。命令输出写 stdout；日志会在 CLI 执行时转到 stderr，便于 agent 只解析 stdout。

## 配置

`autodl hunt` 可从 CLI、环境变量、`.env`、`runtime/data/config.json` 和 `--config` 指定的 JSON 文件读取配置。CLI 覆盖项和环境变量优先于配置文件；`--save-config` 会把合并后的配置写入 `runtime/data/config.json`。

常用环境变量示例：

```sh
export AUTODL_REGION_NAMES='["西北B区"]'
export AUTODL_GPU_TYPE_NAMES='["RTX 4090"]'
export AUTODL_GPU_IDLE_NUM=1
```

## 注意事项

- 本工具会创建 AutoDL 按量实例；下单前建议先查余额，并设置 `--shutdown-hours` 或 `shutdown_instance_today`。
- 请妥善保管 `AUTODL_TOKEN`，不要提交到 Git。
- AutoDL 后台接口可能变化；如果返回结构变化，需要同步更新客户端解析逻辑。

## 开发检查

提交 Python 变更前运行：

```sh
uv run ruff format --check src/autodl
uv run ruff check src/autodl
uv run ty check src/autodl
```
