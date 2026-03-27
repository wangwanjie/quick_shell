#!/usr/bin/env bash
# gen-appicon.sh
# 功能：从一张图片生成 macOS 或 iOS 的 AppIcon.appiconset 图标集
#
# 用法：
#   bash ./gen-appicon.sh -i <input> -o <output_dir> [--platform mac|ios]
#
# 选项：
#   -i <file>           输入图片路径（必填，建议 1024x1024 PNG）
#   -o <dir>            输出目录（必填）
#   --platform <p>      目标平台：mac 或 ios，默认 mac
#   -h                  显示帮助

set -euo pipefail

# ============================================================
# 默认值
# ============================================================
INPUT=""
OUTPUT_DIR=""
PLATFORM="mac"

# ============================================================
# 帮助
# ============================================================
usage() {
    grep '^#' "$0" | head -15 | sed 's/^# \?//'
    exit 0
}

# ============================================================
# 解析参数
# ============================================================
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i)          INPUT="$2";    shift 2 ;;
        -o)          OUTPUT_DIR="$2"; shift 2 ;;
        --platform)  PLATFORM="$2"; shift 2 ;;
        -h|--help)   usage ;;
        *) echo "❌ 未知参数: $1"; usage ;;
    esac
done

# ============================================================
# 参数校验
# ============================================================
[[ -z "$INPUT" ]]      && { echo "❌ 缺少 -i 参数（输入文件）"; exit 1; }
[[ -z "$OUTPUT_DIR" ]] && { echo "❌ 缺少 -o 参数（输出目录）"; exit 1; }
[[ ! -f "$INPUT" ]]    && { echo "❌ 输入文件不存在: $INPUT"; exit 1; }

if [[ "$PLATFORM" != "mac" ]] && [[ "$PLATFORM" != "ios" ]]; then
    echo "❌ --platform 只支持：mac | ios"
    exit 1
fi

# 检查 ImageMagick
if ! command -v magick &>/dev/null && ! command -v convert &>/dev/null; then
    echo "❌ 未找到 ImageMagick，请先安装：brew install imagemagick"
    exit 1
fi

IM_CMD="magick"
command -v magick &>/dev/null || IM_CMD="convert"

# ============================================================
# 图标尺寸定义
# 格式：filename|px|idiom|size|scale
# ============================================================
declare -a MAC_ICONS=(
    "app_icon_16.png|16|mac|16x16|1x"
    "app_icon_16@2x.png|32|mac|16x16|2x"
    "app_icon_32.png|32|mac|32x32|1x"
    "app_icon_32@2x.png|64|mac|32x32|2x"
    "app_icon_128.png|128|mac|128x128|1x"
    "app_icon_128@2x.png|256|mac|128x128|2x"
    "app_icon_256.png|256|mac|256x256|1x"
    "app_icon_256@2x.png|512|mac|256x256|2x"
    "app_icon_512.png|512|mac|512x512|1x"
    "app_icon_512@2x.png|1024|mac|512x512|2x"
)

declare -a IOS_ICONS=(
    "app_icon_20.png|20|iphone|20x20|1x"
    "app_icon_20@2x.png|40|iphone|20x20|2x"
    "app_icon_20@3x.png|60|iphone|20x20|3x"
    "app_icon_29.png|29|iphone|29x29|1x"
    "app_icon_29@2x.png|58|iphone|29x29|2x"
    "app_icon_29@3x.png|87|iphone|29x29|3x"
    "app_icon_40.png|40|iphone|40x40|1x"
    "app_icon_40@2x.png|80|iphone|40x40|2x"
    "app_icon_40@3x.png|120|iphone|40x40|3x"
    "app_icon_60@2x.png|120|iphone|60x60|2x"
    "app_icon_60@3x.png|180|iphone|60x60|3x"
    "app_icon_ipad_20.png|20|ipad|20x20|1x"
    "app_icon_ipad_20@2x.png|40|ipad|20x20|2x"
    "app_icon_ipad_29.png|29|ipad|29x29|1x"
    "app_icon_ipad_29@2x.png|58|ipad|29x29|2x"
    "app_icon_ipad_40.png|40|ipad|40x40|1x"
    "app_icon_ipad_40@2x.png|80|ipad|40x40|2x"
    "app_icon_ipad_76.png|76|ipad|76x76|1x"
    "app_icon_ipad_76@2x.png|152|ipad|76x76|2x"
    "app_icon_ipad_83@2x.png|167|ipad|83.5x83.5|2x"
    "app_icon_1024.png|1024|ios-marketing|1024x1024|1x"
)

# ============================================================
# 主逻辑
# ============================================================
ICONSET_DIR="$OUTPUT_DIR/AppIcon.appiconset"
mkdir -p "$ICONSET_DIR"

echo "=================================================="
echo "🖼  输入文件  : $INPUT"
echo "📁 输出目录  : $ICONSET_DIR"
echo "📱 平台      : $PLATFORM"
echo "=================================================="

