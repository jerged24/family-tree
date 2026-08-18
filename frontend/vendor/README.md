# Vendored frontend libraries

Self-contained ES-module bundles, committed so the app has **no runtime CDN
dependency** (works offline; CI needs no network for the frontend).

| File         | Package          | Version | Notes                                  |
|--------------|------------------|---------|----------------------------------------|
| `d3.js`      | `d3`             | 7.9.0   | Full D3 bundle                         |
| `d3-dag.js`  | `d3-dag`         | 1.1.0   | Sugiyama DAG layout (`graphStratify`)  |

Both are single files with all transitive dependencies inlined (no external
imports). Imported by `../src/tree.js`.

## Refreshing

Re-fetch the bundled builds from esm.sh (the `.bundle.mjs` variant inlines deps):

```bash
curl -sL "https://esm.sh/d3@7.9.0/es2020/d3.bundle.mjs"          -o d3.js
curl -sL "https://esm.sh/d3-dag@1.1.0/es2020/d3-dag.bundle.mjs"  -o d3-dag.js
```

After refreshing, confirm no external imports remain
(`grep -E 'from ["'\'']https?://' d3.js d3-dag.js` should print nothing) and
re-run the e2e suite (`pytest -m e2e`).
