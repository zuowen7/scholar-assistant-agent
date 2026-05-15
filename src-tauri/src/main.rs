use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tauri::{Emitter, Manager};

static HEALTH_MONITOR_RUNNING: AtomicBool = AtomicBool::new(false);

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

fn wait_or_kill(child: &mut std::process::Child, timeout: std::time::Duration) {
    // Ask the process to exit gracefully first
    #[cfg(not(windows))]
    {
        let _ = std::process::Command::new("kill")
            .args(["-TERM", &child.id().to_string()])
            .status();
    }
    #[cfg(windows)]
    {
        let _ = std::process::Command::new("taskkill")
            .args(["/PID", &child.id().to_string()])
            .status();
    }

    // Poll for up to `timeout` for a graceful exit, then force-kill
    let deadline = std::time::Instant::now() + timeout;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return, // process exited
            Ok(None) => {}
            Err(_) => break,
        }
        if std::time::Instant::now() >= deadline {
            break;
        }
        std::thread::sleep(std::time::Duration::from_millis(200));
    }
    kill_child(child);
}

fn kill_child(child: &mut std::process::Child) {
    let pid = child.id();
    if child.kill().is_err() {
        kill_tree(pid);
    }
    // Reap the zombie so the OS cleans up the entry from the process table
    let _ = child.wait();
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

/// Reject calls that did not originate from the main window.
/// Sensitive management commands (start/stop Ollama, restart backend) should
/// only be invocable from the primary UI window, not from any embedded webview.
fn require_main_window(window: &tauri::WebviewWindow) -> Result<(), String> {
    if window.label() != "main" {
        return Err("This command is restricted to the main application window".into());
    }
    Ok(())
}

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
fn start_ollama(window: tauri::WebviewWindow, state: tauri::State<'_, ManagedProcesses>) -> Result<String, String> {
    require_main_window(&window)?;
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
    // Restrict writes to user home directory to prevent WebView XSS → arbitrary file write
    let home = std::env::var("USERPROFILE")
        .or_else(|_| std::env::var("HOME"))
        .unwrap_or_default();
    if !home.is_empty() {
        let canon_home = std::path::Path::new(&home)
            .canonicalize()
            .unwrap_or_else(|_| std::path::PathBuf::from(&home));
        let p = std::path::Path::new(&path);
        let canon_parent = p
            .parent()
            .and_then(|parent| parent.canonicalize().ok())
            .unwrap_or_else(|| p.to_path_buf());
        if !canon_parent.starts_with(&canon_home) {
            return Err("Files can only be saved within the user home directory.".into());
        }
    }
    std::fs::write(&path, content.as_bytes())
        .map(|_| format!("Saved to {}", path))
        .map_err(|e| format!("Failed to save file: {}", e))
}

#[tauri::command]
fn stop_ollama(window: tauri::WebviewWindow, state: tauri::State<'_, ManagedProcesses>) -> Result<String, String> {
    require_main_window(&window)?;
    if let Some(mut child) = lock_state!(state.ollama).take() {
        wait_or_kill(&mut child, std::time::Duration::from_secs(3));
        Ok("stopped".into())
    } else {
        Ok("not running".into())
    }
}

#[tauri::command]
fn restart_backend(window: tauri::WebviewWindow, app: tauri::AppHandle) -> Result<String, String> {
    require_main_window(&window)?;
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
        .plugin(tauri_plugin_shell::init())
        .manage(ManagedProcesses {
            python: Mutex::new(None),
            ollama: Mutex::new(None),
        })
        .setup(|app| {
            let handle = app.handle().clone();
            if let Err(e) = spawn_python_inner(&handle, Some(&handle)) {
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
                // Only kill backend processes when the main window closes
                if window.label() != "main" {
                    return;
                }
                let state = window.state::<ManagedProcesses>();
                {
                    let mut guard = state.python.lock().unwrap_or_else(|e| e.into_inner());
                    if let Some(mut child) = guard.take() {
                        wait_or_kill(&mut child, std::time::Duration::from_secs(5));
                    }
                }
                {
                    let mut guard = state.ollama.lock().unwrap_or_else(|e| e.into_inner());
                    if let Some(mut child) = guard.take() {
                        wait_or_kill(&mut child, std::time::Duration::from_secs(3));
                    }
                }
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
        // Prevent duplicate monitor threads when restart_backend is called multiple times
        if !HEALTH_MONITOR_RUNNING.swap(true, Ordering::SeqCst) {
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_secs(15));
                let mut interval_secs = 30u64;
                loop {
                    std::thread::sleep(std::time::Duration::from_secs(interval_secs));
                    if !is_port_listening(18088, 1000) {
                        eprintln!("[WARN] Python backend port not responding");
                        let _ = h.emit(
                            "backend-crashed",
                            serde_json::json!({
                                "message": "Python backend may have exited. Please restart it.",
                            }),
                        );
                        // Back off but keep monitoring; backend might be restarting
                        interval_secs = (interval_secs * 2).min(120);
                    } else {
                        interval_secs = 30;
                    }
                }
            });
        }
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
    // Clear proxy env vars for the current process so WebView2's fetch()
    // doesn't route localhost requests through a system-configured proxy.
    // Child processes (Python, Ollama) are already covered by build_command().
    for var in &[
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "ALL_PROXY",
        "all_proxy",
    ] {
        std::env::remove_var(var);
    }
    run()
}
