# LLM Profile Configuration Guide

## 目标

多个项目、Windows、WSL、云服务器共用同一套 LLM 配置协议：

- 项目只选择 profile，不保存明文 API key。
- profile 描述用途、base URL、模型和密钥环境变量名。
- 真正的 API key 只放在当前运行环境的环境变量或 secret manager 中。

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
api_key_env = "OPENAI_DEV_API_KEY"
model = "gpt-5.4"

[profiles.gpt-dev]
provider = "openai-compatible"
base_url = "https://sub2.de5.net"
api_key_env = "OPENAI_DEV_API_KEY"
model = "gpt-5.5"

[profiles.gpt-image]
provider = "openai-compatible"
base_url = "https://image-api.example.test"
api_key_env = "OPENAI_IMAGE_API_KEY"
model = "gpt-image-2"
```

当前项目只读取：

- `base_url`
- `api_key_env`
- `model`
- `provider`

先不要在 profile 里加入未被项目读取的字段。等有共享 LLM SDK、图片生成或多协议路由需求时，再扩展 `wire_api`、`capabilities` 这类元数据。

## API key 配置

Profile 文件不要写真实 API key，只写环境变量名：

```toml
api_key_env = "OPENAI_DEV_API_KEY"
```

### Windows PowerShell

持久写入当前 Windows 用户环境变量：

```powershell
[Environment]::SetEnvironmentVariable("OPENAI_DEV_API_KEY", "你的key", "User")
[Environment]::SetEnvironmentVariable("OPENAI_IMAGE_API_KEY", "你的图片key", "User")
```

新开的 PowerShell/Codex 会话会读取新值。

### WSL

写入 `~/.profile`、`~/.bashrc` 或 `~/.zshrc`：

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

## Profile 命名建议

按用途命名，不按模型名命名：

- `cheap-review`: 批量低成本 JSON 审核。
- `gpt-dev`: 日常开发、推理、工具调用。
- `gpt-image`: 图片生成。
- `prod-review`: 生产审核。
- `local-qwen`: 本地模型备用。

同一个 GPT 模型如果有多个 endpoint/key，也应拆成多个 profile。