if [[ "$PLATFORM" == "mac" ]]; then
    ICONS=("${MAC_ICONS[@]}")
else
    ICONS=("${IOS_ICONS[@]}")
fi

for entry in "${ICONS[@]}"; do
    IFS='|' read -r filename px idiom size scale <<< "$entry"
    echo "  → ${px}x${px}  ($size @${scale} · ${idiom})  →  $filename"
    $IM_CMD "$INPUT" -resize "${px}x${px}" "$ICONSET_DIR/$filename"
done


echo ""
echo "⚙️  生成 Contents.json..."

if [[ "$PLATFORM" == "mac" ]]; then
    cat > "$ICONSET_DIR/Contents.json" << 'EOF'
{
  "images" : [
    { "filename": "app_icon_16.png",      "idiom": "mac", "scale": "1x", "size": "16x16"   },
    { "filename": "app_icon_16@2x.png",   "idiom": "mac", "scale": "2x", "size": "16x16"   },
    { "filename": "app_icon_32.png",      "idiom": "mac", "scale": "1x", "size": "32x32"   },
    { "filename": "app_icon_32@2x.png",   "idiom": "mac", "scale": "2x", "size": "32x32"   },
    { "filename": "app_icon_128.png",     "idiom": "mac", "scale": "1x", "size": "128x128" },
    { "filename": "app_icon_128@2x.png",  "idiom": "mac", "scale": "2x", "size": "128x128" },
    { "filename": "app_icon_256.png",     "idiom": "mac", "scale": "1x", "size": "256x256" },
    { "filename": "app_icon_256@2x.png",  "idiom": "mac", "scale": "2x", "size": "256x256" },
    { "filename": "app_icon_512.png",     "idiom": "mac", "scale": "1x", "size": "512x512" },
    { "filename": "app_icon_512@2x.png",  "idiom": "mac", "scale": "2x", "size": "512x512" }
  ],
  "info" : {
    "author"  : "xcode",
    "version" : 1
  }
}
EOF

else
    cat > "$ICONSET_DIR/Contents.json" << 'EOF'
{
  "images" : [
    { "filename": "app_icon_20.png",          "idiom": "iphone", "scale": "1x", "size": "20x20"       },
    { "filename": "app_icon_20@2x.png",       "idiom": "iphone", "scale": "2x", "size": "20x20"       },
    { "filename": "app_icon_20@3x.png",       "idiom": "iphone", "scale": "3x", "size": "20x20"       },
    { "filename": "app_icon_29.png",          "idiom": "iphone", "scale": "1x", "size": "29x29"       },
    { "filename": "app_icon_29@2x.png",       "idiom": "iphone", "scale": "2x", "size": "29x29"       },
    { "filename": "app_icon_29@3x.png",       "idiom": "iphone", "scale": "3x", "size": "29x29"       },
    { "filename": "app_icon_40.png",          "idiom": "iphone", "scale": "1x", "size": "40x40"       },
    { "filename": "app_icon_40@2x.png",       "idiom": "iphone", "scale": "2x", "size": "40x40"       },
    { "filename": "app_icon_40@3x.png",       "idiom": "iphone", "scale": "3x", "size": "40x40"       },
    { "filename": "app_icon_60@2x.png",       "idiom": "iphone", "scale": "2x", "size": "60x60"       },
    { "filename": "app_icon_60@3x.png",       "idiom": "iphone", "scale": "3x", "size": "60x60"       },
    { "filename": "app_icon_ipad_20.png",     "idiom": "ipad",   "scale": "1x", "size": "20x20"       },
    { "filename": "app_icon_ipad_20@2x.png",  "idiom": "ipad",   "scale": "2x", "size": "20x20"       },
    { "filename": "app_icon_ipad_29.png",     "idiom": "ipad",   "scale": "1x", "size": "29x29"       },
    { "filename": "app_icon_ipad_29@2x.png",  "idiom": "ipad",   "scale": "2x", "size": "29x29"       },
    { "filename": "app_icon_ipad_40.png",     "idiom": "ipad",   "scale": "1x", "size": "40x40"       },
    { "filename": "app_icon_ipad_40@2x.png",  "idiom": "ipad",   "scale": "2x", "size": "40x40"       },
    { "filename": "app_icon_ipad_76.png",     "idiom": "ipad",   "scale": "1x", "size": "76x76"       },
    { "filename": "app_icon_ipad_76@2x.png",  "idiom": "ipad",   "scale": "2x", "size": "76x76"       },
    { "filename": "app_icon_ipad_83@2x.png",  "idiom": "ipad",   "scale": "2x", "size": "83.5x83.5"   },
    { "filename": "app_icon_1024.png",        "idiom": "ios-marketing", "scale": "1x", "size": "1024x1024" }
  ],
  "info" : {
    "author"  : "xcode",
    "version" : 1
  }
}
EOF

fi

echo ""
echo "✅ 完成！共生成 ${#ICONS[@]} 张图标"
echo "📂 $ICONSET_DIR"
echo "=================================================="
