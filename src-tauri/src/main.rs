use std::sync::Mutex;
use tauri::{Manager, Emitter};

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
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &pid.to_string()])
            .status();
    }
}

/// Check if a process is still running (port-based)
fn is_port_listening(port: u16, timeout_ms: u64) -> bool {
    let addr: std::net::SocketAddr = format!("127.0.0.1:{}", port).parse().unwrap();
    std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_millis(timeout_ms)).is_ok()
}

/// Safe mutex lock that handles poisoned mutexes
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

    if is_port_listening(11434, 2000) {
        eprintln!("[INFO] Ollama already running on port 11434, skip spawn");
        return Ok("already running".into());
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
    eprintln!("[INFO] Ollama started PID={}", pid);

    std::thread::spawn(move || {
        match child.wait() {
            Ok(status) => eprintln!("[INFO] Ollama process exited: {}", status),
            Err(e) => eprintln!("[WARN] Ollama process wait failed: {}", e),
        }
    });

    Ok("started".into())
}

#[tauri::command]
fn check_backend_health() -> bool {
    is_port_listening(18088, 2000)
}

#[tauri::command]
fn check_ollama_health() -> bool {
    is_port_listening(11434, 2000)
}

#[tauri::command]
fn save_file(path: String, content: String) -> Result<String, String> {
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

/// Restart Python backend — kills existing process and spawns a new one
#[tauri::command]
fn restart_backend(app: tauri::AppHandle) -> Result<String, String> {
    let state = app.state::<ManagedPids>();

    // Kill existing Python process
    if let Some(pid) = lock_state!(state.python).take() {
        eprintln!("[INFO] Restart: killing Python PID={}", pid);
        kill_tree(pid);
        // Wait for port to free up
        for _ in 0..10 {
            if !is_port_listening(18088, 500) {
                break;
            }
            std::thread::sleep(std::time::Duration::from_millis(500));
        }
    }

    spawn_python_inner(&app, None)
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
            if let Err(e) = spawn_python_inner(app, None) {
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
        .invoke_handler(tauri::generate_handler![
            start_ollama,
            stop_ollama,
            save_file,
            check_backend_health,
            check_ollama_health,
            restart_backend,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

fn spawn_ollama(app: &tauri::App) -> Result<(), Box<dyn std::error::Error>> {
    let state = app.state::<ManagedPids>();
    if lock_state!(state.ollama).is_some() {
        return Ok(());
    }

    if is_port_listening(11434, 2000) {
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
            Ok(status) => eprintln!("[INFO] Ollama process exited: {}", status),
            Err(e) => eprintln!("[WARN] Ollama process wait failed: {}", e),
        }
    });
    Ok(())
}

/// Internal Python spawn logic, shared between setup and restart_backend.
/// `app_handle` is only needed for crash notifications (emit events).
fn spawn_python_inner<R: tauri::Runtime, M: Manager<R>>(app: &M, app_handle: Option<&tauri::AppHandle<R>>) -> Result<String, String> {
    let python_dir = resolve_python_dir();
    let api_path = python_dir.join("api.py");
    if !api_path.exists() {
        return Err(format!("Python API 文件不存在: {}", api_path.display()));
    }
    let api_str = api_path.to_str().expect("path not valid UTF-8").to_string();

    eprintln!("[INFO] Python dir: {}", python_dir.display());

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
        )
        .map_err(|e| format!("启动 Python 失败: {}。请确认 Python 已安装。", e))?;

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
        )
        .map_err(|e| format!("启动 Python 失败: {}。请确认 Python 已安装。", e))?;

    let pid = child.id();
    let state = app.state::<ManagedPids>();
    *lock_state!(state.python) = Some(pid);
    eprintln!("[INFO] Python spawned PID={}", pid);

    // Spawn a monitor thread that reads stdout, stderr, AND detects process exit
    let handle = app_handle.cloned();
    std::thread::spawn(move || {
        use std::io::{BufRead, BufReader};

        // Take stdout/stderr before wait
        let out = child.stdout.take();
        let err = child.stderr.take();

        // Read stdout in a sub-thread
        if let Some(out) = out {
            std::thread::spawn(move || {
                for line in BufReader::new(out).lines().flatten() {
                    println!("[python] {}", line);
                }
            });
        }

        // Read stderr in a sub-thread
        if let Some(err) = err {
            std::thread::spawn(move || {
                for line in BufReader::new(err).lines().flatten() {
                    eprintln!("[python] {}", line);
                }
            });
        }

        // Wait for process exit
        let exit_result = child.wait();
        match &exit_result {
            Ok(status) => {
                eprintln!("[WARN] Python process exited unexpectedly: {}", status);
            }
            Err(e) => {
                eprintln!("[WARN] Python process wait error: {}", e);
            }
        }

        // Notify frontend that backend crashed
        if let Some(h) = handle {
            let _ = h.emit("backend-crashed", serde_json::json!({
                "message": "Python 后端进程意外退出，请重启",
                "exit_status": exit_result.map(|s| s.to_string()).unwrap_or_else(|e| e.to_string())
            }));
        }
    });

    // Verify Python server is actually listening after spawn
    eprintln!("[INFO] Waiting for Python server to be ready...");
    for i in 0..30 {
        std::thread::sleep(std::time::Duration::from_millis(500));
        if is_port_listening(18088, 1000) {
            eprintln!("[INFO] Python server ready after {}ms", (i + 1) * 500);
            return Ok(format!("Python 后端已启动 (PID={})", pid));
        }
    }
    eprintln!("[WARN] Python server did not become ready within 15s, but process is running");
    Ok(format!("Python 进程已启动但未在 15 秒内就绪 (PID={})", pid))
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

        let candidates: Vec<std::path::PathBuf> = vec![
            exe_dir.join("python"),
            exe_dir.join("../../../python").canonicalize().unwrap_or_else(|_| exe_dir.join("../../../python")),
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
