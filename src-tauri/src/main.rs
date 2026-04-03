use std::sync::Mutex;
use tauri::Manager;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

struct ManagedPids {
    python: Mutex<Option<u32>>,
    ollama: Mutex<Option<u32>>,
}

fn kill_tree(pid: u32) {
    eprintln!("[INFO] Killing process tree PID={}", pid);
    let _ = std::process::Command::new("taskkill")
        .args(["/F", "/T", "/PID", &pid.to_string()])
        .spawn();
}

#[tauri::command]
fn start_ollama(state: tauri::State<'_, ManagedPids>) -> Result<String, String> {
    if state.ollama.lock().unwrap().is_some() {
        return Ok("already running".into());
    }

    #[cfg(windows)]
    let mut child = std::process::Command::new("ollama")
        .arg("serve")
        .creation_flags(0x00000010)
        .spawn()
        .map_err(|e| format!("启动 Ollama 失败: {}。请确认 Ollama 已安装。", e))?;

    #[cfg(not(windows))]
    let mut child = std::process::Command::new("ollama")
        .arg("serve")
        .spawn()
        .map_err(|e| format!("启动 Ollama 失败: {}", e))?;

    let pid = child.id();
    *state.ollama.lock().unwrap() = Some(pid);
    eprintln!("[INFO] Ollama started PID={}", pid);

    std::thread::spawn(move || { let _ = child.wait(); });

    Ok("started".into())
}

#[tauri::command]
fn stop_ollama(state: tauri::State<'_, ManagedPids>) -> Result<String, String> {
    if let Some(pid) = state.ollama.lock().unwrap().take() {
        kill_tree(pid);
        Ok("stopped".into())
    } else {
        Ok("not running".into())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.set_focus();
                let _ = w.unminimize();
            }
        }))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(ManagedPids {
            python: Mutex::new(None),
            ollama: Mutex::new(None),
        })
        .setup(|app| {
            if let Err(e) = spawn_python(app) {
                eprintln!("[ERROR] spawn Python: {}", e);
            }
            if let Err(e) = spawn_ollama(app) {
                eprintln!("[WARN] spawn Ollama: {} (可能已在运行)", e);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<ManagedPids>();
                if let Some(pid) = state.python.lock().unwrap().take() {
                    kill_tree(pid);
                }
                // 不杀 Ollama：它是共享服务，其他程序可能也在用
                state.ollama.lock().unwrap().take();
            }
        })
        .invoke_handler(tauri::generate_handler![start_ollama, stop_ollama])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn spawn_ollama(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let state = app.state::<ManagedPids>();
    if state.ollama.lock().unwrap().is_some() {
        return Ok(());
    }

    // 检测 Ollama 是否已经在运行（端口可连接则跳过）
    let addr: std::net::SocketAddr = "127.0.0.1:11434".parse().unwrap();
    if std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(2)).is_ok() {
        eprintln!("[INFO] Ollama already running, skip spawn");
        return Ok(());
    }

    #[cfg(windows)]
    const CREATE_NO_WINDOW: u32 = 0x08000000;

    #[cfg(windows)]
    let mut child = std::process::Command::new("ollama")
        .arg("serve")
        .creation_flags(CREATE_NO_WINDOW)
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| format!("启动 Ollama 失败: {}。请确认 Ollama 已安装。", e))?;

    #[cfg(not(windows))]
    let mut child = std::process::Command::new("ollama")
        .arg("serve")
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|e| format!("启动 Ollama 失败: {}", e))?;

    let pid = child.id();
    *state.ollama.lock().unwrap() = Some(pid);
    eprintln!("[INFO] Ollama spawned PID={}", pid);

    std::thread::spawn(move || { let _ = child.wait(); });
    Ok(())
}

fn spawn_python(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let python_dir = resolve_python_dir();
    let api_path = python_dir.join("api.py");
    let api_str = api_path.to_str().expect("path not valid UTF-8").to_string();

    eprintln!("[INFO] Python dir: {}", python_dir.display());

    let mut child = std::process::Command::new("python")
        .args([&api_str, "--port", "18088"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()?;

    let pid = child.id();
    let state = app.state::<ManagedPids>();
    *state.python.lock().unwrap() = Some(pid);
    eprintln!("[INFO] Python spawned PID={}", pid);

    if let Some(out) = child.stdout.take() {
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            for line in BufReader::new(out).lines().flatten() {
                println!("[python] {}", line);
            }
        });
    }

    if let Some(err) = child.stderr.take() {
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            for line in BufReader::new(err).lines().flatten() {
                eprintln!("[python] {}", line);
            }
        });
    }

    Ok(())
}

fn resolve_python_dir() -> std::path::PathBuf {
    let base = if cfg!(debug_assertions) {
        let manifest = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        manifest.parent().and_then(|p| p.parent())
            .map(|p| p.join("python"))
            .unwrap_or_else(|| manifest.join("..").join("python"))
    } else {
        std::env::current_exe().ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_default()
            .join("python")
    };

    let junction = std::path::PathBuf::from("D:\\pycharm_study\\st\\python");
    if junction.exists() { junction } else { base }
}

fn main() { run() }
