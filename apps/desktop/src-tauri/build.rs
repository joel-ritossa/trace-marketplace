fn main() {
    // The notifications plugin links Swift (swift-bridge) on macOS; the
    // binary needs an rpath to the system Swift runtime or dyld aborts at
    // launch with "Library not loaded: @rpath/libswift_Concurrency.dylib".
    #[cfg(target_os = "macos")]
    println!("cargo:rustc-link-arg=-Wl,-rpath,/usr/lib/swift");
    tauri_build::build()
}
