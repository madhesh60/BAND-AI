// This program prints "Hello, World!" to the console.
// It demonstrates a simple Rust entry point with proper error handling.

use std::process;

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Print the greeting to standard output.
    println!("Hello, World!");
    
    // Optionally, we could check for I/O errors, but println! does not return a Result.
    // If we wanted to handle errors, we could use io::stdout and flush.
    let _ = std::io::stdout().flush();
    
    Ok(())
}
