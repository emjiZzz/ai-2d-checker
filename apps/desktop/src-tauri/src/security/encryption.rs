use aes_gcm::{
    aead::{Aead, KeyInit},
    Aes256Gcm, Nonce
};
use base64::{Engine as _, engine::general_purpose::STANDARD as BASE64};
use rand::{RngCore, thread_rng};
use std::env;
use sha2::{Sha256, Digest};

/// Derive a stable, machine-bound 32-byte key from hardware attributes.
/// This matches the Python side implementation exactly to ensure cross-platform compatibility.
pub fn get_device_key() -> [u8; 32] {
    let computer = env::var("COMPUTERNAME")
        .or_else(|_| env::var("HOSTNAME"))
        .unwrap_or_default();
    
    let user = env::var("USERNAME")
        .or_else(|_| env::var("USER"))
        .unwrap_or_default();
    
    let os = env::consts::OS.to_string();

    let signature = format!(
        "ai-2d-checker-device-salt-{}-{}-{}",
        computer.trim(),
        user.trim(),
        os.trim()
    );

    let mut hasher = Sha256::new();
    hasher.update(signature.as_bytes());
    let result = hasher.finalize();
    let mut key = [0u8; 32];
    key.copy_from_slice(&result);
    key
}

/// Encrypts a plaintext UTF-8 string.
/// Returns a base64 encoded string format: base64(nonce[12B] + ciphertext).
pub fn encrypt(plaintext: &str) -> Result<String, String> {
    if plaintext.is_empty() {
        return Ok(String::new());
    }
    
    let key = get_device_key();
    let cipher = Aes256Gcm::new_from_slice(&key)
        .map_err(|e| format!("Failed to initialize AES cipher: {}", e))?;

    // 12-byte cryptographically secure random nonce
    let mut nonce_bytes = [0u8; 12];
    thread_rng().fill_bytes(&mut nonce_bytes);
    let nonce = Nonce::from_slice(&nonce_bytes);

    // Encrypt the plaintext bytes
    let ciphertext = cipher
        .encrypt(nonce, plaintext.as_bytes())
        .map_err(|e| format!("AES GCM encryption failed: {}", e))?;

    // Combine nonce and ciphertext
    let mut combined = Vec::new();
    combined.extend_from_slice(&nonce_bytes);
    combined.extend_from_slice(&ciphertext);

    Ok(BASE64.encode(combined))
}

/// Decrypts a base64 encoded payload of format: base64(nonce[12B] + ciphertext).
/// Returns the original decrypted plaintext UTF-8 string.
pub fn decrypt(encrypted_base64: &str) -> Result<String, String> {
    if encrypted_base64.is_empty() {
        return Ok(String::new());
    }
    
    let key = get_device_key();
    let cipher = Aes256Gcm::new_from_slice(&key)
        .map_err(|e| format!("Failed to initialize AES cipher: {}", e))?;

    // Decode base64 payload
    let combined = BASE64
        .decode(encrypted_base64)
        .map_err(|e| format!("Failed to decode base64 ciphertext: {}", e))?;

    if combined.len() < 12 {
        return Err("Ciphertext payload is too short, missing valid GCM nonce.".to_string());
    }

    let (nonce_bytes, ciphertext) = combined.split_at(12);
    let nonce = Nonce::from_slice(nonce_bytes);

    // Decrypt the ciphertext
    let decrypted_bytes = cipher
        .decrypt(nonce, ciphertext)
        .map_err(|e| format!("AES GCM decryption failed: {}", e))?;

    String::from_utf8(decrypted_bytes)
        .map_err(|e| format!("Decrypted data contains invalid UTF-8 sequence: {}", e))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encryption_roundtrip() {
        let secret = "SuperSecretAPIKey123_TauriRust";
        let encrypted = encrypt(secret).expect("Encryption failed");
        assert!(!encrypted.is_empty());
        
        let decrypted = decrypt(&encrypted).expect("Decryption failed");
        assert_eq!(secret, decrypted);
    }
}
