# Nora generation journey

Verified against the original studio forms plus Nora adapters at `8b61e89`,
2026-11-01. See the deployment ledger for live browser verification.

```mermaid
flowchart TD
  Login[Sign in] --> Studio[Choose Image or Video Studio]
  Studio --> Model[Choose configured model]
  Model --> Inputs[Attach supported references and enter prompt]
  Inputs --> Settings[Set supported dimensions, motion and generation controls]
  Settings --> Quote[Review estimate or unknown cost and published rates]
  Quote --> Enqueue[Add to persistent queue]
  Enqueue --> Start[Explicitly start queue]
  Start --> Result[Review output and available billing]
```

Input references stay unmodified by the adapter. H3 guide conditioning can crop
inside the model when guide/output aspect ratios differ; the form explains this.
Other MuAPI studios are explicitly unconnected. Queued or running work blocks
catalog refresh so its endpoint settings are not replaced underneath it. Empty
prompts do not trigger cost-estimate requests.
