fn main() {
    let resource_dir = std::path::Path::new("python-dist");
    if !resource_dir.exists() {
        std::fs::create_dir_all(resource_dir).expect("failed to create python-dist resource dir");
    }

    let icon_path = std::path::Path::new("D:\\cargo-target\\scholar-translate\\icons\\icon.ico");
    if !icon_path.exists() {
        if let Some(parent) = icon_path.parent() {
            std::fs::create_dir_all(parent).expect("failed to create icon target dir");
        }
        std::fs::copy("icons\\icon.ico", icon_path).expect("failed to copy icon to target dir");
    }

    let attrs = tauri_build::Attributes::new()
        .windows_attributes(tauri_build::WindowsAttributes::new().window_icon_path(icon_path));

    // In debug builds, emit rerun-if-changed only for the top-level python-dist
    // directory to avoid Windows quota exhaustion (8200+ files exceed OS limits).
    // In release builds, tauri_build handles full resource tracking for bundling.
    if cfg!(debug_assertions) {
        println!("cargo:rerun-if-changed=python-dist");
    }

    tauri_build::try_build(attrs).expect("failed to run build script");
}
