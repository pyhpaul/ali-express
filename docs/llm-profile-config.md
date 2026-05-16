# LLM Profile Configuration Guide

## 目标

多个项目、Windows、WSL、云服务器共用同一套 LLM 配置协议：

- 项目只选择 profile，不保存明文 API key。
- profile 描述用途、base URL、模型，以及 `api_key` 或 `api_key_env`。
- 机器本地全局 profile 可以直接保存 API key；仓库内模板仍建议使用 `api_key_env`。

## 当前项目用法

当前项目 `.env` 推荐只保留：

```dotenv
ALI_MVP_LLM_PROFILE=cheap-review
ALI_MVP_LLM_MODEL=gpt-5.4
```

`ALI_MVP_LLM_MODEL` 是项目级覆盖项；如果不写，则使用 profile 里的 `model`。

## Profile 文件位置

解析顺序：

1. `LLM_PROFILES_PATH`
2. Windows: `%USERPROFILE%\.config\llm-profiles\profiles.toml`
3. WSL/Linux: `~/.config/llm-profiles/profiles.toml`
4. Linux server fallback: `/etc/llm-profiles/profiles.toml`

建议每个环境各自维护实际 profile 文件。不要让 WSL 或云服务器依赖 Windows 路径。

## Profile 文件格式

```toml
default_text_profile = "cheap-review"
default_image_profile = "gpt-image"

[profiles.cheap-review]
provider = "openai-compatible"
base_url = "https://sub2.de5.net"
api_key = "sk-local-only"
# 或者改成：
# api_key_env = "OPENAI_DEV_API_KEY"
model = "gpt-5.4"

[profiles.gpt-dev]
provider = "openai-compatible"
base_url = "https://sub2.de5.net"
api_key = "sk-local-only"
model = "gpt-5.5"

[profiles.gpt-image]
provider = "openai-compatible"
base_url = "https://sub2.de5.net"
api_key = "sk-local-only"
model = "gpt-image-2"
```

当前项目只读取：

- `base_url`
- `api_key`
- `api_key_env`
- `model`
- `provider`

先不要在 profile 里加入未被项目读取的字段。等有共享 LLM SDK、图片生成或多协议路由需求时，再扩展 `wire_api`、`capabilities` 这类元数据。

## API key 配置

当前支持两种写法：

### 方案 A：机器本地全局 profile 直接存 `api_key`

适合当前这台机器自己用的 `%USERPROFILE%\.config\llm-profiles\profiles.toml`：

```toml
[profiles.cheap-review]
provider = "openai-compatible"
base_url = "https://sub2.de5.net"
api_key = "sk-local-only"
model = "gpt-5.4"
```

这个文件不要提交到仓库。

### 方案 B：profile 只存 `api_key_env`

适合需要跨 Windows / WSL / 服务器复用同一份模板，或不想把 key 放进 profile 文件时：

```toml
api_key_env = "OPENAI_DEV_API_KEY"
```

当同一个 profile 同时写了 `api_key` 和 `api_key_env` 时，当前实现优先使用 `api_key`。

### Windows PowerShell

若使用 `api_key_env`，持久写入当前 Windows 用户环境变量：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_DEV_API_KEY", "你的key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_IMAGE_API_KEY", "你的图片key", "User")
```

新开的 PowerShell/Codex 会话会读取新值。

### WSL

若使用 `api_key_env`，写入 `~/.profile`、`~/.bashrc` 或 `~/.zshrc`：

```bash
export OPENAI_DEV_API_KEY="你的key"
export OPENAI_IMAGE_API_KEY="你的图片key"
```

只在 shell 里临时执行 `export` 不会持久化；`wsl --shutdown` 后会丢失。写入 shell 启动文件后，重启 WSL 仍会加载。

### 云服务器

推荐按部署方式注入：

- systemd: `EnvironmentFile=/etc/<app>/app.env`
- Docker: `env_file` 或 Docker secrets
- Kubernetes: Secret
- CI/CD: 平台 secrets

生产环境可以放：

```bash
ALI_MVP_LLM_PROFILE=prod-review
LLM_PROFILES_PATH=/etc/llm-profiles/profiles.toml
OPENAI_PROD_API_KEY=...
```

对应 profile：

```toml
[profiles.prod-review]
provider = "openai-compatible"
base_url = "https://provider.example.test"
api_key_env = "OPENAI_PROD_API_KEY"
model = "gpt-5.5"
```

## 其他项目接入规则

推荐每个项目遵守同一优先级：

1. CLI 显式参数。
2. 项目专属显式环境变量，例如 `ALI_MVP_LLM_BASE_URL` / `ALI_MVP_LLM_API_KEY` / `ALI_MVP_LLM_MODEL`。
3. 项目 `.env` 里的 profile 选择，例如 `ALI_MVP_LLM_PROFILE=cheap-review`。
4. 全局 profile 文件。
5. 标准 fallback：`OPENAI_BASE_URL` / `OPENAI_API_KEY` / `OPENAI_MODEL`。

项目仓库可以提交 `config/llm-profiles.example.toml` 作为模板，但不要提交真实 `profiles.toml` 或 API key。

不要让项目运行时直接依赖 `~/.codex/auth.json` 这类工具内部文件；如果要复用其中的 key，建议一次性同步到你自己的全局 `profiles.toml`。

## Profile 命名建议

按用途命名，不按模型名命名：

- `cheap-review`: 批量低成本 JSON 审核。
- `gpt-dev`: 日常开发、推理、工具调用。
- `gpt-image`: 图片生成。
- `prod-review`: 生产审核。
- `local-qwen`: 本地模型备用。

同一个 GPT 模型如果有多个 endpoint/key，也应拆成多个 profile。
