#!/bin/bash
# usage: ./install.sh [uninstall]
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
USER_HOME="${SUDO_USER:+$(getent passwd "$SUDO_USER" | cut -d: -f6)}"
USER_HOME="${USER_HOME:-$HOME}"
DESKTOP="$USER_HOME/.local/share/applications/org.zencontrol.ZenControl.desktop"

if [ "${1:-}" = uninstall ]; then
    sudo rm -f /usr/local/libexec/zencontrol-helper \
               /usr/share/polkit-1/actions/org.zencontrol.helper.policy
    sudo rm -rf /var/lib/zencontrol
    rm -f "$DESKTOP"
    echo "ZenControl removed. Current settings stay until reboot."
    exit 0
fi

python3 -m py_compile "$DIR/helper/zencontrol-helper" "$DIR/app/zencontrol.py" "$DIR/app/monitor.py"
sudo install -o root -g root -m 0755 "$DIR/helper/zencontrol-helper" /usr/local/libexec/zencontrol-helper
sudo install -o root -g root -m 0644 "$DIR/data/org.zencontrol.helper.policy" /usr/share/polkit-1/actions/
sudo restorecon /usr/local/libexec/zencontrol-helper 2>/dev/null || true

mkdir -p "$(dirname "$DESKTOP")"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Name=ZenControl
Comment=CPU and GPU power control
Exec=python3 $DIR/app/zencontrol.py
Icon=power-profile-balanced-symbolic
Terminal=false
Type=Application
Categories=System;Settings;
EOF
echo "Installed. Open 'ZenControl' from the app menu, or run: python3 $DIR/app/zencontrol.py"
