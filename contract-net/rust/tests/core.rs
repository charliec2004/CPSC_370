use auctioneers::{
    random::PythonRandom,
    strategy::{Model, Strategy},
    tasks::Work,
};
use serde_json::json;
use std::time::Instant;

#[test]
fn random_matches_cpython_mixed_draws() {
    let mut random = PythonRandom::new(370);
    // Generated using Python 3.12 random.Random(370), in this draw order.
    for (bits, expected) in [
        (0, 0),
        (1, 0),
        (31, 1345292143),
        (32, 3566661997),
        (33, 8197107193),
        (63, 5456699038192240523),
        (64, 5153438635458767530),
    ] {
        assert_eq!(random.bits(bits), expected);
    }
    for expected in [0.6650186845395569, 0.08556723061595028, 0.6124921709915234] {
        assert_eq!(random.random(), expected);
    }
}

#[test]
#[should_panic(expected = "upper bound must be positive")]
fn zero_random_bound_fails_instead_of_hanging() {
    PythonRandom::new(0).below(0);
}

#[test]
fn expired_work_never_starts() {
    for (kind, params) in [
        ("sort_checksum", json!({"seed": 0, "n": 100})),
        ("monte_carlo_pi", json!({"seed": 0, "samples": 100})),
        ("matmul_mod", json!({"seed": 0, "n": 10, "mod": 2})),
        ("prime_count", json!({"lo": 2, "hi": 100})),
        ("hash_search", json!({"seed": "test", "threshold": 1})),
    ] {
        let work = Work::parse(kind, &params).unwrap();
        assert_eq!(
            work.execute(Some(Instant::now())),
            Err("execution deadline exceeded")
        );
    }
}

#[test]
fn quotes_reserve_queue_and_adapt_to_results() {
    let mut strategy = Strategy::new(Model {
        monte: 0.001,
        ..Model::default()
    });
    let work = Work::Monte {
        seed: 0,
        samples: 100,
    };
    for queue in [-1., f64::NAN, f64::INFINITY] {
        assert!(strategy.quote(&work, 10., 2., queue).is_none());
    }
    assert!(strategy.quote(&work, 10., 0.2, 0.).is_none());
    assert!(strategy.quote(&work, 10., 1., 0.9).is_none());
    let first = strategy.quote(&work, 10., 2., 0.).unwrap();
    assert!(first.price >= first.safe_finish * strategy.rules.cost_rate);
    assert!(first.safe_finish >= first.compute + first.overhead);
    strategy.rejected(work.kind());
    let reduced = strategy.quote(&work, 10., 2., 0.).unwrap();
    assert!(reduced.price >= reduced.baseline_price);
    for _ in 0..5 {
        strategy.settled(&reduced, "correct", Some(0.1), Some(0.4));
    }
    assert!(strategy.network >= 0.32);
    assert!(strategy.quote(&work, 10., 2., 0.).unwrap().price > reduced.price);
}

#[test]
fn hash_bids_require_high_probability_of_finishing() {
    let strategy = Strategy::new(Model {
        hash: 0.00001,
        ..Model::default()
    });
    let work = Work::Hash {
        seed: "test".into(),
        threshold: 65536,
    };
    assert!(strategy.quote(&work, 10., 1., 0.).is_none());
    let quote = strategy.quote(&work, 10., 5., 0.).unwrap();
    assert!(quote.model_success_probability >= 0.95);
}

#[test]
fn repeated_rejections_cannot_erase_cost_floor() {
    let mut strategy = Strategy::new(Model {
        monte: 0.001,
        ..Model::default()
    });
    let work = Work::Monte {
        seed: 0,
        samples: 100,
    };
    for _ in 0..100 {
        strategy.rejected(work.kind());
    }
    let q = strategy.quote(&work, 10., 2., 0.).unwrap();
    assert!(q.price >= q.safe_finish * 1.28);
    assert!(strategy.quote(&work, 0.01, 2., 0.).is_none());
    strategy.settled(&q, "correct", Some(0.1), Some(1.));
    let next = strategy.quote(&work, 10., 3., 0.).unwrap();
    assert!(
        next.price >= 1.2,
        "loss must push price toward measured cost"
    );
}

#[test]
fn token_transport_requires_tls_except_loopback() {
    use auctioneers::config::validate_url;
    for url in [
        "wss://example.com/agent?room=test",
        "ws://127.0.0.1:1234/agent",
        "ws://[::1]:1234/agent",
    ] {
        assert!(validate_url(url).is_ok());
    }
    for url in [
        "ws://example.com/agent",
        "https://example.com",
        "wss://user:secret@example.com",
        "wss://example.com/#token",
    ] {
        assert!(validate_url(url).is_err());
    }
}
