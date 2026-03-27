#!/usr/bin/env bash

set -euo pipefail

fail() {
    echo "error: $*" >&2
    exit 1
}

usage() {
    cat <<'EOF'
Usage:
  ./create_pretty_dmg.sh \
    --app-path "/path/to/Xcode.app" \
    --dmg-name "Xcode" \
    [--append-version] \
    [--append-build] \
    [--output-dir "/path/to/output"]

Options:
  --app-path PATH      Path to the source .app bundle
  --dmg-name NAME      Base name used for the DMG file name and mounted volume
  --append-version     Read the app version and append it to NAME values
  --append-build       Read the app build version and append it to NAME values
  --output-dir PATH    Output directory for the final DMG. Default: current directory
  -h, --help           Show this help message

Examples:
  ./create_pretty_dmg.sh \
    --app-path "./Xcode_26.3.app" \
    --dmg-name "Xcode" \
    --append-version \
    --append-build
EOF
}

require_command() {
    local command_name="$1"
    command -v "$command_name" >/dev/null 2>&1 || fail "missing required command: $command_name"
}

DMG_BACKGROUND_WIDTH=620
DMG_BACKGROUND_HEIGHT=360
DMG_LEFT_PANEL_X=58
DMG_LEFT_PANEL_Y=72
DMG_RIGHT_PANEL_X=370
DMG_RIGHT_PANEL_Y=72
DMG_PANEL_WIDTH=192
DMG_PANEL_HEIGHT=168
DMG_HEADER_Y=250
DMG_HEADER_HEIGHT=110
DMG_ARROW_START_X=254
DMG_ARROW_END_X=338
DMG_ARROW_Y=156
DMG_ARROW_HEAD_LEFT_X=326
DMG_ARROW_HEAD_TIP_X=364
DMG_ARROW_HEAD_TOP_Y=178
DMG_ARROW_HEAD_BOTTOM_Y=134
FINDER_ICON_SIZE=96
FINDER_TEXT_SIZE=13
FINDER_LABEL_VERTICAL_GAP=4
FINDER_LABEL_MAX_WIDTH=140
FINDER_SINGLE_LINE_LABEL_HEIGHT=16
FINDER_CENTER_Y_OFFSET=18
SWIFT_MODULE_CACHE_PATH="${TMPDIR:-/tmp}/create_pretty_dmg-swift-module-cache"

read_plist_value() {
    local plist_path="$1"
    local key="$2"

    if [[ ! -f "$plist_path" ]]; then
        return 0
    fi

    /usr/libexec/PlistBuddy -c "Print :$key" "$plist_path" 2>/dev/null || true
}

read_app_version() {
    local app_path="$1"
    local version=""

    version="$(read_plist_value "$app_path/Contents/version.plist" "CFBundleShortVersionString")"
    if [[ -z "$version" ]]; then
        version="$(read_plist_value "$app_path/Contents/Info.plist" "CFBundleShortVersionString")"
    fi

    printf '%s' "$version"
}

read_app_build() {
    local app_path="$1"
    local build=""

    build="$(read_plist_value "$app_path/Contents/version.plist" "ProductBuildVersion")"
    if [[ -z "$build" ]]; then
        build="$(read_plist_value "$app_path/Contents/version.plist" "CFBundleVersion")"
    fi
    if [[ -z "$build" ]]; then
        build="$(read_plist_value "$app_path/Contents/Info.plist" "CFBundleVersion")"
    fi

    printf '%s' "$build"
}

append_metadata_suffixes() {
    local base_name="$1"
    local version="$2"
    local build="$3"
    local append_version="$4"
    local append_build="$5"
    local final_name="$base_name"

    if [[ "$append_version" == true ]]; then
        [[ -n "$version" ]] || fail "version requested but not found in app bundle"
        final_name+="_v$version"
    fi

    if [[ "$append_build" == true ]]; then
        [[ -n "$build" ]] || fail "build requested but not found in app bundle"
        final_name+="_$build"
    fi

    printf '%s' "$final_name"
}

app_bundle_display_name() {
    local app_path="$1"
    local app_name

    app_name="$(basename "$app_path")"
    printf '%s' "${app_name%.app}"
}

strip_dmg_extension() {
    local name="$1"
    printf '%s' "${name%.dmg}"
}

