#!/usr/bin/env bash
# Qwen3.6-27B-VL on VastAI · 8 GB VRAM
# Self-contained: build → download → run → forward → monitor
set -euo pipefail

# ═══════════════════════════════════════════════════════════════
# ── API ────────────────────────────────────────────────────────
API_KEY_FILE="${HOME}/.config/vastai/vast_api_key"
VAST_API="https://console.vast.ai/api/v0"

# ── model ──────────────────────────────────────────────────────
MODEL_FILE="Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-IQ3_M.gguf"
MMPROJ_FILE="mmproj-Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-f16.gguf"
BASE_URL="https://huggingface.co/HauhauCS/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive/resolve/main"
MODEL_URL="${BASE_URL}/${MODEL_FILE}?download=true"
MMPROJ_URL="${BASE_URL}/${MMPROJ_FILE}?download=true"

# ── llama-server flags ─────────────────────────────────────────
# Edit for your GPU. Uncomment optional features as needed.

CTX=262144
NGL=28
BATCH=512
UBATCH=512
TYPE_K="q8_0"
TYPE_V="q4_0"
PARALLEL=1

# ── optional flags (remove leading # to enable) ────────────────
NO_KV_OFFLOAD=1
# CACHE_REUSE=256
# REASONING="on"
# CONTEXT_SHIFT=1
# NO_MMPROJ_OFFLOAD=1
# IMAGE_MIN_TOKENS=512
# IMAGE_MAX_TOKENS=768
# MTRACK=1
# N_CPU_MOE=26
# MLOCK=1
# NO_MMAP=1
# SPEC_DRAFT_N_MAX=2
# SPEC_DRAFT_MODEL="/workspace/models/draft.gguf"

# ── remote paths ───────────────────────────────────────────────
REMOTE_RW="/workspace"
LLAMA_BIN="${REMOTE_RW}/llama.cpp/build/bin/llama-server"
BUILD_DIR="${REMOTE_RW}/llama.cpp/build"
LLAMA_DIR="${REMOTE_RW}/llama.cpp"
MODEL_DIR="${REMOTE_RW}/models"
LOG="${REMOTE_RW}/llama-server.log"
PID_FILE="${REMOTE_RW}/llama-server.pid"
LOCAL_PORT=12887
REMOTE_PORT=8089

# ── build control ──────────────────────────────────────────────
# FORCE_REBUILD=1

# ═══════════════════════════════════════════════════════════════
# script logic (no need to edit below)
# ═══════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

info()  { echo "  \033[36mℹ\033[0m $*"; }
ok()    { echo "  \033[32m✓\033[0m $*"; }
warn()  { echo "  \033[33m⚠\033[0m $*"; }
fail()  { echo "  \033[31m✗\033[0m $*"; exit 1; }

ssh_run() {
  ssh -p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=15 -o LogLevel=ERROR "root@${SSH_HOST}" "$1" 2>/dev/null
}

ssh_stream() {
  ssh -p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    -o ConnectTimeout=15 -o LogLevel=ERROR "root@${SSH_HOST}" "$1" 2>&1
}

check_local_port() {
  timeout 2 bash -c "</dev/tcp/127.0.0.1/${LOCAL_PORT}" 2>/dev/null
}

extract_json() {
  python3 -c "
import sys, json
data = json.load(sys.stdin)
${1}
" 2>/dev/null || echo "?"
}

# ── construct server flags ─────────────────────────────────────
build_flags() {
  local f=""
  f+="-c ${CTX} -b ${BATCH} -ub ${UBATCH} -ngl ${NGL} "
  f+="--cache-type-k ${TYPE_K} --cache-type-v ${TYPE_V} "
  f+="--parallel ${PARALLEL} "
  f+="-fa on --jinja --log-timestamps "
  [ -n "${CACHE_REUSE:-}"     ] && f+="--cache-reuse ${CACHE_REUSE} "
  [ -n "${REASONING:-}"       ] && f+="--reasoning ${REASONING} "
  [ -n "${CONTEXT_SHIFT:-}"   ] && f+="--context-shift "
  [ -n "${NO_KV_OFFLOAD:-}"   ] && f+="--no-kv-offload "
  [ -n "${NO_MMPROJ_OFFLOAD:-}" ] && f+="--no-mmproj-offload "
  [ -n "${IMAGE_MIN_TOKENS:-}" ] && f+="--image-min-tokens ${IMAGE_MIN_TOKENS} "
  [ -n "${IMAGE_MAX_TOKENS:-}" ] && f+="--image-max-tokens ${IMAGE_MAX_TOKENS} "
  [ -n "${MTRACK:-}"          ] && f+="--log-verbose --verbose-prompt "
  [ -n "${N_CPU_MOE:-}"       ] && f+="--n-cpu-moe ${N_CPU_MOE} "
  [ -n "${MLOCK:-}"           ] && f+="--mlock "
  [ -n "${NO_MMAP:-}"         ] && f+="--no-mmap "
  [ -n "${SPEC_DRAFT_N_MAX:-}" ] && f+="--model-draft ${SPEC_DRAFT_MODEL:?SPEC_DRAFT_MODEL required} --spec-type draft-mtp --spec-draft-n-max ${SPEC_DRAFT_N_MAX} --cache-type-k-draft q4_0 --cache-type-v-draft q4_0 "
  echo "$f"
}

