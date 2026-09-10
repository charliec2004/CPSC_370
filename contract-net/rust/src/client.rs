//! One owner for bids, reservations, awards and retained deliveries.
use crate::{
    config::Config,
    strategy::{Model, Quote, Rules, Strategy},
    tasks::Work,
    transport::{self, Event, Outgoing},
};
use serde::Deserialize;
use serde_json::{Value, json};
use std::{
    collections::{HashMap, VecDeque},
    time::{Duration, Instant},
};
use tokio::sync::mpsc;

#[derive(Deserialize)]
struct Cfp {
    task_id: u64,
    task_type: String,
    params: Value,
    budget: f64,
    deadline_s: f64,
    bid_window_ms: u64,
    #[serde(default = "first_attempt")]
    attempt: u64,
}
fn first_attempt() -> u64 {
    1
}

enum Phase {
    Bid,
    Queued {
        cutoff: Instant,
    },
    Running,
    Delivered {
        message: Value,
        sent_generation: Option<u64>,
        duration: f64,
    },
}
struct Commitment {
    work: Work,
    quote: Quote,
    attempt: u64,
    deadline: f64,
    expires: Instant,
    phase: Phase,
}
struct Completion {
    id: u64,
    attempt: u64,
    result: Result<u64, &'static str>,
    duration: f64,
}
struct Running {
    id: u64,
    attempt: u64,
    started: Instant,
    compute: f64,
}

struct State {
    strategy: Strategy,
    commitments: HashMap<u64, Commitment>,
    queue: VecDeque<u64>,
    retired: VecDeque<(u64, u64)>,
    running: Option<Running>,
    generation: Option<u64>,
    server_clock: Option<(f64, Instant)>,
    stopping: bool,
}

