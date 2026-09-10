use crate::tasks::{Work, hash_benchmark};
use serde::{Deserialize, Serialize};
use std::{
    collections::{HashMap, VecDeque},
    time::Instant,
};

#[derive(Clone, Debug, Deserialize)]
#[serde(default)]
pub struct Rules {
    pub award_policy: String,
    pub time_weight: f64,
    pub cost_rate: f64,
    pub penalty_rate: f64,
    pub late_credit: f64,
    pub concurrency: u32,
}
impl Default for Rules {
    fn default() -> Self {
        Self {
            award_policy: "best_value".into(),
            time_weight: 2.,
            cost_rate: 1.,
            penalty_rate: 0.5,
            late_credit: 0.,
            concurrency: 1,
        }
    }
}

#[derive(Clone, Debug, Serialize)]
pub struct Quote {
    pub budget: f64,
    pub task_type: String,
    pub price: f64,
    pub estimate: f64,
    pub compute: f64,
    pub base: f64,
    pub queue: f64,
    pub overhead: f64,
    pub safe_finish: f64,
    pub baseline_price: f64,
    pub model_success_probability: f64,
    pub price_share: f64,
}

#[derive(Clone, Debug, Default)]
pub struct Model {
    pub hash: f64,
    pub monte: f64,
    pub sort: f64,
    pub matrix32: f64,
    pub matrix64: f64,
    pub prime_setup: f64,
    pub prime_marking: f64,
}

fn measure(mut f: impl FnMut()) -> f64 {
    let mut times = [0.; 3];
    for t in &mut times {
        let start = Instant::now();
        f();
        *t = start.elapsed().as_secs_f64();
    }
    times.sort_by(f64::total_cmp);
    times[1]
}
fn timed(w: &Work) -> f64 {
    measure(|| {
        std::hint::black_box(w.execute(None).expect("valid calibration task"));
    })
}

impl Model {
    pub fn calibrate() -> Self {
        let mut m = Self::default();
        for s in ["370".to_owned(), "é".repeat(128)] {
            m.hash = m
                .hash
                .max(measure(|| hash_benchmark(&s, 150_000)) / 150_000.);
        }
        for n in [96, 192] {
            for modulus in [1000003, 1 << 20, (1u64 << 63) - 1, 1 << 63] {
                let c = timed(&Work::Matrix {
                    seed: 370,
                    n,
                    modulus,
                }) / (n * n) as f64;
                if modulus <= u32::MAX as u64 {
                    m.matrix32 = m.matrix32.max(c);
                } else {
                    m.matrix64 = m.matrix64.max(c);
                }
            }
        }
        for hi in [2_000_000u64, 100_000_000, 1_000_000_000_000] {
            m.prime_setup = m
                .prime_setup
                .max(timed(&Work::Prime { lo: hi - 1, hi }) / (2 * (hi - 1).isqrt()) as f64);
        }
        for (lo, width) in [
            (2_000_000, 262144),
            (10_000_000, 786432),
            (1_000_000_000, 262144),
        ] {
            m.prime_marking = m
                .prime_marking
                .max(timed(&Work::Prime { lo, hi: lo + width }) / width as f64);
        }
        for n in [100_000, 400_000, 1_200_000] {
            m.sort = m
                .sort
                .max(timed(&Work::Sort { seed: 370, n }) / (n as f64 * (n as f64).log2()));
        }
        for samples in [100_000, 500_000] {
            m.monte = m
                .monte
                .max(timed(&Work::Monte { seed: 370, samples }) / samples as f64);
        }
        m
    }

    pub fn estimate(&self, w: &Work) -> f64 {
        0.0005
            + match w {
                Work::Hash { threshold, .. } => (1u64 << 32) as f64 / *threshold as f64 * self.hash,
                Work::Monte { samples, .. } => *samples as f64 * self.monte,
                Work::Sort { n, .. } => *n as f64 * ((*n).max(2) as f64).log2() * self.sort,
                Work::Matrix { n, modulus, .. } => {
                    (n * n) as f64
                        * if *modulus <= u32::MAX as u64 {
                            self.matrix32
                        } else {
                            self.matrix64
                        }
                }
                Work::Prime { lo, hi } => {
                    if hi <= lo {
                        0.
                    } else {
                        let width = hi - lo;
                        self.prime_setup
                            * (hi - 1).isqrt() as f64
                            * (1 + width.div_ceil(262144)) as f64
                            + self.prime_marking * width as f64
                    }
                }
            }
    }
}

pub struct Strategy {
    pub model: Model,
    pub rules: Rules,
    pub network: f64,
    pub biases: HashMap<String, f64>,
    pub shares: HashMap<String, f64>,
    wins: HashMap<String, u32>,
    overheads: VecDeque<f64>,
}

pub fn hash_probability(threshold: u64, mean: f64, available: f64) -> f64 {
    if available <= 0. || mean <= 0. {
        return 0.;
    }
    let p = threshold as f64 / (1u64 << 32) as f64;
    let attempts = (available / (mean * p)).floor();
    if attempts < 1. {
        0.
    } else if p == 1. {
        1.
    } else {
        -(attempts * (-p).ln_1p()).exp_m1()
    }
}
fn round4(x: f64) -> f64 {
    (x * 10000.).round_ties_even() / 10000.
}
fn ceil4(x: f64) -> f64 {
    (x * 10000.).ceil() / 10000.
}

