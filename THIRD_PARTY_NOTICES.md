# Third-party geometry notices

The AeroForge source code is distributed separately from third-party vehicle assets.
No Volkswagen, Audi, BMW, XPeng, Li Auto, or AITO source mesh is bundled.

## DrivAerML example asset

- Dataset: DrivAerML, `run_1/drivaer_1.stl`
- Authors and citation: see the [DrivAerML dataset card](https://huggingface.co/datasets/neashton/drivaerml)
- License: CC BY-SA 4.0
- Source SHA-256: `411e6651284a26fc94924106b833fd79febc6deba63922c929dd8acfc99720d2`
- Local transformation: streamed ASCII-to-binary STL conversion, normal recomputation,
  single-region normalization, and translation to a minimum ground height of `0.005 m`;
  no triangle decimation was applied.

The dataset geometry remains under its upstream license. Repository code licensing does
not replace or weaken the geometry license, attribution, or share-alike requirements.
