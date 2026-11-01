# Limitations

- The model is a single 2D synthetic cross-section with local feet-based coordinates. It does not establish geological realism for a field or support a 3D reservoir interpretation.
- Offsets provide sparse regional support. Their exact synthetic marker picks and a known layer-response calibration make this experiment more constrained than real interpretation.
- The GR response deliberately supplies signed center-distance information. Real GR curves need not identify which side of a target the bit occupies. Saturation removes precise center information; the replay carries forward unresolved interpretation and records that failure.
- The uncertainty band is assumed. It is not a calibrated confidence, prediction, or posterior interval.
- Replay recommendations do not change the recorded path. Only causal commands change future simulated positions and observations.
- The causal response models inclination changes and geometric integration. It excludes toolface dynamics, bit/formation interaction, telemetry delay, drilling mechanics, pressure, well control, and operational safety controls.
- The landing build uses a 6 degrees/100 ft limit; causal lateral comparisons use 3 degrees/100 ft. Mixing these intervals would misstate constraint compliance.
- A single seed and geological scenario support a reproducible software case study, not a general claim that one strategy outperforms another. No target-success threshold is used to tune a run after evaluation.
- Numeric scoring approximates the nonlinear truth field at a documented integration resolution. Estimated piecewise-linear zone scores use exact interval integration.
- Project storage is local and intended for a single writer. There is no multi-user database, operational deployment, or production certification.
- Older projects without spatial references can be inspected, but cannot establish common-datum interpretation or steering performance until reimported with explicit references.
- Browser/platform UI verification is outside this implementation's verification scope. Automated scientific, service and report checks do not prove every interactive workflow behaves correctly.
