use std::sync::Mutex;
use std::fs::{OpenOptions, create_dir_all};
use std::io::Write;
use std::path::PathBuf;
use chrono::Local;
use lazy_static::lazy_static;

lazy_static! {
    static ref LOG_FILE: Mutex<Option<PathBuf>> = Mutex::new(None);
    static ref API_TOKEN: Mutex<Option<String>> = Mutex::new(None);
}

/// Initialize the global file logger and hooks a critical panic handler.
/// Also reads the API token from storage if available to configure the redactor.
pub fn init_logger(log_dir: PathBuf, token_file_path: Option<PathBuf>) {
    let _ = create_dir_all(&log_dir);
    
    // Set active log file path
    if let Ok(mut file_guard) = LOG_FILE.lock() {
        *file_guard = Some(log_dir.join("app.log"));
    }
    
    // Read and save token for dynamic redactions
    if let Some(token_path) = token_file_path {
        if token_path.exists() {
            if let Ok(content) = std::fs::read_to_string(&token_path) {
                if let Ok(mut token_guard) = API_TOKEN.lock() {
                    *token_guard = Some(content.trim().to_string());
                }
            }
        }
    }

    // Configure persistent panic hook logging
    let log_dir_clone = log_dir.clone();
    std::panic::set_hook(Box::new(move |info| {
        let location = info.location()
            .map(|l| format!("{}:{}", l.file(), l.line()))
            .unwrap_or_else(|| "unknown".to_string());
            
        let payload = info.payload()
            .downcast_ref::<&str>()
            .map(|s| *s)
            .or_else(|| info.payload().downcast_ref::<String>().map(|s| s.as_str()))
            .unwrap_or("Box<Any>");

        let log_msg = format!(
            "[{}] [CRITICAL] [PanicHook] Rust panic at location '{}': {}\n",
            Local::now().format("%Y-%m-%dT%H:%M:%S%.3f"),
            location,
            payload
        );
        
        eprintln!("{}", log_msg);
        let log_file_path = log_dir_clone.join("app.log");
        if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(&log_file_path) {
            let _ = file.write_all(log_msg.as_bytes());
        }
    }));
}

/// Thread-safe logger outputting styled lines to stdout and appending to the app.log file.
/// Automatically redacts the loaded API security token.
pub fn log(level: &str, module: &str, message: &str) {
    let timestamp = Local::now().format("%Y-%m-%dT%H:%M:%S%.3f").to_string();
    
    // Redact active API token if it's found in the message
    let mut clean_message = message.to_string();
    if let Ok(token_guard) = API_TOKEN.lock() {
        if let Some(ref token) = *token_guard {
            if !token.is_empty() && clean_message.contains(token) {
                clean_message = clean_message.replace(token, "********");
            }
        }
    }

    let formatted = format!(
        "[{}] [{}] ({}) {}\n",
        timestamp,
        level.to_uppercase(),
        module,
        clean_message
    );

    // Stdout console output
    print!("{}", formatted);

    // Persistent file appending
    if let Ok(file_guard) = LOG_FILE.lock() {
        if let Some(ref path) = *file_guard {
            if let Ok(mut file) = OpenOptions::new().create(true).append(true).open(path) {
                let _ = file.write_all(formatted.as_bytes());
            }
        }
    }
}