impl State {
    fn new(model: Model) -> Self {
        Self {
            strategy: Strategy::new(model),
            commitments: HashMap::new(),
            queue: VecDeque::new(),
            retired: VecDeque::new(),
            running: None,
            generation: None,
            server_clock: None,
            stopping: false,
        }
    }
    fn retire(&mut self, id: u64) -> Option<Commitment> {
        let commitment = self.commitments.remove(&id)?;
        if self.retired.len() == 2048 {
            self.retired.pop_front();
        }
        self.retired.push_back((id, commitment.attempt));
        self.queue.retain(|queued| *queued != id);
        Some(commitment)
    }
    fn queue_seconds(&self) -> f64 {
        let mut total = self.running.as_ref().map_or(0., |r| {
            // Never pretend a still-running job has disappeared after its estimate.
            (r.compute - r.started.elapsed().as_secs_f64()).max(0.001)
        });
        for c in self.commitments.values() {
            if matches!(c.phase, Phase::Bid | Phase::Queued { .. }) {
                total += c.quote.compute + c.quote.overhead;
            }
        }
        total
    }
    fn cfp(&mut self, value: Value) -> Option<Value> {
        let id = value["task_id"].as_u64()?;
        let refuse = || Some(json!({"type":"REFUSE", "task_id":id}));
        let Ok(cfp) = serde_json::from_value::<Cfp>(value) else {
            return refuse();
        };
        if self.commitments.contains_key(&id) || self.retired.contains(&(id, cfp.attempt)) {
            return None;
        }
        if self.stopping
            || self.commitments.len() >= 256
            || cfp.attempt == 0
            || !(0. ..=300.).contains(&cfp.deadline_s)
            || cfp.deadline_s == 0.
            || !(1..=60_000).contains(&cfp.bid_window_ms)
        {
            return refuse();
        }
        let Ok(work) = Work::parse(&cfp.task_type, &cfp.params) else {
            return refuse();
        };
        let Some(quote) =
            self.strategy
                .quote(&work, cfp.budget, cfp.deadline_s, self.queue_seconds())
        else {
            return refuse();
        };
        let message = json!({"type":"PROPOSE", "task_id":cfp.task_id, "price":quote.price, "est_seconds":quote.estimate});
        eprintln!(
            "BID {}",
            json!({"task_id":id,"task_type":work.kind(),"price":quote.price,"estimate":quote.estimate,"queue":quote.queue,"compute":quote.compute})
        );
        self.commitments.insert(
            id,
            Commitment {
                work,
                quote,
                attempt: cfp.attempt,
                deadline: cfp.deadline_s,
                expires: Instant::now() + Duration::from_millis(cfp.bid_window_ms + 5000),
                phase: Phase::Bid,
            },
        );
        Some(message)
    }
    fn accept(&mut self, value: &Value) {
        let Some(id) = value["task_id"].as_u64() else {
            return;
        };
        let Some(c) = self.commitments.get_mut(&id) else {
            return;
        };
        if !matches!(c.phase, Phase::Bid) {
            return;
        }
        let Some(deadline) = value["deadline_s"]
            .as_f64()
            .filter(|d| d.is_finite() && *d > 0. && *d <= 300.)
        else {
            return;
        };
        let Some(due) = value["due_at"].as_f64().filter(|d| d.is_finite()) else {
            return;
        };
        let Some((server_now, measured_at)) = self.server_clock else {
            return;
        };
        let remaining = (due / 1000. - server_now - measured_at.elapsed().as_secs_f64())
            .min(deadline)
            .min(c.deadline)
            .max(0.);
        let now = Instant::now();
        let cutoff = now + Duration::from_secs_f64((remaining - self.strategy.network).max(0.));
        c.expires = now + Duration::from_secs_f64(remaining + 30.);
        c.phase = Phase::Queued { cutoff };
        self.queue.push_back(id);
    }
    fn complete(&mut self, completed: Completion) {
        if self
            .running
            .as_ref()
            .is_some_and(|r| r.id == completed.id && r.attempt == completed.attempt)
        {
            self.running = None;
        }
        let Some(c) = self
            .commitments
            .get_mut(&completed.id)
            .filter(|c| c.attempt == completed.attempt && matches!(c.phase, Phase::Running))
        else {
            return;
        };
        let message = match completed.result {
            Ok(result) => {
                json!({"type":"INFORM", "task_id":completed.id, "result":result.to_string(), "runtime":completed.duration})
            }
            Err(_) => {
                json!({"type":"FAILURE", "task_id":completed.id, "reason":"execution could not complete within its limits"})
            }
        };
        c.phase = Phase::Delivered {
            message,
            sent_generation: None,
            duration: completed.duration,
        };
    }
    fn start_next(&mut self, sender: &mpsc::Sender<Completion>) {
        if self.running.is_some() {
            return;
        }
        while let Some(id) = self.queue.pop_front() {
            let Some(c) = self.commitments.get_mut(&id) else {
                continue;
            };
            let Phase::Queued { cutoff } = c.phase else {
                continue;
            };
            let work = c.work.clone();
            let attempt = c.attempt;
            c.phase = Phase::Running;
            self.running = Some(Running {
                id,
                attempt,
                started: Instant::now(),
                compute: c.quote.compute,
            });
            let sender = sender.clone();
            tokio::spawn(async move {
                let started = Instant::now();
                let result = tokio::task::spawn_blocking(move || work.execute(Some(cutoff)))
                    .await
                    .unwrap_or(Err("worker failed"));
                let _ = sender
                    .send(Completion {
                        id,
                        attempt,
                        result,
                        duration: started.elapsed().as_secs_f64(),
                    })
                    .await;
            });
            break;
        }
    }
    fn expire(&mut self) {
        let now = Instant::now();
        let expired: Vec<_> = self
            .commitments
            .iter()
            .filter(|(_, c)| now >= c.expires)
            .map(|(&id, _)| id)
            .collect();
        for id in expired {
            if let Some(c) = self.retire(id)
                && !matches!(c.phase, Phase::Bid)
            {
                eprintln!("contract #{id} expired without confirmed settlement");
            }
        }
    }
    fn dispatch(&mut self, generation: u64, message: Value) -> Result<Vec<Value>, &'static str> {
        let mut outgoing = Vec::new();
        match message["type"].as_str() {
            Some("REGISTERED") => {
                let rules: Rules = serde_json::from_value(message["rules"].clone())
                    .map_err(|_| "invalid manager rules")?;
                if !rules.cost_rate.is_finite()
                    || rules.cost_rate < 0.
                    || !rules.penalty_rate.is_finite()
                    || rules.penalty_rate < 0.
                    || !(0. ..=1.).contains(&rules.late_credit)
                    || !rules.time_weight.is_finite()
                    || rules.time_weight < 0.
                    || rules.concurrency == 0
                    || !matches!(rules.award_policy.as_str(), "best_value" | "lowest_price")
                {
                    return Err("unsupported manager rules");
                }
                let now = message["now"]
                    .as_f64()
                    .filter(|n| n.is_finite() && *n > 0.)
                    .ok_or("invalid manager clock")?;
                self.server_clock = Some((now / 1000., Instant::now()));
                self.strategy.rules = rules;
                self.generation = Some(generation);
                eprintln!(
                    "registered; concurrency {}",
                    self.strategy.rules.concurrency
                );
                if let Some(cfps) = message["open_cfps"].as_array() {
                    for cfp in cfps.iter().take(256) {
                        if let Some(bid) = self.cfp(cfp.clone()) {
                            outgoing.push(bid);
                        }
                    }
                }
            }
            _ if self.generation != Some(generation) => {}
            Some("CFP") => {
                if let Some(bid) = self.cfp(message) {
                    outgoing.push(bid);
                }
            }
            Some("ACCEPT_PROPOSAL") => self.accept(&message),
            Some("REJECT_PROPOSAL" | "BID_INVALID") => {
                if let Some(id) = message["task_id"].as_u64()
                    && self
                        .commitments
                        .get(&id)
                        .is_some_and(|c| matches!(c.phase, Phase::Bid))
                    && let Some(c) = self.retire(id)
                    && message["type"] == "REJECT_PROPOSAL"
                {
                    self.strategy.rejected(c.work.kind());
                }
            }
            Some("SETTLED") => {
                let verdict = message["verdict"].as_str().unwrap_or("");
                if !matches!(
                    verdict,
                    "correct" | "late" | "wrong_answer" | "timeout" | "failure"
                ) {
                    return Ok(outgoing);
                }
                if let Some(id) = message["task_id"].as_u64()
                    && self
                        .commitments
                        .get(&id)
                        .is_some_and(|c| !matches!(c.phase, Phase::Bid))
                    && let Some(c) = self.retire(id)
                {
                    let duration = match c.phase {
                        Phase::Delivered { duration, .. } => Some(duration),
                        _ => None,
                    };
                    self.strategy
                        .settled(&c.quote, verdict, duration, message["runtime"].as_f64());
                    eprintln!(
                        "SETTLED {}",
                        json!({"task_id":id,"verdict":verdict,"profit":message["profit"].as_f64(),"runtime":message["runtime"].as_f64()})
                    );
                }
            }
            Some("ERROR") => eprintln!("manager reported a protocol error"),
            _ => {}
        }
        Ok(outgoing)
    }
    fn deliveries(&mut self) -> Vec<Value> {
        let Some(generation) = self.generation else {
            return Vec::new();
        };
        let mut messages = Vec::new();
        for c in self.commitments.values_mut() {
            if let Phase::Delivered {
                message,
                sent_generation,
                ..
            } = &mut c.phase
                && *sent_generation != Some(generation)
            {
                messages.push(message.clone());
                *sent_generation = Some(generation);
            }
        }
        messages
    }
}

