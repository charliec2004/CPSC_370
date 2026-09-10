use std::{collections::HashMap, path::Path};

pub struct Config {
    pub name: String,
    pub url: String,
    pub token: String,
}

pub fn validate_url(raw: &str) -> Result<(), &'static str> {
    let url = url::Url::parse(raw).map_err(|_| "invalid WebSocket URL")?;
    let local = matches!(url.host_str(), Some("localhost" | "127.0.0.1" | "[::1]"));
    if !(url.scheme() == "wss" || url.scheme() == "ws" && local)
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.fragment().is_some()
    {
        return Err("use wss:// (ws:// is allowed only on loopback), without userinfo or fragment");
    }
    Ok(())
}

fn dotenv(path: &Path) -> Result<HashMap<String, String>, &'static str> {
    let text = match std::fs::read_to_string(path) {
        Ok(s) => s,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(HashMap::new()),
        Err(_) => return Err("could not read configuration file"),
    };
    let mut values = HashMap::new();
    for line in text
        .lines()
        .map(str::trim)
        .filter(|s| !s.is_empty() && !s.starts_with('#'))
    {
        let (key, value) = line
            .strip_prefix("export ")
            .unwrap_or(line)
            .split_once('=')
            .ok_or("invalid configuration file")?;
        let value = value.trim();
        let value = if value.starts_with(['\'', '"']) {
            if value.len() < 2 || !value.ends_with(value.chars().next().unwrap()) {
                return Err("unmatched configuration quote");
            }
            &value[1..value.len() - 1]
        } else {
            value
        };
        values.insert(key.trim().to_owned(), value.to_owned());
    }
    Ok(values)
}

impl Config {
    pub fn parse(args: impl Iterator<Item = String>) -> Result<Self, &'static str> {
        let mut args = args.peekable();
        let (mut name, mut url, mut token) = (None, None, None);
        let mut practice = false;
        let mut env_file = None;
        while let Some(arg) = args.next() {
            match arg.as_str() {
                "--name" => name = Some(args.next().ok_or("--name requires a value")?),
                "--url" => url = Some(args.next().ok_or("--url requires a value")?),
                "--token" => token = Some(args.next().ok_or("--token requires a value")?),
                "--env-file" => env_file = Some(args.next().ok_or("--env-file requires a value")?),
                "--practice" => practice = true,
                _ => return Err("unknown option; use --help"),
            }
        }
        if practice && url.is_some() {
            return Err("choose --practice or --url");
        }
        let default_env = Path::new(env!("CARGO_MANIFEST_DIR")).join("../student/.env");
        let values = dotenv(env_file.as_deref().map(Path::new).unwrap_or(&default_env))?;
        let setting = |key| std::env::var(key).ok().or_else(|| values.get(key).cloned());
        let name = name.ok_or("--name is required")?;
        if !(2..=24).contains(&name.len())
            || !name.as_bytes()[0].is_ascii_alphanumeric()
            || !name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-')
        {
            return Err(
                "name must be 2-24 ASCII letters, digits, underscores or hyphens, starting with a letter or digit",
            );
        }
        let url = if practice {
            "wss://contractnet.blackdial.workers.dev/agent?room=practice".to_owned()
        } else {
            url.or_else(|| setting("INSTRUCTOR_TOURNAMENT_WEBSOCKET_URL"))
                .filter(|s| !s.is_empty())
                .ok_or("set INSTRUCTOR_TOURNAMENT_WEBSOCKET_URL, --url, or --practice")?
        };
        validate_url(&url)?;
        let token = token
            .or_else(|| setting("CLASS_TOKEN"))
            .filter(|s| !s.is_empty())
            .ok_or("set CLASS_TOKEN or --token")?;
        if token.len() > 4096 {
            return Err("token too long");
        }
        Ok(Self { name, url, token })
    }
}
