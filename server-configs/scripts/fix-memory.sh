#!/bin/bash
set -e

APP_PATH="/home/panel/public_html"
PHP_VERSION=$(php -r "echo PHP_MAJOR_VERSION.'.'.PHP_MINOR_VERSION;" 2>/dev/null || echo "unknown")
TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')

echo "========================================="
echo "  bqckup-master Memory Fix Script"
echo "========================================="
echo "PHP Version: $PHP_VERSION"
echo "Total RAM: ${TOTAL_RAM_MB}MB"
echo "App Path: $APP_PATH"
echo ""

DETECT_FPM_DIR=""
for dir in /etc/php-fpm.d /etc/php/${PHP_VERSION}/fpm/pool.d /etc/php/8.2/fpm/pool.d /etc/php/8.1/fpm/pool.d /etc/php/8.0/fpm/pool.d; do
    if [ -d "$dir" ]; then
        DETECT_FPM_DIR="$dir"
        break
    fi
done

DETECT_PHP_INI=""
for ini in /etc/php.ini /etc/php/${PHP_VERSION}/fpm/php.ini /etc/php/8.2/fpm/php.ini /etc/php/8.1/fpm/php.ini; do
    if [ -f "$ini" ]; then
        DETECT_PHP_INI="$ini"
        break
    fi
done

echo "Detected FPM config dir: $DETECT_FPM_DIR"
echo "Detected php.ini: $DETECT_PHP_INI"
echo ""

MAX_CHILDREN=$((TOTAL_RAM_MB / 128))
if [ "$MAX_CHILDREN" -gt 20 ]; then
    MAX_CHILDREN=20
fi
if [ "$MAX_CHILDREN" -lt 2 ]; then
    MAX_CHILDREN=2
fi

SPARE_START=$((MAX_CHILDREN / 2))
if [ "$SPARE_START" -lt 1 ]; then
    SPARE_START=1
fi

SPARE_MAX=$((MAX_CHILDREN - 1))
if [ "$SPARE_MAX" -lt 1 ]; then
    SPARE_MAX=1
fi

echo "Calculated PHP-FPM settings:"
echo "  pm.max_children = $MAX_CHILDREN"
echo "  pm.start_servers = $SPARE_START"
echo "  pm.min_spare_servers = $SPARE_START"
echo "  pm.max_spare_servers = $SPARE_MAX"
echo ""

read -p "Apply these settings? (y/n): " CONFIRM
if [ "$CONFIRM" != "y" ] && [ "$CONFIRM" != "Y" ]; then
    echo "Aborted."
    exit 0
fi

echo ""
echo "Step 1: Fixing memory_limit in php.ini..."
if [ -n "$DETECT_PHP_INI" ] && [ -f "$DETECT_PHP_INI" ]; then
    cp "$DETECT_PHP_INI" "${DETECT_PHP_INI}.bak.$(date +%Y%m%d%H%M%S)"
    sed -i 's/^memory_limit\s*=.*/memory_limit = 128M/' "$DETECT_PHP_INI"
    grep "^memory_limit" "$DETECT_PHP_INI"
    echo "php.ini updated."
else
    echo "Creating .user.ini in app path..."
    echo "memory_limit = 128M" > "${APP_PATH}/.user.ini"
    echo ".user.ini created."
fi