absolute_path() {
    local path="$1"
    local dir_path
    local base_name

    dir_path="$(dirname "$path")"
    base_name="$(basename "$path")"

    if [[ -d "$dir_path" ]]; then
        dir_path="$(cd "$dir_path" && pwd)"
    elif [[ "$dir_path" != /* ]]; then
        dir_path="$(cd . && pwd)/$dir_path"
    fi

    printf '%s/%s' "$dir_path" "$base_name"
}

format_dmg_path_log_line() {
    local dmg_path="$1"
    printf 'DMG_PATH: %s' "$(absolute_path "$dmg_path")"
}

finder_disk_reference() {
    local mounted_volume_path="$1"
    printf 'disk (POSIX file "%s" as alias)' "$(escape_applescript_string "$mounted_volume_path")"
}

escape_applescript_string() {
    local value="$1"
    value="${value//\\/\\\\}"
    value="${value//\"/\\\"}"
    printf '%s' "$value"
}

panel_center_x() {
    local panel_x="$1"
    local panel_width="$2"

    printf '%s' $((panel_x + panel_width / 2))
}

panel_center_y_in_finder() {
    local panel_y="$1"
    local panel_height="$2"

    printf '%s' $((DMG_BACKGROUND_HEIGHT - panel_y - panel_height / 2))
}

calculate_centered_item_position() {
    local panel_x="$1"
    local panel_y="$2"
    local panel_width="$3"
    local panel_height="$4"
    local icon_size="$5"
    local label_height="$6"
    local center_x
    local center_y
    local label_delta
    local item_y

    center_x="$(panel_center_x "$panel_x" "$panel_width")"
    center_y="$(panel_center_y_in_finder "$panel_y" "$panel_height")"
    label_delta=$((label_height - FINDER_SINGLE_LINE_LABEL_HEIGHT))
    item_y=$((center_y - FINDER_CENTER_Y_OFFSET - label_delta / 2))

    printf '%s %s' "$center_x" "$item_y"
}

measure_finder_label_height() {
    local label_text="$1"

    mkdir -p "$SWIFT_MODULE_CACHE_PATH"
    CLANG_MODULE_CACHE_PATH="$SWIFT_MODULE_CACHE_PATH" /usr/bin/swift - "$label_text" "$FINDER_LABEL_MAX_WIDTH" "$FINDER_TEXT_SIZE" <<'SWIFT'
import AppKit
import Foundation

guard CommandLine.arguments.count >= 4 else {
    fputs("Error: Missing label measurement arguments\n", stderr)
    exit(1)
}

let text = CommandLine.arguments[1]
let maxWidth = CGFloat(Double(CommandLine.arguments[2]) ?? 140)
let fontSize = CGFloat(Double(CommandLine.arguments[3]) ?? 13)
let paragraph = NSMutableParagraphStyle()
paragraph.alignment = .center
paragraph.lineBreakMode = .byWordWrapping

let attributes: [NSAttributedString.Key: Any] = [
    .font: NSFont.systemFont(ofSize: fontSize),
    .paragraphStyle: paragraph
]

let rect = (text as NSString).boundingRect(
    with: NSSize(width: maxWidth, height: .greatestFiniteMagnitude),
    options: [.usesLineFragmentOrigin, .usesFontLeading],
    attributes: attributes
)

let height = max(Int(ceil(rect.height)), Int(ceil(fontSize)))
print(height)
SWIFT
}

generate_dmg_background() {
    local output_path="$1"
    local target_name="$2"

    mkdir -p "$SWIFT_MODULE_CACHE_PATH"
    CLANG_MODULE_CACHE_PATH="$SWIFT_MODULE_CACHE_PATH" /usr/bin/swift - \
        "$output_path" \
        "$target_name" \
        "$DMG_BACKGROUND_WIDTH" \
        "$DMG_BACKGROUND_HEIGHT" \
        "$DMG_HEADER_Y" \
        "$DMG_HEADER_HEIGHT" \
        "$DMG_LEFT_PANEL_X" \
        "$DMG_LEFT_PANEL_Y" \
        "$DMG_RIGHT_PANEL_X" \
        "$DMG_RIGHT_PANEL_Y" \
        "$DMG_PANEL_WIDTH" \
        "$DMG_PANEL_HEIGHT" \
        "$DMG_ARROW_START_X" \
        "$DMG_ARROW_END_X" \
        "$DMG_ARROW_Y" \
        "$DMG_ARROW_HEAD_LEFT_X" \
        "$DMG_ARROW_HEAD_TIP_X" \
        "$DMG_ARROW_HEAD_TOP_Y" \
        "$DMG_ARROW_HEAD_BOTTOM_Y" <<'SWIFT'
import Cocoa
import Foundation

guard CommandLine.arguments.count >= 20 else {
    fputs("Error: Missing arguments\n", stderr)
    exit(1)
}

let outputPath = CommandLine.arguments[1]
let targetName = CommandLine.arguments[2]
let imageWidth = CGFloat(Double(CommandLine.arguments[3]) ?? 620)
let imageHeight = CGFloat(Double(CommandLine.arguments[4]) ?? 360)
let headerY = CGFloat(Double(CommandLine.arguments[5]) ?? 250)
let headerHeight = CGFloat(Double(CommandLine.arguments[6]) ?? 110)
let leftPanelX = CGFloat(Double(CommandLine.arguments[7]) ?? 58)
let leftPanelY = CGFloat(Double(CommandLine.arguments[8]) ?? 72)
let rightPanelX = CGFloat(Double(CommandLine.arguments[9]) ?? 370)
let rightPanelY = CGFloat(Double(CommandLine.arguments[10]) ?? 72)
let panelWidth = CGFloat(Double(CommandLine.arguments[11]) ?? 192)
let panelHeight = CGFloat(Double(CommandLine.arguments[12]) ?? 168)
let arrowStartX = CGFloat(Double(CommandLine.arguments[13]) ?? 254)
let arrowEndX = CGFloat(Double(CommandLine.arguments[14]) ?? 338)
let arrowY = CGFloat(Double(CommandLine.arguments[15]) ?? 156)
let arrowHeadLeftX = CGFloat(Double(CommandLine.arguments[16]) ?? 326)
let arrowHeadTipX = CGFloat(Double(CommandLine.arguments[17]) ?? 364)
let arrowHeadTopY = CGFloat(Double(CommandLine.arguments[18]) ?? 178)
let arrowHeadBottomY = CGFloat(Double(CommandLine.arguments[19]) ?? 134)
let titleText = "Drag \(targetName) to Applications"
let subtitleText = "Install by dragging it onto the Applications shortcut"

class BackgroundView: NSView {
    private enum Constants {
        static let backgroundColor = NSColor(srgbRed: 0.95, green: 0.97, blue: 0.98, alpha: 1)
        static let topGradientColor = NSColor(srgbRed: 0.80, green: 0.90, blue: 0.95, alpha: 1)
        static let accentColor = NSColor(calibratedRed: 0.11, green: 0.43, blue: 0.63, alpha: 1)
        static let textColor = NSColor(srgbRed: 0.10, green: 0.17, blue: 0.24, alpha: 1)
        static let subtitleColor = NSColor(srgbRed: 0.28, green: 0.35, blue: 0.42, alpha: 1)
        static let panelFillColor = NSColor(srgbRed: 1, green: 1, blue: 1, alpha: 0.94)
        static let panelStrokeColor = NSColor(srgbRed: 0.73, green: 0.83, blue: 0.90, alpha: 1)
        static let cornerRadius: CGFloat = 24
        static let panelCornerRadius: CGFloat = 26
        static let panelStrokeWidth: CGFloat = 2
        static let titleFont = NSFont(name: "Avenir Next Demi Bold", size: 26) ?? .systemFont(ofSize: 26, weight: .semibold)
        static let subtitleFont = NSFont(name: "Avenir Next Regular", size: 14) ?? .systemFont(ofSize: 14)
    }

    private let title: String
    private let subtitle: String

    init(frame frameRect: NSRect, title: String, subtitle: String) {
        self.title = title
        self.subtitle = subtitle
        super.init(frame: frameRect)
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func draw(_ dirtyRect: NSRect) {
        let path = NSBezierPath(roundedRect: bounds, xRadius: Constants.cornerRadius, yRadius: Constants.cornerRadius)
        Constants.backgroundColor.setFill()
        path.fill()

        let headerRect = NSRect(x: 0, y: headerY, width: bounds.width, height: headerHeight)
        let gradient = NSGradient(starting: Constants.topGradientColor, ending: Constants.backgroundColor)!
        gradient.draw(in: headerRect, angle: -90)

        drawText(title, font: Constants.titleFont, color: Constants.textColor, in: NSRect(x: 45, y: 286, width: 530, height: 34))
        drawText(subtitle, font: Constants.subtitleFont, color: Constants.subtitleColor, in: NSRect(x: 70, y: 242, width: 480, height: 24))

        drawPanel(NSRect(x: leftPanelX, y: leftPanelY, width: panelWidth, height: panelHeight))
        drawPanel(NSRect(x: rightPanelX, y: rightPanelY, width: panelWidth, height: panelHeight))

        let arrowBody = NSBezierPath()
        arrowBody.move(to: NSPoint(x: arrowStartX, y: arrowY))
        arrowBody.line(to: NSPoint(x: arrowEndX, y: arrowY))
        Constants.accentColor.setStroke()
        arrowBody.lineWidth = 14
        arrowBody.stroke()

        let arrowHead = NSBezierPath()
        arrowHead.move(to: NSPoint(x: arrowHeadLeftX, y: arrowHeadTopY))
        arrowHead.line(to: NSPoint(x: arrowHeadTipX, y: arrowY))
        arrowHead.line(to: NSPoint(x: arrowHeadLeftX, y: arrowHeadBottomY))
        arrowHead.close()
        Constants.accentColor.setFill()
        arrowHead.fill()
    }

    private func drawPanel(_ rect: NSRect) {
        let path = NSBezierPath(roundedRect: rect, xRadius: Constants.panelCornerRadius, yRadius: Constants.panelCornerRadius)
        Constants.panelFillColor.setFill()
        path.fill()
        Constants.panelStrokeColor.setStroke()
        path.lineWidth = Constants.panelStrokeWidth
        path.stroke()
    }

    private func drawText(_ text: String, font: NSFont, color: NSColor, in rect: NSRect) {
        let paragraph = NSMutableParagraphStyle()
        paragraph.alignment = .center
        let attributes: [NSAttributedString.Key: Any] = [
            .font: font,
            .foregroundColor: color,
            .paragraphStyle: paragraph
        ]
        (text as NSString).draw(in: rect, withAttributes: attributes)
    }
}

let frame = NSRect(x: 0, y: 0, width: imageWidth, height: imageHeight)
let view = BackgroundView(frame: frame, title: titleText, subtitle: subtitleText)

guard let bitmapRep = view.bitmapImageRepForCachingDisplay(in: frame) else {
    fputs("Error: Could not create bitmap rep\n", stderr)
    exit(1)
}

view.cacheDisplay(in: frame, to: bitmapRep)

guard let pngData = bitmapRep.representation(using: .png, properties: [:]) else {
    fputs("Error: Could not generate PNG data\n", stderr)
    exit(1)
}

do {
    try pngData.write(to: URL(fileURLWithPath: outputPath))
} catch {
    fputs("Error: \(error.localizedDescription)\n", stderr)
    exit(1)
}
SWIFT
}

create_pretty_dmg() {
    local app_path="$1"
    local dmg_path="$2"
    local volume_name="$3"
    local target_name="$4"
    local work_dir
    local background_dir
    local background_path
    local sparse_path
    local attach_output
    local device
    local mounted_volume_path
    local finder_disk_ref
    local app_name
    local app_size_kb
    local dmg_size_kb
    local escaped_app_name
    local app_label_height
    local applications_label_height
    local app_position
    local applications_position
    local app_position_x
    local app_position_y
    local applications_position_x
    local applications_position_y
    local osascript_status

    work_dir="$(mktemp -d "${TMPDIR:-/tmp}/pretty-dmg.XXXXXX")"
    background_dir="$work_dir/.background"
    background_path="$background_dir/installer-background.png"
    sparse_path="$work_dir/$(basename "${dmg_path%.dmg}").sparseimage"
    app_name="$(basename "$app_path")"
    escaped_app_name="$(escape_applescript_string "$app_name")"

    mkdir -p "$background_dir"
    generate_dmg_background "$background_path" "$target_name"
    app_label_height="$(measure_finder_label_height "$app_name")"
    applications_label_height="$(measure_finder_label_height "Applications")"
    app_position="$(calculate_centered_item_position "$DMG_LEFT_PANEL_X" "$DMG_LEFT_PANEL_Y" "$DMG_PANEL_WIDTH" "$DMG_PANEL_HEIGHT" "$FINDER_ICON_SIZE" "$app_label_height")"
    applications_position="$(calculate_centered_item_position "$DMG_RIGHT_PANEL_X" "$DMG_RIGHT_PANEL_Y" "$DMG_PANEL_WIDTH" "$DMG_PANEL_HEIGHT" "$FINDER_ICON_SIZE" "$applications_label_height")"
    read -r app_position_x app_position_y <<< "$app_position"
    read -r applications_position_x applications_position_y <<< "$applications_position"

    app_size_kb="$(du -sk "$app_path" | awk '{print $1}')"
    dmg_size_kb=$((app_size_kb + 1024 * 1024))

    hdiutil create \
        -size "${dmg_size_kb}k" \
        -fs HFS+ \
        -volname "$volume_name" \
        -type SPARSE \
        -ov \
        "$sparse_path" >/dev/null

    attach_output="$(hdiutil attach -readwrite -noverify -noautoopen "$sparse_path")"
    device="$(printf '%s\n' "$attach_output" | awk -F '\t' '/\/Volumes\// {print $1; exit}')"
    mounted_volume_path="$(printf '%s\n' "$attach_output" | awk -F '\t' '/\/Volumes\// {print $NF; exit}')"
    finder_disk_ref="$(finder_disk_reference "$mounted_volume_path")"

    if [[ -z "$device" || -z "$mounted_volume_path" ]]; then
        rm -rf "$work_dir"
        fail "failed to mount temporary DMG"
    fi

    mkdir -p "$mounted_volume_path/.background" "$mounted_volume_path/.fseventsd"
    cp "$background_path" "$mounted_volume_path/.background/installer-background.png"
    touch "$mounted_volume_path/.fseventsd/no_log"
    ln -s /Applications "$mounted_volume_path/Applications"
    ditto "$app_path" "$mounted_volume_path/$app_name"

    chflags hidden "$mounted_volume_path/.background" 2>/dev/null || true
    chflags hidden "$mounted_volume_path/.fseventsd" 2>/dev/null || true

    set +e
    osascript <<EOF
tell application "Finder"
    set dmgDisk to $finder_disk_ref
    tell dmgDisk
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set bounds of container window to {220, 120, 840, 520}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to $FINDER_ICON_SIZE
        set text size of viewOptions to $FINDER_TEXT_SIZE
        set background picture of viewOptions to file ".background:installer-background.png"
        set position of item "$escaped_app_name" of container window to {$app_position_x, $app_position_y}
        set position of item "Applications" of container window to {$applications_position_x, $applications_position_y}
        try
            set position of item ".background" of container window to {860, 320}
        end try
        try
            set position of item ".fseventsd" of container window to {960, 320}
        end try
        close
        open
        update without registering applications
        delay 2
    end tell
end tell
EOF
    osascript_status=$?
    set -e

    sync
    sleep 1
    hdiutil detach "$mounted_volume_path" >/dev/null || hdiutil detach "$device" -force >/dev/null

    if [[ "$osascript_status" -ne 0 ]]; then
        rm -rf "$work_dir"
        return "$osascript_status"
    fi

    hdiutil convert "$sparse_path" -format UDZO -imagekey zlib-level=9 -o "$dmg_path" >/dev/null
    rm -rf "$work_dir"
}

main() {
    local app_path=""
    local dmg_name=""
    local output_dir="."
    local append_version=false
    local append_build=false
    local version=""
    local build=""
    local effective_target_name
    local effective_dmg_name
    local dmg_path

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --app-path)
                app_path="${2:-}"
                shift 2
                ;;
            --dmg-name)
                dmg_name="${2:-}"
                shift 2
                ;;
            --append-version)
                append_version=true
                shift
                ;;
            --append-build)
                append_build=true
                shift
                ;;
            --output-dir)
                output_dir="${2:-}"
                shift 2
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            *)
                fail "unknown argument: $1"
                ;;
        esac
    done

    [[ -n "$app_path" ]] || fail "--app-path is required"
    [[ -n "$dmg_name" ]] || fail "--dmg-name is required"
    [[ -d "$app_path" ]] || fail "app bundle not found: $app_path"

    require_command ditto
    require_command du
    require_command hdiutil
    require_command osascript
    require_command swift

    mkdir -p "$output_dir"

    version="$(read_app_version "$app_path")"
    build="$(read_app_build "$app_path")"
    effective_target_name="$(app_bundle_display_name "$app_path")"
    effective_dmg_name="$(append_metadata_suffixes "$(strip_dmg_extension "$dmg_name")" "$version" "$build" "$append_version" "$append_build")"
    dmg_path="$output_dir/$effective_dmg_name.dmg"

    rm -f "$dmg_path"

    echo "creating DMG: $dmg_path"
    create_pretty_dmg "$app_path" "$dmg_path" "$effective_dmg_name" "$effective_target_name"
    echo "done: $dmg_path"
    format_dmg_path_log_line "$dmg_path"
    printf '\n'
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
