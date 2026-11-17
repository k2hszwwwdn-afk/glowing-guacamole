#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "$0")" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
    printf 'Python 3 is required to install EarthWatch.\n' >&2
    exit 1
fi

if ! command -v kpackagetool6 >/dev/null 2>&1; then
    printf 'KDE Plasma 6 (kpackagetool6) is required to install the companion widget.\n' >&2
    exit 1
fi

python3 -m venv --system-site-packages "$project_dir/.venv"
if ! "$project_dir/.venv/bin/python" -c 'import PySide6' >/dev/null 2>&1; then
    "$project_dir/.venv/bin/python" -m pip install -r "$project_dir/requirements.txt"
fi

chmod +x "$project_dir/run.sh"
applications_dir="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
icons_dir="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
mkdir -p "$applications_dir"
mkdir -p "$icons_dir"
install -m 0644 "$project_dir/icons/earthwatch.svg" "$icons_dir/earthwatch.svg"
cat > "$applications_dir/earthwatch.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=EarthWatch
Name[zh_CN]=地震观察
Name[es]=EarthWatch
Name[ar]=مراقب الزلازل
Comment=Live global earthquake activity from USGS
Comment[zh_CN]=USGS 全球地震实时活动
Comment[es]=Actividad sísmica global en vivo de USGS
Comment[ar]=النشاط الزلزالي العالمي المباشر من USGS
Exec="$project_dir/run.sh"
Icon=earthwatch
Terminal=false
Categories=Education;Science;
StartupNotify=true
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$applications_dir"
fi

applet_id="io.github.glowingguacamole.earthquakewatch"
if kpackagetool6 --type Plasma/Applet --list | grep -Fq "$applet_id"; then
    kpackagetool6 --type Plasma/Applet --upgrade \
        "$project_dir/plasma/$applet_id"
else
    kpackagetool6 --type Plasma/Applet --install \
        "$project_dir/plasma/$applet_id"
fi

printf 'EarthWatch installed. Launch it from the application menu, then add the EarthWatch widget to a panel.\n'
