#!/usr/bin/env bash
# Run Qwen3.6-27B-VL (IQ3_M) on a running VastAI instance.
# Downloads model, starts llama-server, forwards port 12887 to localhost.
set -euo pipefail

# ── paths ────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VASTAI="$PROJECT_DIR/venv/bin/vastai"
LOCAL_PORT=12887
REMOTE_PORT=8089
RW="/workspace"
LLAMA_BIN="$RW/llama.cpp/build/bin/llama-server"
MODEL_DIR="$RW/models"
LOG="$RW/llama-server.log"
PID_FILE="$RW/llama-server.pid"

MODEL_FILE="Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-IQ3_M.gguf"
MMPROJ_FILE="mmproj-Qwen3.6-27B-Uncensored-HauhauCS-Aggressive-f16.gguf"
BASE_URL="https://huggingface.co/HauhauCS/Qwen3.6-27B-Uncensored-HauhauCS-Aggressive/resolve/main"
MODEL_URL="$BASE_URL/$MODEL_FILE?download=true"
MMPROJ_URL="$BASE_URL/$MMPROJ_FILE?download=true"

# ── llama-server settings (tune these per GPU) ─────────────
CTX=256111
NGL=50
BATCH=512
UBATCH=512
CACHE_K="q8_0"
CACHE_V="q8_0"
PARALLEL=2

FWD_PID=""
CLEANUP_DONE=0
trap _exit INT TERM
trap _cleanup EXIT

_cleanup() {
  [ "$CLEANUP_DONE" = "1" ] && return
  CLEANUP_DONE=1
  [ -n "$FWD_PID" ] && kill "$FWD_PID" 2>/dev/null && wait "$FWD_PID" 2>/dev/null
  [ -n "$INST_ID" ] && {
    echo ""
    echo "  \033[36mℹ\033[0m Instance still running and charging."
    echo "  To destroy: $VASTAI destroy instance $INST_ID"
    echo "  To stop:    $VASTAI stop instance $INST_ID"
  }
}

_exit() {
  _cleanup
  exit 1
}

# ── helpers ──────────────────────────────────────────────────
info()  { echo "  \033[36mℹ\033[0m $*"; }
ok()    { echo "  \033[32m✓\033[0m $*"; }
warn()  { echo "  \033[33m⚠\033[0m $*"; }
fail()  { echo "  \033[31m✗\033[0m $*"; exit 1; }

ssh_run() {
  local timeout="${2:-30}"
  ssh -p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=15 -o LogLevel=ERROR root@"$SSH_HOST" "$1" 2>/dev/null
}

ssh_stream() {
  local timeout="${2:-600}"
  ssh -p "$SSH_PORT" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
      -o ConnectTimeout=15 -o LogLevel=ERROR root@"$SSH_HOST" "$1" 2>&1
}

check_local_port() {
  timeout 2 bash -c "</dev/tcp/127.0.0.1/$LOCAL_PORT" 2>/dev/null && return 0 || return 1
}

# ── 1. detect instance ──────────────────────────────────────
echo "  \033[1;36m══ Qwen3.6-27B-VL VastAI ══\033[0m"

