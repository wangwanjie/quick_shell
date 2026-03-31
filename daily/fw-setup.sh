#!/bin/bash

# ====================================================
# Debian 防火墙一键修复、设置与恢复脚本 (V3.0)
# ====================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m'

BACKUP_DIR="/root/iptables_backups"
SSH_PORT=22
TCP_PORTS=""
UDP_PORTS=""
ALL_YES=false
NAT_NET="192.168.90.0/24"

# 帮助信息
show_usage() {
    echo -e "${BLUE}用法:${NC}"
    echo -e "  sudo bash $0 [选项]"
    echo ""
    echo -e "${BLUE}配置选项:${NC}"
    echo -e "  -s, --ssh-port <端口>    设置 SSH 端口 (默认: 22)"
    echo -e "  -t, --tcp-ports <列表>   允许 TCP 端口 (例: 80,443)"
    echo -e "  -u, --udp-ports <列表>   允许 UDP 端口 (例: 51820)"
    echo -e "  -n, --nat-net <网段>     NAT 转发网段 (默认: 192.168.90.0/24)"
    echo -e "  -y, --all-yes            跳过所有确认提示"
    echo ""
    echo -e "${BLUE}管理选项:${NC}"
    echo -e "  --restore                从备份文件中恢复防火墙规则"
    echo -e "  -h, --help               显示帮助"
}

# 恢复逻辑
do_restore() {
    if [ ! -d "$BACKUP_DIR" ] || [ -z "$(ls -A "$BACKUP_DIR")" ]; then
        echo -e "${RED}错误: 未找到任何备份文件在 $BACKUP_DIR${NC}"
        exit 1
    fi

    echo -e "${YELLOW}检测到以下备份文件:${NC}"
    select file in $(ls "$BACKUP_DIR"/*.rules); do
        if [ -n "$file" ]; then
            echo -e "${BLUE}正在恢复: $file ...${NC}"
            iptables-restore < "$file"
            iptables-save > /etc/iptables/rules.v4
            echo -e "${GREEN}恢复成功！当前规则已更新。${NC}"
            break
        else
            echo -e "${RED}选择无效，请重新选择。${NC}"
        fi
    done
    exit 0
}

# 校验端口
validate_port() {
    [[ ! $1 =~ ^[0-9]+$ ]] || [ "$1" -gt 65535 ] && { echo -e "${RED}错误: 端口 $1 无效${NC}"; exit 1; }
}

# 1. 权限与系统检查
[[ $EUID -ne 0 ]] && { echo -e "${RED}请以 root 运行${NC}"; exit 1; }
[[ ! -f /etc/debian_version ]] && { echo -e "${RED}仅支持 Debian${NC}"; exit 1; }

# 参数解析
while [[ "$#" -gt 0 ]]; do
    case $1 in
        --restore) do_restore ;;
        -s|--ssh-port) validate_port "$2"; SSH_PORT="$2"; shift ;;
        -t|--tcp-ports) TCP_PORTS="$2"; shift ;;
        -u|--udp-ports) UDP_PORTS="$2"; shift ;;
        -n|--nat-net) NAT_NET="$2"; shift ;;
        -y|--all-yes) ALL_YES=true ;;
        -h|--help) show_usage; exit 0 ;;
        *) echo -e "${RED}未知参数: $1${NC}"; show_usage; exit 1 ;;
    esac
    shift
done

# 2. 备份当前规则
mkdir -p "$BACKUP_DIR"
CURRENT_BACKUP="$BACKUP_DIR/backup_$(date +%Y%m%d_%H%M%S).rules"
iptables-save > "$CURRENT_BACKUP"

# 3. 运行前确认
if [ "$ALL_YES" = false ]; then
    echo -e "${YELLOW}=== 即将执行的操作 ===${NC}"
    echo -e "1. 备份当前规则至: $CURRENT_BACKUP"
    echo -e "2. 默认策略设置为 DROP (仅放行 $SSH_PORT, 80, 443 等)"
    echo -e "3. 开启内核转发并设置 NAT ($NAT_NET)"
    echo -e "4. 兼容 Docker 链"
    read -p "确认继续? (y/n): " confirm
    [[ $confirm != [yY] ]] && exit 0
fi

# 4. 环境准备
apt-get update -qq && apt-get install -y iptables iptables-persistent > /dev/null 2>&1

# 5. 清理规则 (关键: 仅清理主链，保留自定义链)
for t in filter nat mangle; do
    iptables -t $t -F INPUT 2>/dev/null
    iptables -t $t -F FORWARD 2>/dev/null
    iptables -t $t -F OUTPUT 2>/dev/null
done

# 6. 设置规则
iptables -P INPUT DROP
iptables -P FORWARD DROP
iptables -P OUTPUT ACCEPT

# 基础放行
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT
iptables -A INPUT -p tcp --dport "$SSH_PORT" -j ACCEPT
iptables -A INPUT -p tcp --dport 80 -j ACCEPT
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
iptables -A INPUT -p icmp --icmp-type echo-request -j ACCEPT

# 自定义端口
for p in ${TCP_PORTS//,/ }; do validate_port "$p"; iptables -A INPUT -p tcp --dport "$p" -j ACCEPT; done
for p in ${UDP_PORTS//,/ }; do validate_port "$p"; iptables -A INPUT -p udp --dport "$p" -j ACCEPT; done

# NAT & Forward
sysctl -w net.ipv4.ip_forward=1 > /dev/null
PUB_IF=$(ip route show | sed -n 's/^default.* dev \([^ ]*\).*/\1/p' | head -n 1)
if [ -n "$PUB_IF" ]; then
    iptables -t nat -A POSTROUTING -s "$NAT_NET" -o "$PUB_IF" -j MASQUERADE
    iptables -A FORWARD -s "$NAT_NET" -j ACCEPT
    iptables -A FORWARD -m state --state ESTABLISHED,RELATED -j ACCEPT
fi

# Docker 补丁
command -v docker &> /dev/null && {
    iptables -A FORWARD -i docker0 ! -o docker0 -j ACCEPT
    iptables -A FORWARD -o docker0 -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
}

# 日志与保存
iptables -A INPUT -j LOG --log-prefix "FW-DROP: " --log-level 4
iptables-save > /etc/iptables/rules.v4
netfilter-persistent save > /dev/null 2>&1

echo -e "\n${GREEN}配置完成！${NC}"
echo -e "${BLUE}提示: 如果由于配置错误导致无法连接，请登录 VNC 并运行:${NC}"
echo -e "${YELLOW}  sudo bash $0 --restore${NC}"