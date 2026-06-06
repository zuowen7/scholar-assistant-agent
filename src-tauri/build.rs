fn main() {
    let resource_dir = std::path::Path::new("python-dist");
    if !resource_dir.exists() {
        std::fs::create_dir_all(resource_dir).expect("failed to create python-dist resource dir");
    }

    let icon_path = std::path::Path::new("icons/icon.ico");

    let attrs = tauri_build::Attributes::new()
        .windows_attributes(tauri_build::WindowsAttributes::new().window_icon_path(icon_path));

    if cfg!(debug_assertions) {
        println!("cargo:rerun-if-changed=python-dist");
    }

    tauri_build::try_build(attrs).expect("failed to run build script");
}
