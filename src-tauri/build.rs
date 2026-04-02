fn main() {
    // Use icon from ASCII-only target path to avoid windres issues
    // with non-ASCII project directory names on Windows
    let icon_path = std::path::Path::new("D:\\cargo-target\\scholar-translate\\icons\\icon.ico");
    let attrs = tauri_build::Attributes::new()
        .windows_attributes(tauri_build::WindowsAttributes::new().window_icon_path(icon_path));
    tauri_build::try_build(attrs).expect("failed to run build script");
}
