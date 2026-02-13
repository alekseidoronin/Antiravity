#!/bin/bash
# Скопируйте и вставьте всё это в терминал на сервере (KVM или SSH), затем пришлите вывод сюда.

echo "=== OS ==="
uname -a
cat /etc/os-release | head -6

echo ""
echo "=== Диск ==="
df -h

echo ""
echo "=== Память RAM ==="
free -h

echo ""
echo "=== CPU ==="
nproc
grep -E "model name|MHz" /proc/cpuinfo | head -4

echo ""
echo "=== Docker (если есть) ==="
docker --version 2>/dev/null || echo "Docker не установлен"
docker ps -a 2>/dev/null || true

echo ""
echo "=== Службы systemd (первые 25) ==="
systemctl list-units --type=service --state=running 2>/dev/null | head -25

echo ""
echo "=== Открытые порты ==="
ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null

echo ""
echo "=== Крупные пакеты / что установлено (примеры) ==="
dpkg -l 2>/dev/null | grep -E "^ii" | wc -l
echo "установленных пакетов"
which node npm n8n docker 2>/dev/null; true

echo ""
echo "=== Конец проверки ==="
