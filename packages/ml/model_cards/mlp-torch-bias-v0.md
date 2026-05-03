# Model card — `mlp-torch-bias-eurusd-1h-v0`

## Model details

- **ID**: `mlp-torch-bias-eurusd-1h-v0`
- **Family**: 3-layer MLP, dropout regularization (PyTorch)
- **Owner**: Ichor bias agent
- **Status**: planned — Phase 1
- **Expected Brier**: 0.21 on hold-out

## Intended use

Captures higher-order feature interactions that tree models can miss when
the splits are coarse. Held in the ensemble at lower weight as it requires
careful regularization to avoid overfitting on sub-50k bar training sets.

Same inputs as the LightGBM card. Architecture:

```
Input (~30 features)
  → Linear(30, 64) + ReLU + Dropout(0.3)
  → Linear(64, 32) + ReLU + Dropout(0.3)
  → Linear(32, 1) + Sigmoid
```

## Training

- Adam optimizer, `lr=1e-3`, `weight_decay=1e-4`.
- Early stopping on val Brier with patience 5 epochs.
- Batch size 256, ~50 epochs typical.

## Caveats & failure modes

- Easy to overfit — keep the architecture small and rely on dropout +
  early stopping.
- Calibration not trustworthy out of the box — isotonic post-hoc mandatory.
- Latency: < 2 ms.

## Aggregator weight

Initial weight: 0.10 — promote to 0.15 if 30d rolling Brier consistently
beats the boosters.
