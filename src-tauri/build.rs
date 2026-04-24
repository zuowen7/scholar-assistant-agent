fn main() {
    let resource_dir = std::path::Path::new("python-dist");
    if !resource_dir.exists() {
        std::fs::create_dir_all(resource_dir).expect("failed to create python-dist resource dir");
    }

    // Use icon from ASCII-only target path to avoid windres issues
    // with non-ASCII project directory names on Windows
    let icon_path = std::path::Path::new("D:\\cargo-target\\scholar-translate\\icons\\icon.ico");
    if !icon_path.exists() {
        if let Some(parent) = icon_path.parent() {
            std::fs::create_dir_all(parent).expect("failed to create icon target dir");
        }
        std::fs::copy("icons\\icon.ico", icon_path).expect("failed to copy icon to target dir");
    }

    let attrs = tauri_build::Attributes::new()
        .windows_attributes(tauri_build::WindowsAttributes::new().window_icon_path(icon_path));
    tauri_build::try_build(attrs).expect("failed to run build script");
}
