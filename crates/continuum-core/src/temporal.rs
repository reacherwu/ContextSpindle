//! O(1) Gated Recurrent Temporal State Core.

use crate::math::normalize;

#[derive(Debug, Clone)]
pub struct TemporalCore {
    pub state_dim: usize,
    pub input_dim: usize,
    pub state: Vec<f32>,
    pub decay: f32,
}

impl TemporalCore {
    pub fn new(input_dim: usize, state_dim: usize) -> Self {
        Self {
            input_dim,
            state_dim,
            state: vec![0.0f32; state_dim],
            decay: 0.95,
        }
    }

    /// Step temporal state conditioned on input embedding x_t.
    pub fn step(&mut self, x_t: &[f32]) -> Vec<f32> {
        let x_norm = normalize(x_t);
        let min_len = self.state_dim.min(x_norm.len());
        for i in 0..min_len {
            self.state[i] = self.decay * self.state[i] + (1.0 - self.decay) * x_norm[i];
        }
        self.state.clone()
    }

    pub fn current_state(&self) -> &[f32] {
        &self.state
    }

    pub fn reset(&mut self) {
        self.state.fill(0.0);
    }
}
