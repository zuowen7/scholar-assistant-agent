use std::sync::Mutex;
use tauri::Manager;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

struct ManagedPids {
    python: Mutex<Option<u32>>,
    ollama: Mutex<Option<u32>>,
}

/// Kill a process tree (cross-platform)
fn kill_tree(pid: u32) {
    eprintln!("[INFO] Killing process tree PID={}", pid);
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .status(); // BUG-22: use .status() to wait for completion
    }
    #[cfg(not(windows))]
    {
        // BUG-05: use kill on Unix
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status();
    }
}

/// BUG-21: Safe mutex lock that handles poisoned mutexes
macro_rules! lock_state {
    ($lock:expr) => {
        $lock.lock().unwrap_or_else(|e| e.into_inner())
    };
}

#[tauri::command]
fn start_ollama(state: tauri::State<'_, ManagedPids>) -> Result<String, String> {
    if lock_state!(state.ollama).is_some() {
        return Ok("already running".into());
    }

    // Pre-check: is Ollama already running on port 11434?
    let addr: std::net::SocketAddr = "127.0.0.1:11434".parse().unwrap();
    if std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(2)).is_ok() {
        eprintln!("[INFO] Ollama already running on port 11434, skip spawn");
        return Ok("already running".into());
    }

    // BUG-12: consistent CREATE_NO_WINDOW
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
    *lock_state!(state.ollama) = Some(pid);
    eprintln!("[INFO] Ollama started PID={}", pid);

    std::thread::spawn(move || {
        match child.wait() {
            Ok(status) => eprintln!("[INFO] Process exited: {}", status),
            Err(e) => eprintln!("[WARN] Process wait failed: {}", e),
        }
    });

    Ok("started".into())
}

#[tauri::command]
fn check_backend_health() -> bool {
    let addr: std::net::SocketAddr = "127.0.0.1:18088".parse().unwrap();
    std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(2)).is_ok()
}

#[tauri::command]
fn check_ollama_health() -> bool {
    let addr: std::net::SocketAddr = "127.0.0.1:11434".parse().unwrap();
    std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(2)).is_ok()
}

#[tauri::command]
fn save_file(path: String, content: String) -> Result<String, String> {
    // BUG-01: validate file extension to prevent arbitrary file write
    let ext = std::path::Path::new(&path)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_lowercase();

    if !["md", "txt"].contains(&ext.as_str()) {
        return Err("仅支持保存 .md 或 .txt 文件".into());
    }

    std::fs::write(&path, content.as_bytes())
        .map(|_| format!("已保存到 {}", path))
        .map_err(|e| format!("保存失败: {}", e))
}

#[tauri::command]
fn stop_ollama(state: tauri::State<'_, ManagedPids>) -> Result<String, String> {
    if let Some(pid) = lock_state!(state.ollama).take() {
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
        .plugin(tauri_plugin_dialog::init())
        .manage(ManagedPids {
            python: Mutex::new(None),
            ollama: Mutex::new(None),
        })
        .setup(|app| {
            if let Err(e) = spawn_python(app) {
                eprintln!("[ERROR] spawn Python: {}", e);
                eprintln!("[ERROR] 请确认 Python 已安装并在 PATH 中，且已安装所需依赖 (pip install -r python/requirements.txt)");
            }
            if let Err(e) = spawn_ollama(app) {
                eprintln!("[WARN] spawn Ollama: {} (可能已在运行)", e);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<ManagedPids>();
                if let Some(pid) = lock_state!(state.python).take() {
                    kill_tree(pid);
                }
                // 不杀 Ollama：它是共享服务，其他程序可能也在用
                lock_state!(state.ollama).take();
            }
        })
        .invoke_handler(tauri::generate_handler![start_ollama, stop_ollama, save_file, check_backend_health, check_ollama_health])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn spawn_ollama(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let state = app.state::<ManagedPids>();
    if lock_state!(state.ollama).is_some() {
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
    *lock_state!(state.ollama) = Some(pid);
    eprintln!("[INFO] Ollama spawned PID={}", pid);

    std::thread::spawn(move || {
        match child.wait() {
            Ok(status) => eprintln!("[INFO] Process exited: {}", status),
            Err(e) => eprintln!("[WARN] Process wait failed: {}", e),
        }
    });
    Ok(())
}

fn spawn_python(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let python_dir = resolve_python_dir();
    let api_path = python_dir.join("api.py");
    let api_str = api_path.to_str().expect("path not valid UTF-8").to_string();

    eprintln!("[INFO] Python dir: {}", python_dir.display());

    // Windows: python; Linux/macOS: python3
    let python_cmd = if cfg!(windows) { "python" } else { "python3" };

    #[cfg(windows)]
    const CREATE_NO_WINDOW: u32 = 0x08000000;

    #[cfg(windows)]
    let mut child = std::process::Command::new(python_cmd)
        .args([&api_str, "--port", "18088"])
        .creation_flags(CREATE_NO_WINDOW)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .or_else(|_| std::process::Command::new("python")
            .args([&api_str, "--port", "18088"])
            .creation_flags(CREATE_NO_WINDOW)
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
        )?;

    #[cfg(not(windows))]
    let mut child = std::process::Command::new(python_cmd)
        .args([&api_str, "--port", "18088"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .or_else(|_| std::process::Command::new("python")
            .args([&api_str, "--port", "18088"])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
        )?;

    let pid = child.id();
    let state = app.state::<ManagedPids>();
    *lock_state!(state.python) = Some(pid);
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

    // BUG-23: verify Python server is actually listening after spawn
    eprintln!("[INFO] Waiting for Python server to be ready...");
    for i in 0..30 {
        std::thread::sleep(std::time::Duration::from_millis(500));
        let addr: std::net::SocketAddr = "127.0.0.1:18088".parse().unwrap();
        if std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_secs(1)).is_ok() {
            eprintln!("[INFO] Python server ready after {}ms", (i + 1) * 500);
            return Ok(());
        }
    }
    eprintln!("[WARN] Python server did not become ready within 15s, but process is running");

    Ok(())
}

fn resolve_python_dir() -> std::path::PathBuf {
    if cfg!(debug_assertions) {
        let manifest = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        manifest.parent()
            .map(|p| p.join("python"))
            .unwrap_or_else(|| manifest.join("python"))
    } else {
        let exe_dir = std::env::current_exe().ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_default();

        // 按优先级搜索: exe 同级 > 项目开发目录 > 兜底
        let candidates: Vec<std::path::PathBuf> = vec![
            exe_dir.join("python"),                          // NSIS 安装: python 在 exe 旁
            exe_dir.join("../../../python").canonicalize().unwrap_or_else(|_| exe_dir.join("../../../python")), // 开发构建
        ];
        for dir in &candidates {
            if dir.exists() {
                return dir.clone();
            }
        }

        exe_dir.join("python")
    }
}

fn main() { run() }
