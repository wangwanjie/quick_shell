#!/usr/bin/env bash
# appicon-magick.sh
# 功能：使用 ImageMagick 移除图片背景，可选消除毛边，可选生成 macOS AppIcon.appiconset
#
# 用法：
#   bash ./appicon-magick.sh -i <input> -o <output_dir> [options]
#
# 选项：
#   -i <file>              输入图片路径（必填）
#   -o <dir>               输出目录（必填）
#   --fuzz <percent>       背景色容差，默认 15
#   --bg-color <color>     手动指定背景色，默认自动取左上角像素
#   --defringe <method>    毛边消除方案：erode | smooth | decontam（默认不启用）
#   --defringe-radius <n>  erode 方案腐蚀半径，默认 1
#   --mac-appicon           生成 macOS AppIcon.appiconset
#   -h                     显示帮助

set -euo pipefail

# ============================================================
# 默认值
# ============================================================
INPUT=""
OUTPUT_DIR=""
FUZZ=15
BG_COLOR=""
DEFRINGE_METHOD=""   # erode | smooth | decontam | ""
DEFRINGE_RADIUS=1
MAC_APPICON=false

# ============================================================
# 帮助
# ============================================================
usage() {
    grep '^#' "$0" | head -20 | sed 's/^# \?//'
    exit 0
}

# ============================================================
# 解析参数
# ============================================================
while [[ $# -gt 0 ]]; do
    case "$1" in
        -i)               INPUT="$2";            shift 2 ;;
        -o)               OUTPUT_DIR="$2";       shift 2 ;;
        --fuzz)           FUZZ="$2";             shift 2 ;;
        --bg-color)       BG_COLOR="$2";         shift 2 ;;
        --defringe)       DEFRINGE_METHOD="$2";  shift 2 ;;
        --defringe-radius) DEFRINGE_RADIUS="$2"; shift 2 ;;
        --mac-appicon)    MAC_APPICON=true;       shift   ;;
        -h|--help)        usage ;;
        *) echo "❌ 未知参数: $1"; usage ;;
    esac
done

# ============================================================
# 参数校验
# ============================================================
[[ -z "$INPUT" ]]      && { echo "❌ 缺少 -i 参数（输入文件）"; exit 1; }
[[ -z "$OUTPUT_DIR" ]] && { echo "❌ 缺少 -o 参数（输出目录）"; exit 1; }
[[ ! -f "$INPUT" ]]    && { echo "❌ 输入文件不存在: $INPUT"; exit 1; }

if [[ -n "$DEFRINGE_METHOD" ]] && \
   [[ "$DEFRINGE_METHOD" != "erode" ]] && \
   [[ "$DEFRINGE_METHOD" != "smooth" ]] && \
   [[ "$DEFRINGE_METHOD" != "decontam" ]]; then
    echo "❌ --defringe 只支持：erode | smooth | decontam"
    exit 1
fi

# 检查 ImageMagick
if ! command -v magick &>/dev/null && ! command -v convert &>/dev/null; then
    echo "❌ 未找到 ImageMagick，请先安装：brew install imagemagick"
    exit 1
fi

# 兼容 v6 (convert) 和 v7 (magick)
IM_CMD="magick"
command -v magick &>/dev/null || IM_CMD="convert"

# ============================================================
# 准备输出目录
# ============================================================
mkdir -p "$OUTPUT_DIR"

BASENAME=$(basename "$INPUT")
STEM="${BASENAME%.*}"
OUTPUT_PNG="$OUTPUT_DIR/${STEM}_no_bg.png"

# ============================================================
# 移除背景
# ============================================================
echo "=================================================="
echo "🖼  输入文件  : $INPUT"
echo "📁 输出目录  : $OUTPUT_DIR"
echo "🔧 容差(fuzz): ${FUZZ}%"

# 自动检测背景色（取左上角像素）
if [[ -z "$BG_COLOR" ]]; then
    BG_COLOR=$($IM_CMD "$INPUT" -format "%[pixel:u.p{0,0}]" info: 2>/dev/null || echo "white")
    echo "🎨 自动检测背景色: $BG_COLOR"
else
    echo "🎨 指定背景色    : $BG_COLOR"
fi

echo "⚙️  正在移除背景..."
$IM_CMD "$INPUT" \
    -alpha set \
    -fuzz "${FUZZ}%" \
    -fill none \
    -draw "color 0,0 floodfill" \
    -draw "color %[fx:w-1],0 floodfill" \
    -draw "color 0,%[fx:h-1] floodfill" \
    -draw "color %[fx:w-1],%[fx:h-1] floodfill" \
    "$OUTPUT_PNG"