# ═══════════════════════════════════════════════════════════════
# 1. detect instance via API
# ═══════════════════════════════════════════════════════════════
echo "  \033[1;36m══ Qwen3.6-27B-VL · 8 GB VRAM ══\033[0m"

[ -f "$API_KEY_FILE" ] || fail "API key not found at ${API_KEY_FILE}"
API_KEY=$(cat "$API_KEY_FILE")

INST_JSON=$(curl -sL "${VAST_API}/instances?owner=me&api_key=${API_KEY}")

INST_ID=$(echo "$INST_JSON" | extract_json '
data = data.get("instances", data)
for i in sorted(data, key=lambda x: x.get("id", 0), reverse=True):
  if i.get("cur_state") == "running":
    print(i["id"])
    break
')
[ -n "$INST_ID" ] && [ "$INST_ID" != "?" ] || fail "No running instance found"

GPU_NAME=$(echo "$INST_JSON" | extract_json "
for i in data.get('instances', data):
  if i.get('id') == $INST_ID:
    print(i.get('gpu_name', '?'))
    break
")
ok "Instance ${INST_ID} (${GPU_NAME})"

SSH_HOST=$(echo "$INST_JSON" | extract_json "
for i in data.get('instances', data):
  if i.get('id') == $INST_ID:
    print(i.get('public_ipaddr', '?'))
    break
")
SSH_PORT=$(echo "$INST_JSON" | extract_json "
for i in data.get('instances', data):
  if i.get('id') == $INST_ID:
    print(i.get('direct_port_start', '?'))
    break
")
[ "$SSH_HOST" != "?" ] && [ "$SSH_PORT" != "?" ] || fail "Could not extract SSH info"
ok "SSH: ${SSH_HOST}:${SSH_PORT}"

VRAM=$(ssh_run "nvidia-smi --query-gpu=memory.total --format=csv,noheader" 5 | grep -oP '\d+(?= MiB)' || echo "?")
ok "GPU: ${GPU_NAME} (${VRAM} MiB)"

# ═══════════════════════════════════════════════════════════════
# 2. attach SSH key
# ═══════════════════════════════════════════════════════════════
for k in ~/.ssh/id_ed25519.pub ~/.ssh/id_rsa.pub; do
  if [ -f "$k" ]; then
    SSH_KEY=$(cat "$k" | tr -d '\n')
    curl -sL -X PUT -H "Content-Type: application/json" \
      -H "Authorization: Bearer ${API_KEY}" \
      "${VAST_API}/instances/${INST_ID}/ssh/" \
      -d "{\"ssh_key\": \"${SSH_KEY}\"}" >/dev/null 2>&1 || true
    break
  fi
done
sleep 3

# ═══════════════════════════════════════════════════════════════
# 3. conditional build
# ═══════════════════════════════════════════════════════════════
[ -z "${FORCE_REBUILD:-}" ] || ssh_run "rm -rf ${LLAMA_DIR}" 60

if ssh_run "test -x ${LLAMA_BIN} && echo OK || echo MISS" | grep -q OK; then
  ok "llama-server ready"
else
  info "llama-server not found, building..."

  info "Installing build tools..."
  OUT=$(ssh_stream '
which cmake git make g++ >/dev/null 2>&1 && echo TOOLS_OK || {
  apt-get update -qq && apt-get install -y -qq build-essential cmake git wget curl && echo TOOLS_OK
}' 120 2>/dev/null)
  echo "$OUT" | tail -1 | grep -q TOOLS_OK || fail "Tool install failed"
  ok "Build tools ready"

  HAS_CUDA=false
  CUDA_OUT=$(ssh_run "which nvcc 2>/dev/null && echo FOUND || echo MISSING" 10)
  if echo "$CUDA_OUT" | grep -q FOUND; then
    info "CUDA detected, attempting GPU build..."
    OUT=$(ssh_stream "
cd ${REMOTE_RW}
[ -d ${LLAMA_DIR}/.git ] || { rm -rf ${LLAMA_DIR}; git clone --depth=1 https://github.com/ggerganov/llama.cpp.git ${LLAMA_DIR}; }
mkdir -p ${BUILD_DIR}
cmake -B ${BUILD_DIR} -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=86-real 2>&1
cmake --build ${BUILD_DIR} --config Release -j\$(nproc) --target llama-server 2>&1
echo BUILD_OK
" 900 2>/dev/null)
    echo "$OUT" | tail -1 | grep -q BUILD_OK && { ok "CUDA build successful"; HAS_CUDA=true; } || warn "CUDA build failed, falling back to CPU..."
  fi

  if [ "$HAS_CUDA" = false ]; then
    info "Building CPU-only..."
    OUT=$(ssh_stream "
cd ${REMOTE_RW}
[ -d ${LLAMA_DIR}/.git ] || { rm -rf ${LLAMA_DIR}; git clone --depth=1 https://github.com/ggerganov/llama.cpp.git ${LLAMA_DIR}; }
mkdir -p ${BUILD_DIR}
cmake -B ${BUILD_DIR} 2>&1
cmake --build ${BUILD_DIR} --config Release -j\$(nproc) --target llama-server 2>&1
echo BUILD_OK
" 900 2>/dev/null)
    echo "$OUT" | tail -1 | grep -q BUILD_OK || fail "Build failed"
    ok "CPU build successful"
  fi

  ssh_run "test -x ${LLAMA_BIN} && echo OK || echo MISS" | grep -q OK || fail "llama-server not found after build"
  ok "llama-server compiled"
fi

# ═══════════════════════════════════════════════════════════════
# 4. download models
# ═══════════════════════════════════════════════════════════════
info "Checking models..."
ssh_run "mkdir -p ${MODEL_DIR}" 10

if ssh_run "test -f ${MODEL_DIR}/${MODEL_FILE} && echo OK || echo MISS" | grep -q OK; then
  ok "Model present"
else
  info "Downloading model (~11 GB)..."
  ssh_stream "wget -c -O ${MODEL_DIR}/${MODEL_FILE} '${MODEL_URL}'" 7200
  ok "Model downloaded"
fi

if ssh_run "test -f ${MODEL_DIR}/${MMPROJ_FILE} && echo OK || echo MISS" | grep -q OK; then
  ok "mmproj present"
else
  info "Downloading mmproj..."
  ssh_stream "wget -c -O ${MODEL_DIR}/${MMPROJ_FILE} '${MMPROJ_URL}'" 3600
  ok "mmproj downloaded"
fi

# ═══════════════════════════════════════════════════════════════
# 5. register CUDA libs + start server
# ═══════════════════════════════════════════════════════════════
ssh_run "mkdir -p /etc/ld.so.conf.d && echo '/usr/local/cuda/lib64' > /etc/ld.so.conf.d/cuda-x86_64.conf && ldconfig" 10 || true

info "Starting llama-server..."
ssh_run "kill -9 \$(cat ${PID_FILE} 2>/dev/null) 2>/dev/null; pkill -9 llama-server 2>/dev/null; sleep 1; true" 10

FLAGS=$(build_flags)
REMOTE_CMD="export LD_LIBRARY_PATH=/usr/local/cuda/lib64; \
  nohup ${LLAMA_BIN} \
  -m ${MODEL_DIR}/${MODEL_FILE} \
  --mmproj ${MODEL_DIR}/${MMPROJ_FILE} \
  --host 0.0.0.0 --port ${REMOTE_PORT} \
  ${FLAGS} \
  > ${LOG} 2>&1 & PID=\$!; disown; echo \$PID > ${PID_FILE}"
ssh_run "$REMOTE_CMD" 30
sleep 2
PID=$(ssh_run "cat ${PID_FILE} 2>/dev/null || echo 0" 5 | tr -d ' \n\r' || true)
PID="${PID#PID=}"
if [ "$PID" = "0" ] || [ -z "$PID" ]; then
  warn "Could not determine server PID"
else
  ok "llama-server PID ${PID}"
fi

# ═══════════════════════════════════════════════════════════════
# 6. wait for remote port
# ═══════════════════════════════════════════════════════════════
info "Waiting for port ${REMOTE_PORT}..."
for i in $(seq 1 36); do
  ssh_run "timeout 2 bash -c '</dev/tcp/localhost/${REMOTE_PORT}' 2>/dev/null && echo OPEN || echo CLOSED" 5 | grep -q OPEN && break
  [ "$i" -eq 36 ] && fail "Timeout waiting for server"
  sleep 5
done
ok "Remote port ${REMOTE_PORT} open"

# ═══════════════════════════════════════════════════════════════
# 7. SSH forward
# ═══════════════════════════════════════════════════════════════
FWD_PID=""
CLEANUP_DONE=0
trap _exit INT TERM
trap _cleanup EXIT

_cleanup() {
  [ "$CLEANUP_DONE" = "1" ] && return
  CLEANUP_DONE=1
  [ -n "$FWD_PID" ] && kill "$FWD_PID" 2>/dev/null && wait "$FWD_PID" 2>/dev/null
  echo ""
  info "Instance still running and charging."
  info "Destroy: curl -sL -X DELETE -H 'Authorization: Bearer <key>' '${VAST_API}/instances/${INST_ID}/'"
  info "Stop:    curl -sL -X PUT -H 'Authorization: Bearer <key>' -d '{\"state\":\"stopped\"}' '${VAST_API}/instances/${INST_ID}/'"
}

_exit() {
  _cleanup
  exit 1
}

info "Forwarding localhost:${LOCAL_PORT} → remote:${REMOTE_PORT}..."
ssh -N -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" \
  -p "$SSH_PORT" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ExitOnForwardFailure=yes \
  "root@${SSH_HOST}" &
FWD_PID=$!
sleep 3
check_local_port || fail "Forward tunnel failed"
ok "localhost:${LOCAL_PORT} ↔ remote:${REMOTE_PORT}"

# ═══════════════════════════════════════════════════════════════
# 8. health check
# ═══════════════════════════════════════════════════════════════
info "Verifying server..."
for i in $(seq 1 12); do
  sleep 2
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${LOCAL_PORT}/health" 2>/dev/null || echo "000")
  [ "$CODE" = "200" ] && { ok "Health OK"; break; }
  [ "$i" -eq 12 ] && warn "Health check did not return 200"
done

MODEL_NAME=$(curl -s "http://localhost:${LOCAL_PORT}/v1/models" 2>/dev/null | extract_json '
try:
  d = json.load(sys.stdin)
  models = d.get("models", d.get("data", []))
  print(models[0].get("name", models[0].get("model", "?")) if models else "?")
except:
  print("?")
')

PRICE=$(echo "$INST_JSON" | extract_json "
for i in data.get('instances', data):
  if i.get('id') == $INST_ID:
    print(f\"\${i.get('dph_total', 0):.4f}/hr\")
    break
")
GPU_DISPLAY="${GPU_NAME} (${VRAM} MiB)"

echo ""
echo "  \033[1;36mQwen3.6-27B-VL · Instance ${INST_ID}\033[0m"
echo "  ──────────────────────────────────────────────────────────"
echo "  GPU      : ${GPU_DISPLAY}"
echo "  SSH      : root@${SSH_HOST}:${SSH_PORT}"
echo "  Price    : ${PRICE}"
echo "  ──────────────────────────────────────────────────────────"
echo "  ctx=${CTX}  ngl=${NGL}  batch=${BATCH}/${UBATCH}"
echo "  cache=${TYPE_K}/${TYPE_V}  parallel=${PARALLEL}"
echo "  ──────────────────────────────────────────────────────────"
echo "  \033[32m●\033[0m Server running (PID ${PID})"
echo "  \033[32m●\033[0m Model: ${MODEL_NAME}"
echo "  ──────────────────────────────────────────────────────────"
echo "  \033[36m🌐 Local API:\033[0m  http://localhost:${LOCAL_PORT}/v1"
echo "  \033[36m📡 Health:\033[0m    http://localhost:${LOCAL_PORT}/health"
echo "  ──────────────────────────────────────────────────────────"
echo "  \033[90mCtrl+C to stop forwarding (instance keeps running).\033[0m"
echo ""

# ═══════════════════════════════════════════════════════════════
# 9. monitoring loop
# ═══════════════════════════════════════════════════════════════
while true; do
  sleep 25
  UPTIME=$(ssh_run "ps -p ${PID} -o etime= 2>/dev/null || echo '?'" 8 | tr -d ' ')
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${LOCAL_PORT}/health" 2>/dev/null || echo "000")
  MARK="\033[32m●\033[0m"
  [ "$CODE" != "200" ] && MARK="\033[31m●\033[0m"
  echo -e "  [$(date +%H:%M:%S)] $MARK uptime=${UPTIME}  localhost:${LOCAL_PORT}/v1"
done
