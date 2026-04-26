use std::sync::Mutex;
use tauri::{Emitter, Manager};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

struct ManagedProcesses {
    python: Mutex<Option<std::process::Child>>,
    ollama: Mutex<Option<std::process::Child>>,
}

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

fn kill_child(child: &mut std::process::Child) {
    let pid = child.id();
    if child.kill().is_err() {
        kill_tree(pid);
    }
}

fn is_port_listening(port: u16, timeout_ms: u64) -> bool {
    let addr = format!("127.0.0.1:{}", port)
        .parse::<std::net::SocketAddr>()
        .expect("invalid socket address");
    std::net::TcpStream::connect_timeout(&addr, std::time::Duration::from_millis(timeout_ms)).is_ok()
}

macro_rules! lock_state {
    ($lock:expr) => {
        $lock.lock().unwrap_or_else(|e| e.into_inner())
    };
}

const CREATE_NO_WINDOW: u32 = 0x08000000;

fn build_command(program: &str, args: &[&str]) -> std::process::Command {
    let mut cmd = std::process::Command::new(program);
    cmd.args(args);
    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);
    // Remove proxy env vars so httpx doesn't hang trying to connect through a local proxy
    cmd.env_remove("HTTP_PROXY");
    cmd.env_remove("HTTPS_PROXY");
    cmd.env_remove("http_proxy");
    cmd.env_remove("https_proxy");
    cmd.env_remove("ALL_PROXY");
    cmd.env_remove("all_proxy");
    cmd
}

fn pipe_output(child: &mut std::process::Child, label: &str) {
    let out = child.stdout.take();
    let err = child.stderr.take();
    let lo = label.to_string();
    let le = label.to_string();

    if let Some(out) = out {
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            for line in BufReader::new(out).lines().flatten() {
                println!("[{}] {}", lo, line);
            }
        });
    }
    if let Some(err) = err {
        std::thread::spawn(move || {
            use std::io::{BufRead, BufReader};
            for line in BufReader::new(err).lines().flatten() {
                eprintln!("[{}] {}", le, line);
            }
        });
    }
}

