//! Native Real-Text Embedder for Continuum in pure Rust.
//!
//! Provides deterministic subword/n-gram hashing and dense normalized projection
//! with zero external dependencies, zero PyTorch dependency, and microsecond latency.

use crate::math::normalize;

/// Deterministic Pseudo-Random Number Generator (Xorshift64).
#[derive(Debug, Clone)]
pub struct SimpleRng {
    state: u64,
}

impl SimpleRng {
    pub fn new(seed: u64) -> Self {
        Self {
            state: if seed == 0 { 0x54321 } else { seed },
        }
    }

    #[inline]
    pub fn next_u64(&mut self) -> u64 {
        let mut x = self.state;
        x ^= x << 13;
        x ^= x >> 7;
        x ^= x << 17;
        self.state = x;
        x
    }

    #[inline]
    pub fn next_f32(&mut self) -> f32 {
        (self.next_u64() as f64 / u64::MAX as f64) as f32
    }

    /// Generates standard normal random variable via Box-Muller transform.
    pub fn next_gaussian(&mut self) -> f32 {
        let u1 = self.next_f32().max(1e-7);
        let u2 = self.next_f32();
        let r = (-2.0 * u1.ln()).sqrt();
        let theta = 2.0 * std::f32::consts::PI * u2;
        r * theta.cos()
    }
}

/// FNV-1a 64-bit hash.
#[inline]
fn fnv1a_hash(text: &str) -> u64 {
    let mut hash = 0xcbf29ce484222325u64;
    for &byte in text.as_bytes() {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(0x100000001b3);
    }
    hash
}

/// English stop words filter for code and text processing.
fn is_stop_word(word: &str) -> bool {
    matches!(
        word,
        "a" | "an" | "and" | "are" | "as" | "at" | "be" | "by" | "for" | "from" |
        "has" | "he" | "in" | "is" | "it" | "its" | "of" | "on" | "that" | "the" |
        "to" | "was" | "were" | "will" | "with"
    )
}

#[derive(Debug, Clone)]
pub struct RealTextEmbedder {
    pub dim: usize,
    pub num_buckets: usize,
    projection: Vec<f32>, // Shape: [num_buckets * dim]
}

impl RealTextEmbedder {
    pub fn new(dim: usize, seed: u64) -> Self {
        let num_buckets = 4096;
        let mut rng = SimpleRng::new(seed);
        let mut proj = vec![0.0f32; num_buckets * dim];

        // Fill projection matrix with standard Gaussian values
        for i in 0..(num_buckets * dim) {
            proj[i] = rng.next_gaussian();
        }

        // Normalize each column (each dimension)
        for d in 0..dim {
            let mut col_norm_sq = 0.0f32;
            for b in 0..num_buckets {
                let val = proj[b * dim + d];
                col_norm_sq += val * val;
            }
            let col_norm = col_norm_sq.sqrt().max(1e-8);
            for b in 0..num_buckets {
                proj[b * dim + d] /= col_norm;
            }
        }

        Self {
            dim,
            num_buckets,
            projection: proj,
        }
    }

    /// Pre-tokenizes text: splits camelCase, underscores, dots, dashes into lowercase word tokens.
    pub fn pre_tokenize(&self, text: &str) -> Vec<String> {
        let mut tokens = Vec::new();
        let mut current = String::new();
        let chars: Vec<char> = text.chars().collect();

        for i in 0..chars.len() {
            let c = chars[i];
            if c.is_alphanumeric() {
                // Check camelCase transition (lower followed by upper)
                if c.is_uppercase() && i > 0 && chars[i - 1].is_lowercase() && !current.is_empty() {
                    tokens.push(current.to_lowercase());
                    current = String::new();
                }
                current.push(c);
            } else {
                if !current.is_empty() {
                    tokens.push(current.to_lowercase());
                    current = String::new();
                }
            }
        }
        if !current.is_empty() {
            tokens.push(current.to_lowercase());
        }

        tokens
    }

    /// Embeds arbitrary text into a normalized dense vector of length `self.dim`.
    pub fn embed(&self, text: &str) -> Vec<f32> {
        let tokens = self.pre_tokenize(text);
        if tokens.is_empty() {
            let val = 1.0 / (self.dim as f32).sqrt();
            return vec![val; self.dim];
        }

        // Accumulate into dense vector
        let mut dense = vec![0.0f32; self.dim];

        // 1-grams
        for word in &tokens {
            if is_stop_word(word) {
                continue;
            }
            let h = fnv1a_hash(word);
            let bucket = (h as usize) % self.num_buckets;
            let sign = if (h >> 32) % 2 == 0 { 1.0f32 } else { -1.0f32 };

            let offset = bucket * self.dim;
            for d in 0..self.dim {
                dense[d] += sign * self.projection[offset + d];
            }
        }

        // 2-grams
        for i in 0..tokens.len().saturating_sub(1) {
            let w1 = &tokens[i];
            let w2 = &tokens[i + 1];
            if is_stop_word(w1) && is_stop_word(w2) {
                continue;
            }
            let bi = format!("{w1} {w2}");
            let h = fnv1a_hash(&bi);
            let bucket = (h as usize) % self.num_buckets;
            let sign = if (h >> 32) % 2 == 0 { 1.0f32 } else { -1.0f32 };

            let offset = bucket * self.dim;
            for d in 0..self.dim {
                dense[d] += sign * self.projection[offset + d];
            }
        }

        normalize(&dense)
    }
}
