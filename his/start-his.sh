#!/bin/bash
# ============================================
#  HIS 一键启动：后端 + 前端
#  项目目录：E:\contest\July_one\hospital\hospital\his
# ============================================

HIS_ROOT="$(cd "$(dirname "$0")" && pwd)"

GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

if command -v cygpath >/dev/null 2>&1; then
  HIS_ROOT_WIN="$(cygpath -w "$HIS_ROOT")"
else
  HIS_ROOT_WIN="$HIS_ROOT"
fi

port_pids() {
  local port="$1"
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique" 2>/dev/null | tr -d '\r'
  else
    netstat -ano 2>/dev/null | awk -v p=":$port" '$0 ~ p && $0 ~ /LISTEN/ { print $NF }' | sort -u
  fi
}

process_info() {
  local pid="$1"
  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "\$p=Get-CimInstance Win32_Process -Filter 'ProcessId=$pid' -ErrorAction SilentlyContinue; if (\$p) { Write-Output (\$p.Name + ' ' + \$p.CommandLine) }" 2>/dev/null | tr -d '\r'
  else
    ps -p "$pid" -o comm=,args= 2>/dev/null
  fi
}

print_port_owner() {
  local port="$1"
  local pids
  pids="$(port_pids "$port")"

  for pid in $pids; do
    echo -e "${YELLOW}  PID ${pid}: $(process_info "$pid")${NC}" >&2
  done
}

port_in_use() {
  [[ -n "$(port_pids "$1")" ]]
}

pick_port() {
  local preferred="$1"
  local name="$2"
  local port="$preferred"
  local max=$((preferred + 30))

  while (( port <= max )); do
    if ! port_in_use "$port"; then
      if [[ "$port" != "$preferred" ]]; then
        echo -e "${GREEN}${name} 自动切换到端口 ${port}.${NC}" >&2
      fi
      echo "$port"
      return 0
    fi

    echo -e "${YELLOW}${name} 首选端口 ${port} 已被占用：${NC}" >&2
    print_port_owner "$port"
    port=$((port + 1))
  done

  echo -e "${RED}${name} 在 ${preferred}-${max} 范围内没有可用端口。${NC}" >&2
  exit 1
}

ensure_his_https_cert() {
  local cert_dir="$HIS_ROOT/client"
  local key_file="$cert_dir/key.pem"
  local cert_file="$cert_dir/cert.pem"

  if [[ -f "$key_file" && -f "$cert_file" ]]; then
    return 0
  fi

  echo -e "${YELLOW}正在生成 HIS 前端本地 HTTPS 证书...${NC}"
  if ! command -v openssl >/dev/null 2>&1; then
    echo -e "${RED}未找到 openssl，无法生成 HTTPS 证书。请使用 Git Bash 或安装 OpenSSL。${NC}"
    exit 1
  fi

  openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$key_file" \
    -out "$cert_file" \
    -days 365 \
    -subj "/CN=localhost" \
    -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" >/dev/null 2>&1 \
  || openssl req -x509 -newkey rsa:2048 -nodes \
    -keyout "$key_file" \
    -out "$cert_file" \
    -days 365 \
    -subj "/CN=localhost" >/dev/null 2>&1

  if [[ ! -f "$key_file" || ! -f "$cert_file" ]]; then
    echo -e "${RED}HTTPS 证书生成失败。${NC}"
    exit 1
  fi
}

ensure_npm_deps() {
  local dir="$1"
  local name="$2"
  if [[ -d "$dir/node_modules" ]]; then
    return 0
  fi

  echo -e "${YELLOW}${name} 依赖未安装，正在执行 npm ci...${NC}"
  cd "$dir" || exit 1
  npm ci || {
    echo -e "${RED}${name} 依赖安装失败。${NC}"
    exit 1
  }
}

wait_for_port() {
  local port="$1"
  local name="$2"
  local retries=25

  while (( retries > 0 )); do
    if port_in_use "$port"; then
      echo -e "${GREEN}${name} 已就绪。${NC}"
      return 0
    fi
    sleep 1
    retries=$((retries - 1))
  done

  echo -e "${RED}${name} 启动超时，请查看上方日志。${NC}"
  cleanup
}

print_access_urls() {
  local frontend_port="$1"
  local backend_port="$2"

  echo ""
  echo -e "${YELLOW}============================================${NC}"
  echo -e "${GREEN}  HIS 系统已启动${NC}"
  echo -e "${YELLOW}============================================${NC}"
  echo -e "  本机前端： ${BLUE}https://localhost:${frontend_port}${NC}"
  echo -e "  本机后端： ${BLUE}http://localhost:${backend_port}${NC}"

  if command -v powershell.exe >/dev/null 2>&1; then
    local ips
    ips="$(powershell.exe -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { \$_.IPAddress -ne '127.0.0.1' -and \$_.IPAddress -notlike '169.254*' } | Select-Object -ExpandProperty IPAddress -First 5" 2>/dev/null | tr -d '\r')"
    if [[ -n "$ips" ]]; then
      echo -e "  外部访问："
      for ip in $ips; do
        echo -e "    ${BLUE}https://${ip}:${frontend_port}${NC}"
      done
      echo -e "  ${YELLOW}提示：首次访问 HTTPS 自签名证书时，浏览器需要手动信任。${NC}"
    fi
  fi

  echo -e "${YELLOW}============================================${NC}"
  echo -e "  按 ${RED}Ctrl+C${NC} 停止 HIS 服务"
  echo ""
}

cleanup() {
  echo ""
  echo -e "${YELLOW}正在停止 HIS 服务...${NC}"
  kill $HIS_FE_PID $HIS_BE_PID 2>/dev/null
  wait $HIS_FE_PID $HIS_BE_PID 2>/dev/null
  echo -e "${GREEN}HIS 服务已停止${NC}"
  exit 0
}
trap cleanup SIGINT SIGTERM

echo -e "${BLUE}============================================${NC}"
echo -e "${BLUE}    HIS 系统一键启动${NC}"
echo -e "${BLUE}    ${HIS_ROOT_WIN}${NC}"
echo -e "${BLUE}============================================${NC}"

ensure_his_https_cert
ensure_npm_deps "$HIS_ROOT/server" "HIS 后端"
ensure_npm_deps "$HIS_ROOT/client" "HIS 前端"

HIS_BE_PORT="$(pick_port 3001 "HIS 后端")"
HIS_FE_PORT="$(pick_port 3002 "HIS 前端")"

echo -e "${GREEN}[1/2] 启动 HIS 后端 → http://0.0.0.0:${HIS_BE_PORT}${NC}"
cd "$HIS_ROOT/server" || exit 1
PORT="$HIS_BE_PORT" HOST="0.0.0.0" npm run dev &
HIS_BE_PID=$!
wait_for_port "$HIS_BE_PORT" "HIS 后端"

echo -e "${GREEN}[2/2] 启动 HIS 前端 → https://0.0.0.0:${HIS_FE_PORT}${NC}"
cd "$HIS_ROOT/client" || exit 1
VITE_API_TARGET="http://127.0.0.1:${HIS_BE_PORT}" npm run dev -- --host 0.0.0.0 --port "$HIS_FE_PORT" --strictPort --force &
HIS_FE_PID=$!
wait_for_port "$HIS_FE_PORT" "HIS 前端"

print_access_urls "$HIS_FE_PORT" "$HIS_BE_PORT"
wait
