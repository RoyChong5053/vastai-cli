# Setup & Deployment Notes — Qwen3.6-27B-VL on VastAI

## Architecture (current)

```
┌─ 租机阶段 ────────────────────┐    ┌─ 跑模型阶段 ──────────────────────┐
│ vastai search / create        │    │ qwen36-27B-12GB.sh (纯 Bash)      │
│ (Python + venv, 偶尔用)        │───▶│   curl + API key → 拿 SSH info    │
│                                │    │   SSH → build / download / run    │
└────────────────────────────────┘    │   SSH -L → forward + monitor     │
                                      └──────────────────────────────────┘
```

**关键变化**：跑模型脚本不再依赖 Python/venv，只用系统自带的 `bash curl ssh`。

## Scripts

| 文件 | 用途 | 依赖 |
|------|------|------|
| `qwen36-27B-12GB.sh` | 12GB VRAM (RTX 3060) | bash, curl, ssh |
| `qwen36-27B-8GB.sh` | 8GB VRAM (no-kv-offload, 256k ctx) | 同上 |
| `qwen36-27B-24GB.sh` | 24GB VRAM (全层 offload, 多 slot) | 同上 |
| `qwen36-vl.sh` | (legacy 旧版，留作参考) | 同上 |

每个脚本自包含：检测实例 → 条件编译 → 下载模型 → 启动 server → 转发 → 监控。

## 核心设计

### API 替代 vastai CLI

```bash
# 读取 API key
API_KEY=$(cat ~/.config/vastai/vast_api_key)

# 获取实例列表
curl -sL "https://console.vast.ai/api/v0/instances?owner=me&api_key=${API_KEY}"
# 返回: {"instances_found": 1, "instances": [{...}]}

# 附加 SSH key
curl -sL -X PUT -H "Authorization: Bearer ${API_KEY}" \
  "https://console.vast.ai/api/v0/instances/${ID}/ssh/" \
  -H "Content-Type: application/json" \
  -d '{"ssh_key": "ssh-ed25519 ..."}'

# 停止实例
curl -sL -X PUT -H "Authorization: Bearer ${API_KEY}" \
  -d '{"state":"stopped"}' \
  "https://console.vast.ai/api/v0/instances/${ID}/"

# 销毁实例
curl -sL -X DELETE -H "Authorization: Bearer ${API_KEY}" \
  "https://console.vast.ai/api/v0/instances/${ID}/"
```

### 条件编译

脚本检测远端是否存在 `llama-server`，若缺失则自动：
1. `apt-get install build-essential cmake git`
2. `git clone --depth=1` llama.cpp
3. `cmake -DGGML_CUDA=ON`（失败则 fallback CPU）
4. `cmake --build --target llama-server`

设置 `FORCE_REBUILD=1` 可强制重编。

### 可开关的 flag 系统

所有 llama-server 的 feature 通过变量控制：

```bash
# 按需求开关
# NO_KV_OFFLOAD=1      # KV cache on CPU（省显存，慢）
# REASONING="on"        # 推理模式
# CACHE_REUSE=256       # KV 缓存复用
# MLOCK=1               # 锁内存
# SPEC_DRAFT_N_MAX=2    # MTP 投机解码
```

## 不同 VRAM 配置参考

| 文件 | VRAM | CTX | NGL | key cache | KV offload | PARALLEL |
|------|------|-----|-----|-----------|------------|----------|
| 8GB | 8 GB | 262144 | 28 | q4_0 | ✅ | 1 |
| 12GB | 12 GB | 32768 | 50 | q8_0 | - | 1 |
| 24GB | 24 GB | 65536 | 99 | q8_0 | - | 2 |

## 已知问题

- **SIGTERM 被忽略**：llama-server 在 CUDA I/O 密集时可能忽略 SIGTERM。脚本用 `-9`（SIGKILL）确保杀干净。
- **CUDA 12.9 CUB 头文件不兼容**：部分 llama.cpp commit 编译会报宏错误，自动 fallback CPU。
- **模型名显示**：`/v1/models` 端点格式可能在旧版 llama.cpp 中不同，不影响使用。

## 历史

- Python 脚本（`setup_llama-cpp.py`、`setup_llama_qwen36_vl.py`）已被删除，功能内嵌至 Bash 脚本。
- 旧的 preset 系统已删除，VRAM 专用脚本直接硬编码参数。
