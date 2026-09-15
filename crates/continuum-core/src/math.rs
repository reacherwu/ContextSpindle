//! Vector arithmetic and similarity kernels.

#[inline]
pub fn dot(a: &[f32], b: &[f32]) -> f32 {
    debug_assert_eq!(a.len(), b.len());
    let mut sum = 0.0f32;
    // Chunk by 4 for basic auto-vectorization
    let chunks_a = a.chunks_exact(4);
    let chunks_b = b.chunks_exact(4);
    let rem_a = chunks_a.remainder();
    let rem_b = chunks_b.remainder();

    for (ca, cb) in chunks_a.zip(chunks_b) {
        sum += ca[0] * cb[0] + ca[1] * cb[1] + ca[2] * cb[2] + ca[3] * cb[3];
    }
    for (va, vb) in rem_a.iter().zip(rem_b.iter()) {
        sum += va * vb;
    }
    sum
}

#[inline]
pub fn norm(a: &[f32]) -> f32 {
    dot(a, a).sqrt()
}

#[inline]
pub fn normalize(a: &[f32]) -> Vec<f32> {
    let n = norm(a);
    if n > 1e-8 {
        a.iter().map(|v| v / n).collect()
    } else {
        a.to_vec()
    }
}

#[inline]
pub fn cosine_similarity(a: &[f32], b: &[f32]) -> f32 {
    let norm_a = norm(a);
    let norm_b = norm(b);
    if norm_a < 1e-8 || norm_b < 1e-8 {
        return 0.0;
    }
    let sim = dot(a, b) / (norm_a * norm_b);
    sim.clamp(0.0, 1.0)
}