#[tauri::command]
fn start_ollama(state: tauri::State<'_, ManagedProcesses>) -> Result<String, String> {
    if lock_state!(state.ollama).is_some() || is_port_listening(11434, 2000) {
        return Ok("already running".into());
    }

    let mut child = build_command("ollama", &["serve"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start Ollama: {}. Please make sure Ollama is installed.", e))?;

    eprintln!("[INFO] Ollama started PID={}", child.id());
    pipe_output(&mut child, "ollama");
    *lock_state!(state.ollama) = Some(child);
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
        return Err("Only .md and .txt files can be saved.".into());
    }
    std::fs::write(&path, content.as_bytes())
        .map(|_| format!("Saved to {}", path))
        .map_err(|e| format!("Failed to save file: {}", e))
}

#[tauri::command]
fn stop_ollama(state: tauri::State<'_, ManagedProcesses>) -> Result<String, String> {
    if let Some(mut child) = lock_state!(state.ollama).take() {
        kill_child(&mut child);
        Ok("stopped".into())
    } else {
        Ok("not running".into())
    }
}

#[tauri::command]
fn restart_backend(app: tauri::AppHandle) -> Result<String, String> {
    let state = app.state::<ManagedProcesses>();

    if let Some(mut child) = lock_state!(state.python).take() {
        eprintln!("[INFO] Restart: killing Python PID={}", child.id());
        kill_child(&mut child);
        for i in 0..60 {
            if !is_port_listening(18088, 500) {
                break;
            }
            if i % 10 == 0 {
                eprintln!("[INFO] Waiting for port 18088 to be freed... ({})", i);
            }
            std::thread::sleep(std::time::Duration::from_millis(500));
        }
    }

    spawn_python_inner(&app, Some(&app))
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
        .plugin(tauri_plugin_fs::init())
        .manage(ManagedProcesses {
            python: Mutex::new(None),
            ollama: Mutex::new(None),
        })
        .setup(|app| {
            if let Err(e) = spawn_python_inner(app, None) {
                eprintln!("[ERROR] spawn Python: {}", e);
                eprintln!("[ERROR] Please make sure Python is installed and available in PATH.");
            }
            if let Err(e) = spawn_ollama(app) {
                eprintln!("[WARN] spawn Ollama: {} (it may already be running)", e);
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { .. } = event {
                let state = window.state::<ManagedProcesses>();
                if let Some(mut child) = lock_state!(state.python).take() {
                    kill_child(&mut child);
                }
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
    let state = app.state::<ManagedProcesses>();
    if lock_state!(state.ollama).is_some() || is_port_listening(11434, 2000) {
        return Ok(());
    }

    let mut child = build_command("ollama", &["serve"])
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .map_err(|e| format!("Failed to start Ollama: {}. Please make sure Ollama is installed.", e))?;

    eprintln!("[INFO] Ollama spawned PID={}", child.id());
    pipe_output(&mut child, "ollama");
    *lock_state!(state.ollama) = Some(child);
    Ok(())
}

fn spawn_python_inner<R: tauri::Runtime, M: Manager<R>>(
    app: &M,
    app_handle: Option<&tauri::AppHandle<R>>,
) -> Result<String, String> {
    let python_dir = resolve_python_dir();

    let mut child = if cfg!(debug_assertions) {
        let api_path = python_dir.join("api.py");
        if !api_path.exists() {
            return Err(format!("Python API file not found: {}", api_path.display()));
        }
        let api_str = api_path
            .to_str()
            .ok_or("Path contains invalid characters")?
            .to_string();
        let python_cmd = if cfg!(windows) { "python" } else { "python3" };
        eprintln!("[INFO] Dev mode: {} {} --port 18088", python_cmd, api_str);

        build_command(python_cmd, &[api_str.as_str(), "--port", "18088"])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .or_else(|_| {
                build_command("python", &[api_str.as_str(), "--port", "18088"])
                    .stdout(std::process::Stdio::piped())
                    .stderr(std::process::Stdio::piped())
                    .spawn()
            })
            .map_err(|e| format!("Failed to start Python: {}. Please make sure Python is installed.", e))?
    } else {
        let api_exe = python_dir.join(if cfg!(windows) { "api.exe" } else { "api" });
        if !api_exe.exists() {
            return Err(format!(
                "Python backend not found: {}. Please reinstall the application.",
                api_exe.display()
            ));
        }
        let api_str = api_exe
            .to_str()
            .ok_or("Path contains invalid characters")?
            .to_string();
        eprintln!("[INFO] Release mode: {} --port 18088", api_str);

        build_command(&api_str, &["--port", "18088"])
            .stdout(std::process::Stdio::piped())
            .stderr(std::process::Stdio::piped())
            .spawn()
            .map_err(|e| format!("Failed to start backend: {}", e))?
    };

    let pid = child.id();
    let state = app.state::<ManagedProcesses>();

    pipe_output(&mut child, "python");
    *lock_state!(state.python) = Some(child);

    eprintln!("[INFO] Python spawned PID={}", pid);

    if let Some(h) = app_handle.cloned() {
        std::thread::spawn(move || {
            std::thread::sleep(std::time::Duration::from_secs(15));
            loop {
                std::thread::sleep(std::time::Duration::from_secs(30));
                if !is_port_listening(18088, 1000) {
                    eprintln!("[WARN] Python backend port not responding");
                    let _ = h.emit(
                        "backend-crashed",
                        serde_json::json!({
                            "message": "Python backend may have exited. Please restart it.",
                        }),
                    );
                    break;
                }
            }
        });
    }

    eprintln!("[INFO] Waiting for Python server to be ready...");
    for i in 0..30 {
        std::thread::sleep(std::time::Duration::from_millis(500));
        if is_port_listening(18088, 1000) {
            eprintln!("[INFO] Python server ready after {}ms", (i + 1) * 500);
            return Ok(format!("Python backend started (PID={})", pid));
        }
    }
    Ok(format!(
        "Python process started but was not ready within 15 seconds (PID={})",
        pid
    ))
}

fn resolve_python_dir() -> std::path::PathBuf {
    if cfg!(debug_assertions) {
        let manifest = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        manifest
            .parent()
            .map(|p| p.join("python"))
            .unwrap_or_else(|| manifest.join("python"))
    } else {
        let exe_dir = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.to_path_buf()))
            .unwrap_or_default();
        exe_dir.join("python-dist").join("api")
    }
}

fn main() {
    run()
}
