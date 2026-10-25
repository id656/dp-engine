#!/bin/bash
# Внешние инструменты для панорам 360°: pbrt-v4 (с патчем ODS-камеры и без GUI) и Intel Open Image Denoise.
# Использование: bash engine/ifc/pbrt/setup_tools.sh [папка, по умолчанию /home/claude/ext]
# Сеть: нужен доступ к github.com (клонирование и релизы). Сборка pbrt ~10–15 мин на 4 ядрах.
set -e
EXT=${1:-/home/claude/ext}
HERE=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$EXT" && cd "$EXT"
if [ ! -x pbrt-v4/build/pbrt ]; then
  [ -d pbrt-v4 ] || git clone --recursive https://github.com/mmp/pbrt-v4.git
  cd pbrt-v4
  git checkout b4ce9687e6c695f5582997c61b0c66cf064bdb4a
  git submodule update --init --recursive
  git apply "$HERE/pbrt-v4-ods.patch" || echo "патч уже наложен?"
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DPBRT_BUILD_NATIVE_EXECUTABLE=ON
  cmake --build build -j$(nproc) --target pbrt_exe 2>&1 | tail -3 || cmake --build build -j$(nproc) 2>&1 | tail -3
  cd "$EXT"
fi
if [ ! -d oidn/oidn-2.3.1.x86_64.linux ]; then
  mkdir -p oidn && cd oidn
  curl -sSL -o oidn.tgz https://github.com/RenderKit/oidn/releases/download/v2.3.1/oidn-2.3.1.x86_64.linux.tar.gz
  tar xzf oidn.tgz
  cd "$EXT"
fi
ls -la "$EXT/pbrt-v4/build/pbrt" "$EXT/oidn/oidn-2.3.1.x86_64.linux/bin/oidnDenoise"
