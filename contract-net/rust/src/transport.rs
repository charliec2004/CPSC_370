//! Socket ownership and bounded reconnects; contract state lives in client.rs.
use crate::config::Config;
use futures_util::{SinkExt, StreamExt};
use serde_json::{Value, json};
use std::time::Duration;
use tokio::{
    sync::mpsc,
    time::{Instant, timeout},
};
use tokio_tungstenite::{
    connect_async_with_config,
    tungstenite::{Message, protocol::WebSocketConfig},
};

pub enum Event {
    Message(u64, Value),
    Disconnected,
    Fatal(&'static str),
}
pub struct Outgoing {
    pub generation: u64,
    pub message: Value,
}

pub async fn run(
    config: Config,
    events: mpsc::Sender<Event>,
    mut outgoing: mpsc::Receiver<Outgoing>,
) {
    let mut generation = 0;
    let mut backoff = 1;
    loop {
        let ws_config = WebSocketConfig::default()
            .max_message_size(Some(256 * 1024))
            .max_frame_size(Some(256 * 1024))
            .max_write_buffer_size(512 * 1024);
        let connection = timeout(
            Duration::from_secs(10),
            connect_async_with_config(config.url.as_str(), Some(ws_config), false),
        )
        .await;
        if let Ok(Ok((mut socket, _))) = connection {
            generation += 1;
            let register = json!({"type":"REGISTER", "name":config.name, "token":config.token,
                "machine":format!("{} {} Rust", std::env::consts::OS, std::env::consts::ARCH)});
            if matches!(
                timeout(
                    Duration::from_secs(5),
                    socket.send(Message::Text(register.to_string().into()))
                )
                .await,
                Ok(Ok(()))
            ) {
                let mut heartbeat = tokio::time::interval(Duration::from_secs(20));
                let mut last_seen = Instant::now();
                let registered_by = Instant::now() + Duration::from_secs(10);
                let mut registered = false;
                loop {
                    tokio::select! {
                        incoming = socket.next() => {
                            last_seen = Instant::now();
                            match incoming {
                                Some(Ok(Message::Text(text))) => {
                                    if text == "pong" { continue; }
                                    let Ok(message) = serde_json::from_str::<Value>(&text) else { continue; };
                                    if message["type"] == "REGISTERED" { registered = true; backoff = 1; }
                                    if message["type"] == "ERROR" && matches!(message["code"].as_str(), Some("bad_token" | "bad_name")) {
                                        let _ = events.send(Event::Fatal("registration rejected; check name and token")).await;
                                        return;
                                    }
                                    if events.send(Event::Message(generation, message)).await.is_err() { return; }
                                }
                                Some(Ok(Message::Close(Some(frame)))) if u16::from(frame.code) == 4001 => {
                                    let _ = events.send(Event::Fatal("another process took over this team name")).await;
                                    return;
                                }
                                Some(Ok(Message::Ping(data))) => {
                                    if !matches!(timeout(Duration::from_secs(5), socket.send(Message::Pong(data))).await, Ok(Ok(()))) { break; }
                                }
                                Some(Ok(Message::Pong(_))) => {}
                                _ => break,
                            }
                        }
                        command = outgoing.recv() => {
                            let Some(command) = command else { return; };
                            // Never replay bids or commands from an old socket.
                            if command.generation != generation { continue; }
                            if !matches!(timeout(Duration::from_secs(5), socket.send(Message::Text(command.message.to_string().into()))).await, Ok(Ok(()))) { break; }
                        }
                        _ = heartbeat.tick() => {
                            if last_seen.elapsed() > Duration::from_secs(60) { break; }
                            if !matches!(timeout(Duration::from_secs(5), socket.send(Message::Text("ping".into()))).await, Ok(Ok(()))) { break; }
                        }
                        _ = tokio::time::sleep_until(registered_by), if !registered => break,
                    }
                }
            }
        }
        if events.send(Event::Disconnected).await.is_err() {
            return;
        }
        eprintln!("connection unavailable; reconnecting");
        tokio::time::sleep(Duration::from_secs(backoff)).await;
        backoff = (backoff * 2).min(15);
    }
}
