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
    if std::env::args().len() != 1 {
        eprintln!("Usage: auctioneers < requests.jsonl (offline execution only)");
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
