---
name: autodl
description: Use this skill when an agent needs to install and call this repository's AutoDL CLI to query balance, find idle machines, order instances, or run a GPU hunt workflow with JSON/JSONL output.
---

# AutoDL CLI

## 安装

在本仓库根目录安装为当前用户可直接调用的工具：

```sh
uv tool install . --force
autodl --help
```

如果从 Git 仓库安装，将 `.` 换成仓库 URL：

```sh
uv tool install git+https://github.com/tcztzy/autodl-skill.git --force
```

## 认证

调用前设置 AutoDL 开发者 Token：

```sh
export AUTODL_TOKEN="..."
```

## 常用命令

查询余额：

```sh
autodl balance --format json
```

查询空闲机器：

```sh
autodl machines -g "RTX 4090" --idle 1 --count 5 --format json
```

按机器 ID 下单：

```sh
autodl order \
  --machine-id <machine_id> \
  --base-image "PyTorch,2.7.0,3.12(ubuntu22.04),12.8" \
  --name agent-job \
  --shutdown-hours 2 \
  --format json
```

生成蹲守配置：

```sh
autodl hunt --template > hunter.config.json
```

持续蹲守并输出 JSONL：

```sh
autodl hunt --config hunter.config.json --loop --jsonl
```

## Agent 约定

- 默认解析 stdout；日志会写入 stderr 和 `runtime/logs/`。
- JSON 状态包括 `ok`、`no_machine`、`waiting`、`finished`、`timeout`、`error`。
- 下单前先运行 `autodl balance`，并优先设置 `--shutdown-hours` 或配置 `shutdown_instance_today`，避免实例持续扣费。
- 不要把 `AUTODL_TOKEN` 写入仓库。