echo "✅ 背景移除完成: $OUTPUT_PNG"

# ============================================================
# 毛边消除（三种方案可选）
# ============================================================
if [[ -n "$DEFRINGE_METHOD" ]]; then
    echo ""
    echo "✂️  毛边消除方案: $DEFRINGE_METHOD"

    case "$DEFRINGE_METHOD" in

        # ----------------------------------------------------------
        # 方案一：Alpha 通道腐蚀
        # 原理：对 alpha 通道做形态学 Erode，将边缘遮罩向内收缩 N px
        # 适用：图标、产品图等硬边缘，白边/黑边明显时
        # ----------------------------------------------------------
        erode)
            echo "   → 腐蚀半径: ${DEFRINGE_RADIUS}px"
            $IM_CMD "$OUTPUT_PNG" \
                -morphology Erode Diamond:${DEFRINGE_RADIUS} \
                "$OUTPUT_PNG"
            # 腐蚀后做轻微 alpha 平滑，防止出现锯齿
            $IM_CMD "$OUTPUT_PNG" \
                -channel Alpha \
                -blur 0x0.5 \
                -level 30%,100% \
                +channel \
                "$OUTPUT_PNG"
            echo "✅ [erode] 毛边处理完成"
            ;;

        # ----------------------------------------------------------
        # 方案二：高斯模糊 + Alpha 阈值截断（边缘软化）
        # 原理：对 alpha 通道轻微模糊后用 -level 拉伸，
        #       消除半透明过渡像素，同时保留柔和边缘
        # 适用：背景去除后边缘有轻微羽化/半透明残留
        # ----------------------------------------------------------
        smooth)
            echo "   → 执行 alpha blur + level 截断"
            $IM_CMD "$OUTPUT_PNG" \
                -channel Alpha \
                -blur 0x1 \
                -level 50%,100% \
                +channel \
                "$OUTPUT_PNG"
            echo "✅ [smooth] 毛边处理完成"
            ;;

        # ----------------------------------------------------------
        # 方案三：去色溢（Color Decontamination）
        # 原理：边缘半透明像素按 alpha 值缩放 RGB，
        #       抑制原背景色渗入前景的颜色污染（白底/黑底专用）
        # 适用：主体边缘带明显背景颜色渗透（如白色光晕）
        # ----------------------------------------------------------
        decontam)
            echo "   → 执行颜色去污（color decontamination）"
            $IM_CMD "$OUTPUT_PNG" \
                -fx "p.a > 0 ? p * p.a + p * (1 - p.a) * 0 : p" \
                "$OUTPUT_PNG"
            # 再做一次 alpha erode 辅助清边
            $IM_CMD "$OUTPUT_PNG" \
                -morphology Erode Diamond:1 \
                "$OUTPUT_PNG"
            echo "✅ [decontam] 毛边处理完成"
            ;;
    esac
fi

# ============================================================
# 生成 macOS AppIcon.appiconset
# ============================================================
if [[ "$MAC_APPICON" == true ]]; then
    echo ""
    echo "=================================================="
    echo "📦 开始生成 macOS AppIcon.appiconset..."

    ICONSET_DIR="$OUTPUT_DIR/AppIcon.appiconset"
    mkdir -p "$ICONSET_DIR"

    # 格式：filename|px|size标注|scale
    declare -a ICONS=(
        "app_icon_16.png|16|16x16|1x"
        "app_icon_16@2x.png|32|16x16|2x"
        "app_icon_32.png|32|32x32|1x"
        "app_icon_32@2x.png|64|32x32|2x"
        "app_icon_128.png|128|128x128|1x"
        "app_icon_128@2x.png|256|128x128|2x"
        "app_icon_256.png|256|256x256|1x"
        "app_icon_256@2x.png|512|256x256|2x"
        "app_icon_512.png|512|512x512|1x"
        "app_icon_512@2x.png|1024|512x512|2x"
    )


    for entry in "${ICONS[@]}"; do
        IFS='|' read -r filename px size scale <<< "$entry"
        echo "  → ${px}x${px}  ($size @${scale})  →  $filename"
        $IM_CMD "$OUTPUT_PNG" -resize "${px}x${px}" "$ICONSET_DIR/$filename"
    done

    # 生成 Contents.json
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

    echo ""
    echo "✅ AppIcon.appiconset 生成完成: $ICONSET_DIR"
fi

echo ""
echo "=================================================="
echo "🎉 全部完成！"
echo "=================================================="