pub async fn run(config: Config) -> Result<(), &'static str> {
    eprintln!("calibrating Rust executors…");
    let model = tokio::task::spawn_blocking(Model::calibrate)
        .await
        .map_err(|_| "calibration failed")?;
    eprintln!("calibration complete");
    let mut state = State::new(model);
    let (events_tx, mut events) = mpsc::channel(256);
    let (outgoing, commands) = mpsc::channel(512);
    let (completion_tx, mut completions) = mpsc::channel(1);
    let network = tokio::spawn(transport::run(config, events_tx, commands));
    let mut tick = tokio::time::interval(Duration::from_millis(50));
    let result = loop {
        let mut messages = Vec::new();
        tokio::select! {
            event = events.recv() => match event {
                Some(Event::Message(generation, message)) => match state.dispatch(generation, message) {
                    Ok(out) => messages = out,
                    Err(error) => break Err(error),
                },
                Some(Event::Disconnected) => state.generation = None,
                Some(Event::Fatal(error)) => break Err(error),
                None => break Err("network task stopped"),
            },
            Some(completed) = completions.recv() => state.complete(completed),
            _ = tick.tick() => state.expire(),
            signal = tokio::signal::ctrl_c(), if !state.stopping => {
                if signal.is_err() { break Err("could not install shutdown handler"); }
                state.stopping = true;
                eprintln!("draining pending bids and awarded contracts; refusing new work");
            }
        }
        state.start_next(&completion_tx);
        messages.extend(state.deliveries());
        if let Some(generation) = state.generation {
            for message in messages {
                if !matches!(
                    tokio::time::timeout(
                        Duration::from_secs(5),
                        outgoing.send(Outgoing {
                            generation,
                            message
                        })
                    )
                    .await,
                    Ok(Ok(()))
                ) {
                    network.abort();
                    return Err("network command queue unavailable");
                }
            }
        }
        if state.stopping && state.commitments.is_empty() && state.running.is_none() {
            break Ok(());
        }
    };
    network.abort();
    result
}