impl Strategy {
    pub fn new(model: Model) -> Self {
        Self {
            model,
            network: 0.12,
            rules: Rules::default(),
            biases: HashMap::new(),
            shares: HashMap::new(),
            wins: HashMap::new(),
            overheads: VecDeque::new(),
        }
    }
    pub fn compute(&self, work: &Work) -> f64 {
        self.model.estimate(work) * self.biases.get(work.kind()).copied().unwrap_or(1.)
    }
    fn initial_share(&self) -> f64 {
        0.01
    }
    pub fn quoted_overhead(&self) -> f64 {
        if self.overheads.len() < 5 {
            self.network
        } else {
            self.network.min(
                (self.overheads.iter().sum::<f64>() / self.overheads.len() as f64 + 0.02).max(0.05),
            )
        }
    }
    pub fn quote(&self, work: &Work, budget: f64, deadline: f64, queue: f64) -> Option<Quote> {
        if !budget.is_finite()
            || budget <= 0.
            || !deadline.is_finite()
            || deadline <= 0.
            || !queue.is_finite()
            || queue < 0.
            || !self.rules.cost_rate.is_finite()
            || self.rules.cost_rate < 0.
        {
            return None;
        }
        let base = self.model.estimate(work);
        let compute = self.compute(work);
        let safe = ceil4(queue + compute + self.network);
        if !safe.is_finite() || safe > deadline {
            return None;
        }
        let estimate = ceil4(queue + compute + self.quoted_overhead());
        let mut success = 1.;
        let mut cost = safe * self.rules.cost_rate;
        {
            if let Work::Hash { threshold, .. } = work {
                if !self.rules.penalty_rate.is_finite()
                    || self.rules.penalty_rate < 0.
                    || !(0. ..=1.).contains(&self.rules.late_credit)
                {
                    return None;
                }
                success = hash_probability(*threshold, compute, deadline - queue - self.network);
                if success < 0.95 {
                    return None;
                }
                cost = (cost + (1. - success) * self.rules.penalty_rate * budget) / success;
            }
        }
        // Prices must cover modelled cost even after a string of auction losses.
        let baseline = ceil4(cost * 1.28).max(0.01);
        let ceiling = (budget * 10000.).floor() / 10000.;
        if !baseline.is_finite() || ceiling < baseline {
            return None;
        }
        let share = self
            .shares
            .get(work.kind())
            .copied()
            .unwrap_or(self.initial_share());
        let price = round4(ceiling * share).max(baseline).min(ceiling);
        Some(Quote {
            budget,
            task_type: work.kind().into(),
            price,
            estimate,
            compute,
            base,
            queue,
            overhead: self.network,
            safe_finish: safe,
            baseline_price: baseline,
            model_success_probability: success,
            price_share: share,
        })
    }
    pub fn rejected(&mut self, kind: &str) {
        let old = self
            .shares
            .get(kind)
            .copied()
            .unwrap_or(self.initial_share());
        let next = (old * 0.75).max(0.001);
        self.shares.insert(kind.into(), next);
        self.wins.insert(kind.into(), 0);
    }
    pub fn settled(
        &mut self,
        q: &Quote,
        verdict: &str,
        duration: Option<f64>,
        runtime: Option<f64>,
    ) {
        let kind = q.task_type.as_str();
        let wins = self.wins.entry(kind.into()).or_default();
        *wins = if verdict == "correct" { *wins + 1 } else { 0 };
        if *wins >= 2 {
            *wins = 0;
            let old = self
                .shares
                .get(kind)
                .copied()
                .unwrap_or(self.initial_share());
            self.shares.insert(
                kind.into(),
                (old.max(q.price / q.budget) * 1.15 + 0.005).min(0.95),
            );
        }
        if verdict != "correct" {
            return;
        }
        if let Some(runtime) = runtime.filter(|r| r.is_finite() && *r >= 0.) {
            let measured_cost = runtime * self.rules.cost_rate;
            if measured_cost > q.price {
                let old = self
                    .shares
                    .get(kind)
                    .copied()
                    .unwrap_or(self.initial_share());
                self.shares.insert(
                    kind.into(),
                    old.max(measured_cost * 1.2 / q.budget).min(0.95),
                );
            }
        }
        if let Some(duration) = duration.filter(|d| d.is_finite() && *d >= 0.) {
            if kind != "hash_search" && q.base > 0. {
                let old = self.biases.get(kind).copied().unwrap_or(1.);
                self.biases.insert(
                    kind.into(),
                    old * 0.8 + (duration / q.base).clamp(0.5, 4.) * 0.2,
                );
            }
            if let Some(runtime) = runtime.filter(|r| r.is_finite() && *r >= duration)
                && q.queue == 0.
            {
                if self.overheads.len() == 20 {
                    self.overheads.pop_front();
                }
                self.overheads.push_back(runtime - duration);
                if self.overheads.len() >= 3 {
                    let mut sorted: Vec<f64> = self.overheads.iter().copied().collect();
                    sorted.sort_by(f64::total_cmp);
                    let p90 = sorted[(0.9 * sorted.len() as f64).ceil() as usize - 1];
                    self.network = 0.05f64
                        .max(p90 + 0.02)
                        .max(sorted.iter().sum::<f64>() / sorted.len() as f64 + 0.02);
                }
            }
        }
    }
}
