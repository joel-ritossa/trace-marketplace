// No custom commands: all behavior lives in the TS frontend; Rust only
// registers the plugins the capabilities file grants.

/// The notifications plugin (notify-rust disabled) drives macOS's
/// UNUserNotificationCenter, which only works from a real .app bundle — its
/// setup fails fatally under `tauri dev`. Skip it there; the frontend treats
/// every notification call as best-effort.
fn notifications_supported() -> bool {
    #[cfg(target_os = "macos")]
    {
        std::env::current_exe()
            .ok()
            .and_then(|exe| {
                let macos_dir = exe.parent()?;
                let bundle = macos_dir.parent()?.parent()?;
                Some(
                    macos_dir.ends_with("MacOS")
                        && bundle.extension().is_some_and(|ext| ext == "app"),
                )
            })
            .unwrap_or(false)
    }
    #[cfg(not(target_os = "macos"))]
    {
        true
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let mut builder = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_store::Builder::default().build())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_http::init());
    if notifications_supported() {
        builder = builder.plugin(tauri_plugin_notifications::init());
    }
    builder
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