echo ""
echo "Step 2: Fixing PHP-FPM pool configuration..."
if [ -n "$DETECT_FPM_DIR" ] && [ -d "$DETECT_FPM_DIR" ]; then
    POOL_FILE=""
    for f in "${DETECT_FPM_DIR}"/*.conf; do
        if [ -f "$f" ]; then
            POOL_FILE="$f"
            break
        fi
    done

    if [ -n "$POOL_FILE" ]; then
        cp "$POOL_FILE" "${POOL_FILE}.bak.$(date +%Y%m%d%H%M%S)"

        grep -q "^pm = " "$POOL_FILE" && \
            sed -i "s/^pm = .*/pm = dynamic/" "$POOL_FILE" || \
            echo "pm = dynamic" >> "$POOL_FILE"

        grep -q "^pm.max_children = " "$POOL_FILE" && \
            sed -i "s/^pm.max_children = .*/pm.max_children = ${MAX_CHILDREN}/" "$POOL_FILE" || \
            echo "pm.max_children = ${MAX_CHILDREN}" >> "$POOL_FILE"

        grep -q "^pm.start_servers = " "$POOL_FILE" && \
            sed -i "s/^pm.start_servers = .*/pm.start_servers = ${SPARE_START}/" "$POOL_FILE" || \
            echo "pm.start_servers = ${SPARE_START}" >> "$POOL_FILE"

        grep -q "^pm.min_spare_servers = " "$POOL_FILE" && \
            sed -i "s/^pm.min_spare_servers = .*/pm.min_spare_servers = ${SPARE_START}/" "$POOL_FILE" || \
            echo "pm.min_spare_servers = ${SPARE_START}" >> "$POOL_FILE"

        grep -q "^pm.max_spare_servers = " "$POOL_FILE" && \
            sed -i "s/^pm.max_spare_servers = .*/pm.max_spare_servers = ${SPARE_MAX}/" "$POOL_FILE" || \
            echo "pm.max_spare_servers = ${SPARE_MAX}" >> "$POOL_FILE"

        grep -q "^pm.max_requests = " "$POOL_FILE" && \
            sed -i "s/^pm.max_requests = .*/pm.max_requests = 500/" "$POOL_FILE" || \
            echo "pm.max_requests = 500" >> "$POOL_FILE"

        grep -q "^php_admin_value\[memory_limit\] = " "$POOL_FILE" && \
            sed -i "s|^php_admin_value\[memory_limit\] = .*|php_admin_value[memory_limit] = 128M|" "$POOL_FILE" || \
            echo "php_admin_value[memory_limit] = 128M" >> "$POOL_FILE"

        echo "FPM pool config updated: $POOL_FILE"
    else
        echo "No pool config found in $DETECT_FPM_DIR"
    fi
else
    echo "FPM config directory not detected. Manual configuration needed."
fi

echo ""
echo "Step 3: Clearing Laravel caches..."
if [ -d "${APP_PATH}" ]; then
    cd "${APP_PATH}"

    rm -rf bootstrap/cache/*.php 2>/dev/null || true
    rm -rf storage/framework/cache/* 2>/dev/null || true
    rm -rf storage/framework/views/* 2>/dev/null || true
    rm -rf storage/framework/sessions/* 2>/dev/null || true

    php artisan config:clear 2>/dev/null || true
    php artisan cache:clear 2>/dev/null || true
    php artisan route:clear 2>/dev/null || true
    php artisan view:clear 2>/dev/null || true
    php artisan optimize:clear 2>/dev/null || true

    echo "Laravel caches cleared."
else
    echo "App path not found: $APP_PATH"
fi

echo ""
echo "Step 4: Testing PHP-FPM config..."
php-fpm -t 2>/dev/null || php-fpm${PHP_VERSION} -t 2>/dev/null || echo "Could not test PHP-FPM config"

echo ""
echo "Step 5: Restarting services..."
if command -v systemctl &>/dev/null; then
    systemctl restart php-fpm 2>/dev/null || systemctl restart php${PHP_VERSION}-fpm 2>/dev/null || echo "Could not restart PHP-FPM"
    systemctl restart nginx 2>/dev/null || systemctl restart apache2 2>/dev/null || systemctl restart httpd 2>/dev/null || echo "Could not restart web server"
    echo "Services restarted."
else
    service php-fpm restart 2>/dev/null || echo "Could not restart PHP-FPM"
    service nginx restart 2>/dev/null || service apache2 restart 2>/dev/null || service httpd restart 2>/dev/null || echo "Could not restart web server"
    echo "Services restarted."
fi

echo ""
echo "========================================="
echo "  Fix Applied Successfully!"
echo "========================================="
echo ""
echo "Verify with:"
echo "  curl -I http://localhost"
echo "  tail -f ${APP_PATH}/storage/logs/laravel.log"
echo "  tail -f /var/log/php-fpm/error.log"