INST_JSON=$($VASTAI show instances --raw 2>/dev/null)
INST_ID=$(echo "$INST_JSON" | python3 -c "
import sys, json
data=json.load(sys.stdin)
for i in sorted(data, key=lambda x: x.get('id',0), reverse=True):
  if i.get('cur_state') == 'running':
    print(i['id'])
    break
" 2>/dev/null)
if [ -z "$INST_ID" ]; then fail "No running instance found"; fi
GPU_NAME=$(echo "$INST_JSON" | python3 -c "import sys,json;d=json.load(sys.stdin);[print(i.get('gpu_name','?')) for i in d if i.get('id')==$INST_ID]")
ok "Instance $INST_ID ($GPU_NAME)"

# ── 2. attach key ────────────────────────────────────────────
for k in ~/.ssh/id_ed25519.pub ~/.ssh/id_rsa.pub; do
  if [ -f "$k" ]; then
    $VASTAI attach ssh "$INST_ID" "$k" >/dev/null 2>&1 || true
    break
  fi
done
sleep 3

# ── 3. SSH URL ───────────────────────────────────────────────
SSH_URL=$($VASTAI ssh-url "$INST_ID" 2>/dev/null)
SSH_HOST=$(echo "$SSH_URL" | sed 's|ssh://[^@]*@||;s|:.*||')
SSH_PORT=$(echo "$SSH_URL" | sed 's|.*:||')
ok "SSH: $SSH_HOST:$SSH_PORT"

# ── 4. GPU info for display ──────────────────────────────────
VRAM=$(ssh_run "nvidia-smi --query-gpu=memory.total --format=csv,noheader" 5 | grep -oP '\d+(?= MiB)' || echo "?")
ok "GPU: $GPU_NAME (${VRAM} MiB)"

# ── 5. check build ──────────────────────────────────────────
info "Checking llama-server..."
if ssh_run "test -x $LLAMA_BIN && echo OK || echo MISS" | grep -q OK; then
  ok "llama-server ready"
else
  fail "llama-server not found. Run setup_llama-cpp.py first."
fi

# ── 6. download models ───────────────────────────────────────
info "Checking models..."
if ssh_run "test -f $MODEL_DIR/$MODEL_FILE && echo OK || echo MISS" | grep -q OK; then
  ok "Model present"
else
  info "Downloading model (~11GB)..."
  ssh_stream "mkdir -p $MODEL_DIR && wget -c -O $MODEL_DIR/$MODEL_FILE '$MODEL_URL'" 7200
  ok "Model downloaded"
fi

if ssh_run "test -f $MODEL_DIR/$MMPROJ_FILE && echo OK || echo MISS" | grep -q OK; then
  ok "mmproj present"
else
  info "Downloading mmproj..."
  ssh_stream "mkdir -p $MODEL_DIR && wget -c -O $MODEL_DIR/$MMPROJ_FILE '$MMPROJ_URL'" 3600
  ok "mmproj downloaded"
fi

# ── 7. register CUDA libs (permanent fix) + start server ─────
ssh_run "mkdir -p /etc/ld.so.conf.d && echo '/usr/local/cuda/lib64' > /etc/ld.so.conf.d/cuda-x86_64.conf && ldconfig" 10 || true
info "Starting llama-server..."
ssh_run "kill \$(cat $PID_FILE 2>/dev/null) 2>/dev/null; pkill llama-server 2>/dev/null; sleep 0.5; true" 10
REMOTE_CMD="export LD_LIBRARY_PATH=/usr/local/cuda/lib64; \
  nohup $LLAMA_BIN \
  -m $MODEL_DIR/$MODEL_FILE \
  --mmproj $MODEL_DIR/$MMPROJ_FILE \
  --host 0.0.0.0 --port $REMOTE_PORT \
  -c $CTX -b $BATCH -ub $UBATCH -ngl $NGL \
  --cache-type-k $CACHE_K --cache-type-v $CACHE_V \
  --parallel $PARALLEL \
  --jinja --reasoning on -fa on \
  --cache-reuse 128 \
  --no-mmproj-offload --no-kv-offload \
  --log-timestamps --log-prefix \
  > $LOG 2>&1 & PID=\$!; disown; echo \$PID > $PID_FILE"
ssh_run "$REMOTE_CMD" 30
sleep 2
PID=$(ssh_run "cat $PID_FILE 2>/dev/null || echo 0" 5 | tr -d ' \n\r'; true)
PID="${PID#PID=}"
if [ "$PID" = "0" ] || [ -z "$PID" ]; then
  warn "Could not determine server PID"
else
  ok "llama-server PID $PID"
fi

# ── 8. wait for remote port ──────────────────────────────────
info "Waiting for port $REMOTE_PORT..."
for i in $(seq 1 36); do
  ssh_run "timeout 2 bash -c '</dev/tcp/localhost/$REMOTE_PORT' 2>/dev/null && echo OPEN || echo CLOSED" 5 | grep -q OPEN && break
  [ "$i" -eq 36 ] && fail "Timeout waiting for server"
  sleep 5
done
ok "Remote port $REMOTE_PORT open"

# ── 9. SSH forward ───────────────────────────────────────────
info "Forwarding localhost:$LOCAL_PORT → remote:$REMOTE_PORT..."
ssh -N -L "$LOCAL_PORT:localhost:$REMOTE_PORT" \
  -p "$SSH_PORT" \
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
  -o ExitOnForwardFailure=yes \
  root@"$SSH_HOST" &
FWD_PID=$!
sleep 3
if ! check_local_port; then fail "Forward tunnel failed"; fi
ok "localhost:$LOCAL_PORT ↔ remote:$REMOTE_PORT"

# ── 10. health check ─────────────────────────────────────────
info "Verifying server..."
for i in $(seq 1 12); do
  sleep 2
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$LOCAL_PORT/health 2>/dev/null || echo "000")
  [ "$CODE" = "200" ] && { ok "Health OK"; break; }
  [ "$i" -eq 12 ] && warn "Health check did not return 200"
