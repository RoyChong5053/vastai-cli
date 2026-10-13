# VastAI + llama.cpp + Qwen3.6-27B-VL 部署知识

## 架构

```
┌─ 租机 ─────────────────────┐    ┌─ 跑模型 ──────────────────────────────────┐
│ vastai search / create      │    │ qwen36-27B-12GB.sh (纯 Bash)              │
│ (Python + venv, 偶尔用)     │───▶│   curl API → SSH info                     │
│                              │    │   SSH → build / download / run           │
└──────────────────────────────┘    │   SSH -L :12887 → monitor               │
                                      └────────────────────────────────────────┘
```

**关键点：**
- `llama-server` 在远端运行时，SSH -L 隧道在本地发起
- API 调用：`curl http://localhost:12887/v1` → 隧道 → 远端 `localhost:8089`
- 跑模型脚本不再依赖 Python/venv，只用系统自带的 `bash curl ssh`

---

## 脚本体系

```
vastai_cli/
├── run-scripts/
│   ├── qwen36-27B-12GB.sh    # 12GB VRAM (RTX 3060)
│   ├── qwen36-27B-8GB.sh     # 8GB VRAM (no-kv-offload, 256k ctx)
│   ├── qwen36-27B-24GB.sh    # 24GB VRAM (全层 offload, 多 slot)
│   ├── qwen36-vl.sh          # (legacy 旧版)
│   └── SETUP_LLAMA_NOTE.md   # 开发笔记
├── docs/
│   └── vastai-llama-deploy.md # 本文档
└── venv/                      # 仅租机阶段需要
```

### 自包含脚本结构

每个 `qwen36-27B-*.sh` 都包含完整流程：

```bash
# 1. API key + curl 检测实例
# 2. SSH key 附加
# 3. 条件编译（若 binary 缺失）
# 4. 下载模型（已存在跳过）
# 5. 注册 CUDA lib + 启动 server
# 6. 等待远端端口
# 7. SSH -L 转发
# 8. Health 探测 + Dashboard
# 9. 监控循环
```

---

## llama-server 配置参数

所有参数集中在脚本顶部：

```bash
CTX=32768       # 上下文长度
NGL=50          # GPU 层数
BATCH=512       # batch size
UBATCH=512      # ubatch size
TYPE_K="q8_0"   # Key cache 量化
TYPE_V="q8_0"   # Value cache 量化
PARALLEL=1      # 并行 slot 数
```

### 可选功能（取消注释启用）

```bash
# CACHE_REUSE=256         # KV 缓存复用（省显存）
# NO_KV_OFFLOAD=1         # KV cache 放 CPU（省显存，慢）
# NO_MMPROJ_OFFLOAD=1     # mmproj 放 CPU（仅 VL 模型）
# REASONING="on"          # 推理模式
# CONTEXT_SHIFT=1         # VL 上下文移位
# IMAGE_MIN_TOKENS=512    # 图片最少 token
# IMAGE_MAX_TOKENS=768    # 图片最多 token
# MTRACK=1                # 内存跟踪日志
# N_CPU_MOE=26            # MoE expert 放 CPU
# MLOCK=1                 # 锁内存
# NO_MMAP=1               # 禁用 mmap
# SPEC_DRAFT_N_MAX=2      # MTP 投机解码
# SPEC_DRAFT_MODEL="..."  # 草稿模型路径
```

### 不同 GPU 参考配置

| 脚本 | VRAM | CTX | NGL | BATCH | CACHE_V | KV offload | PARALLEL |
|------|------|-----|-----|-------|---------|------------|----------|
| 8GB.sh | 8 GB | 262144 | 28 | 512 | q4_0 | ✅ | 1 |
| 12GB.sh | 12 GB | 32768 | 50 | 512 | q8_0 | - | 1 |
| 24GB.sh | 24 GB | 65536 | 99 | 1024 | q8_0 | - | 2 |

---

## 使用流程

### 首次部署

```bash
# 1. 确保有 running instance
cd /home/roychong/workspace/mycode/vastai_cli

# 2. 跑对应脚本（自动编译 + 下载 + 启动）
bash run-scripts/qwen36-27B-12GB.sh
```

### 后续使用（已编译 + 已下载）

```bash
bash run-scripts/qwen36-27B-12GB.sh
```

### 停止

`Ctrl+C` → 关闭本地隧道，远端继续运行（继续计费）。

销毁/停止实例（API 调用）：
```bash
export KEY=$(cat ~/.config/vastai/vast_api_key)
curl -sL -X DELETE -H "Authorization: Bearer $KEY" \
  "https://console.vast.ai/api/v0/instances/40849424/"    # destroy
curl -sL -X PUT -H "Authorization: Bearer $KEY" \
  -d '{"state":"stopped"}' \
  "https://console.vast.ai/api/v0/instances/40849424/"    # stop
```

---

## 常见问题

### 1. libcublas.so.12: No such file or directory

**原因：** CUDA lib 路径未注册。脚本会自动运行 `ldconfig` 修复。

### 2. 服务器拒绝 SIGTERM

**现象：** `kill` 或 `pkill` 无法终止进程。
**原因：** CUDA I/O 密集时进程 SIGTERM 被阻塞。
**修复：** 脚本使用 `kill -9`（SIGKILL）强制终止。

### 3. 编译失败 - CUDA 12.9 CUB 报错

脚本自动 fallback 到 CPU-only 编译。

### 4. SSH 隧道不通

排查：
```bash
# 检查远端端口
ssh -p <PORT> root@<HOST> "ss -tlnp | grep 8089"

# 检查本地转发
ps aux | grep "ssh.*-L"
```

---

## API 参考

无需 `vastai` CLI，直接 curl：

```bash
API_KEY=$(cat ~/.config/vastai/vast_api_key)
BASE="https://console.vast.ai/api/v0"

# 列出实例
curl -sL "${BASE}/instances?owner=me&api_key=${API_KEY}"

# 附加 SSH key
curl -sL -X PUT -H "Authorization: Bearer ${API_KEY}" \
  -H "Content-Type: application/json" \
  "${BASE}/instances/<ID>/ssh/" \
  -d '{"ssh_key": "ssh-ed25519 ..."}'

# 停止实例
curl -sL -X PUT -H "Authorization: Bearer ${API_KEY}" \
  -d '{"state":"stopped"}' \
  "${BASE}/instances/<ID>/"

# 销毁实例
curl -sL -X DELETE -H "Authorization: Bearer ${API_KEY}" \
  "${BASE}/instances/<ID>/"
```

---

## 远端文件路径约定

| 路径 | 内容 |
|------|------|
| `/workspace/llama.cpp/build/bin/llama-server` | 编译产物 |
| `/workspace/llama.cpp/` | 源码 |
| `/workspace/models/*.gguf` | 模型文件 |
| `/workspace/llama-server.log` | server 日志 |
| `/workspace/llama-server.pid` | PID 文件 |
