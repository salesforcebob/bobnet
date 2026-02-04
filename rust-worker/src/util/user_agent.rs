//! User agent rotation utilities.

use rand::prelude::*;

/// Default user agents if none are configured.
const DEFAULT_USER_AGENTS: &[&str] = &[
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36",
];

/// Pick a random user agent from the configured pool or defaults.
pub fn pick_user_agent(pool: Option<&[String]>) -> String {
    let mut rng = thread_rng();
    
    match pool {
        Some(agents) if !agents.is_empty() => {
            agents.choose(&mut rng).unwrap().clone()
        }
        _ => {
            DEFAULT_USER_AGENTS.choose(&mut rng).unwrap().to_string()
        }
    }
}

/// Build standard headers for HTTP requests.
pub fn build_headers(user_agent: &str) -> Vec<(String, String)> {
    vec![
        ("User-Agent".to_string(), user_agent.to_string()),
        ("Accept".to_string(), "*/*".to_string()),
        ("Accept-Language".to_string(), "en-US,en;q=0.9".to_string()),
        ("Connection".to_string(), "keep-alive".to_string()),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pick_user_agent_default() {
        let ua = pick_user_agent(None);
        assert!(!ua.is_empty());
        assert!(ua.contains("Mozilla"));
    }

    #[test]
    fn test_pick_user_agent_custom() {
        let custom = vec!["CustomAgent/1.0".to_string()];
        let ua = pick_user_agent(Some(&custom));
        assert_eq!(ua, "CustomAgent/1.0");
    }

    #[test]
    fn test_pick_user_agent_empty_pool() {
        let empty: Vec<String> = vec![];
        let ua = pick_user_agent(Some(&empty));
        assert!(ua.contains("Mozilla"));
    }

    #[test]
    fn test_build_headers() {
        let headers = build_headers("TestAgent/1.0");
        assert_eq!(headers.len(), 4);
        assert!(headers.iter().any(|(k, v)| k == "User-Agent" && v == "TestAgent/1.0"));
    }
}
