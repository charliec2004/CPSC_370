//! Offline executor: one bounded JSON request per line, one JSON response per line.
use auctioneers::tasks::Work;
use serde::Deserialize;
use serde_json::json;
use std::io::{self, BufRead, Write};
use std::time::{Duration, Instant};

const MAX_REQUEST_BYTES: u64 = 16 * 1024;

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Request {
    task_type: String,
    params: serde_json::Value,
    timeout_ms: Option<u64>,
}

fn execute(line: &[u8]) -> serde_json::Value {
    let result = (|| {
        let request: Request = serde_json::from_slice(line).map_err(|_| "invalid request")?;
        let timeout = request.timeout_ms.unwrap_or(30_000);
        if !(1..=60_000).contains(&timeout) {
            return Err("timeout_ms must be between 1 and 60000");
        }
        let work = Work::parse(&request.task_type, &request.params)?;
        let result = work.execute(Some(Instant::now() + Duration::from_millis(timeout)))?;
        // The protocol carries exact integers as strings.
        Ok(result.to_string())
    })();
    match result {
        Ok(result) => json!({"result": result}),
        Err(error) => json!({"error": error}),
    }
}

fn main() -> io::Result<()> {
    let args: Vec<_> = std::env::args().skip(1).collect();
    if args.first().is_some_and(|s| s == "--help" || s == "-h") {
        println!(
            "Offline: auctioneers < requests.jsonl\nNetwork: auctioneers run --name Auctioneers [--practice | --url URL] [--env-file PATH]\nReads CLASS_TOKEN and INSTRUCTOR_TOURNAMENT_WEBSOCKET_URL from environment or student/.env.\nCtrl+C drains pending work before disconnecting."
        );
        return Ok(());
    }
    if args.first().is_some_and(|s| s == "run") {
        if rustls::crypto::ring::default_provider().install_default().is_err() {
            eprintln!("could not initialize TLS provider");
            std::process::exit(1);
        }
        let config = match auctioneers::config::Config::parse(args.into_iter().skip(1)) {
            Ok(config) => config,
            Err(error) => {
                eprintln!("{error}");
                std::process::exit(2);
            }
        };
        let runtime = tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()?;
        let result = runtime.block_on(auctioneers::client::run(config));
        runtime.shutdown_timeout(Duration::from_secs(1));
        if let Err(error) = result {
            eprintln!("{error}");
            std::process::exit(1);
        }
        return Ok(());
    }
    if !args.is_empty() {
        eprintln!("unknown command; use --help");
        std::process::exit(2);
    }
    let mut input = io::stdin().lock();
    let mut output = io::stdout().lock();
    loop {
        let mut line = Vec::new();
        let count =
            std::io::Read::take(&mut input, MAX_REQUEST_BYTES + 1).read_until(b'\n', &mut line)?;
        if count == 0 {
            break;
        }
        if count as u64 > MAX_REQUEST_BYTES {
            writeln!(output, "{}", json!({"error": "request too large"}))?;
            output.flush()?;
            // Stop rather than interpreting a partial request as another task.
            std::process::exit(2);
        }
        writeln!(output, "{}", execute(&line))?;
        output.flush()?;
    }
    Ok(())
}
