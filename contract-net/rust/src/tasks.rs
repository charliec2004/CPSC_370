use crate::random::PythonRandom;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::time::Instant;

#[derive(Clone, Debug)]
pub enum Work {
    Monte { seed: u64, samples: usize },
    Prime { lo: u64, hi: u64 },
    Hash { seed: String, threshold: u64 },
    Sort { seed: u64, n: usize },
    Matrix { seed: u64, n: usize, modulus: u64 },
}

fn integer(v: &Value) -> Result<i128, &'static str> {
    if !v.is_number() {
        return Err("integer required");
    }
    v.to_string()
        .parse()
        .map_err(|_| "integer outside supported range")
}
fn bounded(v: &Value, max: u64) -> Result<u64, &'static str> {
    let n = integer(v)?;
    if n < 0 || n > max as i128 {
        return Err("parameter outside supported range");
    }
    Ok(n as u64)
}
fn seed(v: &Value) -> Result<u64, &'static str> {
    let n = integer(v)?.unsigned_abs();
    u64::try_from(n).map_err(|_| "seed exceeds 64 bits")
}

impl Work {
    pub fn parse(kind: &str, p: &Value) -> Result<Self, &'static str> {
        Ok(match kind {
            "monte_carlo_pi" => Self::Monte {
                seed: seed(&p["seed"])?,
                samples: bounded(&p["samples"], 50_000_000)? as usize,
            },
            "sort_checksum" => Self::Sort {
                seed: seed(&p["seed"])?,
                n: bounded(&p["n"], 5_000_000)? as usize,
            },
            "matmul_mod" => {
                let modulus = bounded(&p["mod"], u64::MAX)?;
                if modulus == 0 {
                    return Err("zero modulus");
                }
                Self::Matrix {
                    seed: seed(&p["seed"])?,
                    n: bounded(&p["n"], 2048)? as usize,
                    modulus,
                }
            }
            "prime_count" => {
                let lo = integer(&p["lo"])?.max(2);
                let hi = integer(&p["hi"])?;
                if hi > 1_000_000_000_000 || hi.saturating_sub(lo) > 10_000_000 {
                    return Err("prime range too large");
                }
                if hi <= lo {
                    Self::Prime { lo: 2, hi: 2 }
                } else {
                    Self::Prime {
                        lo: lo as u64,
                        hi: hi as u64,
                    }
                }
            }
            "hash_search" => {
                let seed = if let Some(s) = p["seed"].as_str() {
                    s.to_owned()
                } else if p["seed"].is_number() {
                    let s = p["seed"].to_string();
                    if !s
                        .strip_prefix('-')
                        .unwrap_or(&s)
                        .bytes()
                        .all(|b| b.is_ascii_digit())
                    {
                        return Err("hash seed must be an integer or string");
                    }
                    s
                } else {
                    return Err("hash seed must be an integer or string");
                };
                let threshold = bounded(&p["threshold"], 1u64 << 32)?;
                if seed.chars().count() > 128 || threshold == 0 {
                    return Err("unsupported hash parameters");
                }
                Self::Hash { seed, threshold }
            }
            _ => return Err("unsupported task"),
        })
    }

    pub fn kind(&self) -> &'static str {
        match self {
            Self::Monte { .. } => "monte_carlo_pi",
            Self::Prime { .. } => "prime_count",
            Self::Hash { .. } => "hash_search",
            Self::Sort { .. } => "sort_checksum",
            Self::Matrix { .. } => "matmul_mod",
        }
    }

    pub fn execute(&self, cutoff: Option<Instant>) -> Result<u64, &'static str> {
        let check = || {
            if cutoff.is_some_and(|t| Instant::now() >= t) {
                Err("execution deadline exceeded")
            } else {
                Ok(())
            }
        };
        check()?;
        match self {
            Self::Monte { seed, samples } => {
                let mut rng = PythonRandom::new(*seed);
                let mut inside = 0;
                for i in 0..*samples {
                    if i % 65536 == 0 {
                        check()?;
                    }
                    let x = rng.random();
                    let y = rng.random();
                    // Ordinary Rust arithmetic is not fused; do not use mul_add.
                    if x * x + y * y <= 1.0 {
                        inside += 1;
                    }
                }
                Ok(inside)
            }
            Self::Sort { seed, n } => {
                let mut rng = PythonRandom::new(*seed);
                let mut values = Vec::with_capacity(*n);
                for i in 0..*n {
                    if i % 65536 == 0 {
                        check()?;
                    }
                    values.push(rng.below(1 << 31) as u32);
                }
                values.sort_unstable();
                check()?;
                let sum: u128 = values
                    .iter()
                    .enumerate()
                    .map(|(i, v)| (i as u128 + 1) * *v as u128)
                    .sum();
                Ok((sum % ((1u128 << 61) - 1)) as u64)
            }
            Self::Matrix { seed, n, modulus } => {
                let mut rng = PythonRandom::new(*seed);
                let m = *modulus as u128;
                let mut columns = vec![0u128; *n];
                for _ in 0..*n {
                    check()?;
                    for col in &mut columns {
                        *col += rng.below(*modulus) as u128;
                    }
                }
                let mut total = 0u128;
                for col in columns {
                    check()?;
                    let mut row = 0u128;
                    for _ in 0..*n {
                        row += rng.below(*modulus) as u128;
                    }
                    // Reduce BEFORE multiplication: unreduced sums can exceed u128.
                    let product = ((col % m) * (row % m)) % m;
                    total = (total + product) % m;
                }
                Ok(total as u64)
            }
            Self::Prime { lo, hi } => {
                if hi <= lo {
                    return Ok(0);
                }
                let limit = (hi - 1).isqrt() as usize;
                let mut base = vec![true; limit + 1];
                base[0] = false;
                if limit >= 1 {
                    base[1] = false;
                }
                for p in 2..=limit.isqrt() {
                    if base[p] {
                        for x in (p * p..=limit).step_by(p) {
                            base[x] = false;
                        }
                    }
                }
                let primes: Vec<u64> = (2..=limit).filter(|p| base[*p]).map(|p| p as u64).collect();
                let mut total = 0;
                for start in (*lo..*hi).step_by(262144) {
                    check()?;
                    let stop = (start + 262144).min(*hi);
                    let mut segment = vec![true; (stop - start) as usize];
                    for &p in &primes {
                        let first = (p * p).max(start.div_ceil(p) * p);
                        for x in (first..stop).step_by(p as usize) {
                            segment[(x - start) as usize] = false;
                        }
                    }
                    total += segment.iter().filter(|v| **v).count() as u64;
                }
                Ok(total)
            }
            Self::Hash { seed, threshold } => {
                if *threshold == 1 << 32 {
                    return Ok(0);
                }
                let mut prefix = Sha256::new();
                prefix.update(seed.as_bytes());
                prefix.update(b":");
                for nonce in 0..u64::MAX {
                    if nonce % 4096 == 0 {
                        check()?;
                    }
                    if hash_attempt(&prefix, nonce) < *threshold {
                        return Ok(nonce);
                    }
                }
                Err("nonce range exhausted")
            }
        }
    }
}

pub fn hash_attempt(prefix: &Sha256, nonce: u64) -> u64 {
    let mut h = prefix.clone();
    h.update(nonce.to_string().as_bytes());
    let digest = h.finalize();
    u32::from_be_bytes(digest[..4].try_into().unwrap()) as u64
}

pub fn hash_benchmark(seed: &str, count: u64) {
    let mut prefix = Sha256::new();
    prefix.update(seed.as_bytes());
    prefix.update(b":");
    for n in 0..count {
        std::hint::black_box(hash_attempt(&prefix, n));
    }
}