done

MODEL_NAME=$(curl -s http://localhost:$LOCAL_PORT/v1/models 2>/dev/null | python3 -c "
import sys,json
try:
  d=json.load(sys.stdin)
  models=d.get('models',d.get('data',[]))
  print(models[0].get('name',models[0].get('model','?')) if models else '?')
except: print('?')
" 2>/dev/null || echo "?")

# ── 11. dashboard ────────────────────────────────────────────
PRICE=$($VASTAI show instance "$INST_ID" --raw 2>/dev/null | python3 -c "import sys,json;print(f\"\${json.load(sys.stdin).get('dph_total',0):.4f}/hr\")" 2>/dev/null || echo "?")
GPU_DISPLAY="$GPU_NAME (${VRAM} MiB)"

echo ""
echo "  \033[1;36mQwen3.6-27B-VL · Instance $INST_ID\033[0m"
echo "  ──────────────────────────────────────────────────────────"
  echo "  GPU      : $GPU_DISPLAY"
  echo "  SSH      : root@$SSH_HOST:$SSH_PORT"
  echo "  Price    : $PRICE"
  echo "  ──────────────────────────────────────────────────────────"
  echo "  ctx=$CTX  ngl=$NGL  batch=$BATCH/$UBATCH"
  echo "  cache=$CACHE_K/$CACHE_V  parallel=$PARALLEL"
echo "  ──────────────────────────────────────────────────────────"
echo "  \033[32m●\033[0m Server running (PID $PID)"
echo "  \033[32m●\033[0m Model: $MODEL_NAME"
echo "  ──────────────────────────────────────────────────────────"
echo "  \033[36m🌐 Local API:\033[0m  http://localhost:$LOCAL_PORT/v1"
echo "  \033[36m📡 Health:\033[0m    http://localhost:$LOCAL_PORT/health"
echo "  ──────────────────────────────────────────────────────────"
echo "  \033[90mCtrl+C to stop forwarding (instance keeps running).\033[0m"
echo ""

# ── 12. monitoring loop ─────────────────────────────────────
while true; do
  sleep 25
  UPTIME=$(ssh_run "ps -p $PID -o etime= 2>/dev/null || echo '?'" 8 | tr -d ' ')
  CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:$LOCAL_PORT/health 2>/dev/null || echo "000")
  MARK="\033[32m●\033[0m"
  [ "$CODE" != "200" ] && MARK="\033[31m●\033[0m"
  echo -e "  [$(date +%H:%M:%S)] $MARK uptime=$UPTIME  localhost:$LOCAL_PORT/v1"
done
