//! CPython integer-seeded random.Random, including rejection sampling.
//! MT19937 alone is insufficient: seeding, word order, and float draws matter.
pub struct PythonRandom {
    mt: [u32; 624],
    index: usize,
}

impl PythonRandom {
    pub fn new(seed: u64) -> Self {
        let mut r = Self {
            mt: [0; 624],
            index: 624,
        };
        r.mt[0] = 19650218;
        for i in 1..624 {
            r.mt[i] = 1812433253u32
                .wrapping_mul(r.mt[i - 1] ^ (r.mt[i - 1] >> 30))
                .wrapping_add(i as u32);
        }
        let key = [seed as u32, (seed >> 32) as u32];
        let len = if seed > u32::MAX as u64 { 2 } else { 1 };
        let (mut i, mut j) = (1, 0);
        for _ in 0..624 {
            r.mt[i] = (r.mt[i] ^ (r.mt[i - 1] ^ (r.mt[i - 1] >> 30)).wrapping_mul(1664525))
                .wrapping_add(key[j])
                .wrapping_add(j as u32);
            i += 1;
            j += 1;
            if i >= 624 {
                r.mt[0] = r.mt[623];
                i = 1;
            }
            if j >= len {
                j = 0;
            }
        }
        for _ in 0..623 {
            r.mt[i] = (r.mt[i] ^ (r.mt[i - 1] ^ (r.mt[i - 1] >> 30)).wrapping_mul(1566083941))
                .wrapping_sub(i as u32);
            i += 1;
            if i >= 624 {
                r.mt[0] = r.mt[623];
                i = 1;
            }
        }
        r.mt[0] = 0x80000000;
        r
    }

    pub fn word(&mut self) -> u32 {
        if self.index == 624 {
            for i in 0..624 {
                let y = (self.mt[i] & 0x80000000) | (self.mt[(i + 1) % 624] & 0x7fffffff);
                self.mt[i] =
                    self.mt[(i + 397) % 624] ^ (y >> 1) ^ if y & 1 != 0 { 0x9908b0df } else { 0 };
            }
            self.index = 0;
        }
        let mut y = self.mt[self.index];
        self.index += 1;
        y ^= y >> 11;
        y ^= (y << 7) & 0x9d2c5680;
        y ^= (y << 15) & 0xefc60000;
        y ^= y >> 18;
        y
    }

    pub fn bits(&mut self, k: u32) -> u64 {
        assert!(k <= 64, "bit count must not exceed 64");
        if k == 0 {
            return 0;
        }
        if k <= 32 {
            return (self.word() >> (32 - k)) as u64;
        }
        let lo = self.word() as u64;
        lo | (((self.word() >> (64 - k)) as u64) << 32)
    }

    pub fn below(&mut self, n: u64) -> u64 {
        assert!(n > 0, "upper bound must be positive");
        let k = 64 - n.leading_zeros();
        loop {
            let x = self.bits(k);
            if x < n {
                return x;
            }
        }
    }

    pub fn random(&mut self) -> f64 {
        let a = self.word() >> 5;
        let b = self.word() >> 6;
        (a as f64 * 67108864.0 + b as f64) / 9007199254740992.0
    }
}
