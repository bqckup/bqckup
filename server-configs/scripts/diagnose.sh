#!/bin/bash
set -e

echo "========================================="
echo "  bqckup-master Memory Issue Diagnostic"
echo "========================================="
echo ""

echo "--- System Memory ---"
free -h
echo ""

echo "--- CPU Info ---"
nproc
echo ""

echo "--- Disk Space ---"
df -h / /home 2>/dev/null
echo ""

echo "--- OOM Killer Events ---"
dmesg | grep -i "oom\|out of memory\|killed process" 2>/dev/null | tail -20 || echo "Could not read dmesg (need sudo)"
echo ""

echo "--- PHP Version ---"
php -v 2>/dev/null || echo "PHP CLI not found in PATH"
echo ""

echo "--- Current PHP memory_limit ---"
php -i 2>/dev/null | grep "memory_limit" || echo "Could not get PHP info"
echo ""

echo "--- PHP-FPM Status ---"
systemctl status php-fpm 2>/dev/null || systemctl status php8.1-fpm 2>/dev/null || systemctl status php8.2-fpm 2>/dev/null || echo "Could not get PHP-FPM status"
echo ""

echo "--- PHP-FPM Pool Configs ---"
echo "Searching in common locations..."
for f in /etc/php-fpm.d/*.conf /etc/php/*/fpm/pool.d/*.conf; do
    if [ -f "$f" ]; then
        echo "Found: $f"
        grep -E "^(pm\.|memory_limit|php_admin)" "$f" 2>/dev/null
        echo "---"
    fi
done
echo ""

echo "--- PHP Error Log (last 30 lines) ---"
for log in /var/log/php-fpm/error.log /var/log/php*/fpm.log /var/log/php.errors /home/panel/public_html/storage/logs/*.log; do
    if [ -f "$log" ]; then
        echo "Found: $log"
        tail -30 "$log" 2>/dev/null
        echo "---"
    fi
done
echo ""

echo "--- Laravel Log (last 30 lines) ---"
for log in /home/panel/public_html/storage/logs/laravel*.log; do
    if [ -f "$log" ]; then
        echo "Found: $log"
        tail -30 "$log" 2>/dev/null
        echo "---"
    fi
done
echo ""

echo "--- Top Memory Consumers ---"
ps aux --sort=-%mem | head -15
echo ""

echo "--- PHP-FPM Processes ---"
ps aux | grep php-fpm | head -20
echo ""

echo "--- Nginx/Apache Status ---"
systemctl status nginx 2>/dev/null || systemctl status apache2 2>/dev/null || systemctl status httpd 2>/dev/null || echo "Could not get web server status"
echo ""

echo "========================================="
echo "  Diagnostic Complete"
echo "========================================="
