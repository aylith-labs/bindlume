# System One models in Bindlume

Researched 22 September 2026. System One models return typed decisions, not generated prose. Bindlume supports `POST /v1/systemone` with `choice`, `score`, and `noul` questions. These connections are separate from chat-completions connections.

## Three uses

Open **AI companion settings → System One connections**, configure a provider, enable it, and press **Apply**. Credentials are environment-variable names; the running app must inherit the corresponding secret. Remote URLs require HTTPS; plain HTTP is restricted to loopback. Connections and workflows start disabled.

- **Shortcut ranking:** choose a connection in the ranking selector. After a 300 ms pause, the model reranks the first 24 existing search matches. Remaining matches retain their order. Active filters still apply; this is reranking, not semantic retrieval of excluded shortcuts. Search results become a flat ranked list while enabled. Errors retain the original order; obsolete responses cannot replace a newer query.
- **Companion routing:** **Automatic** now tries enabled loopback System One connections first. Explicit commands run through the app API; uncertain or unsupported requests pass to the next local decision connection, then the quota-selected general assistant. Intermediate rejections are not shown as answers. Cancellation stops the chain; an app mutation failure is never replayed through another agent. Without a local connection, the optional routing selector and existing general-assistant selection still apply.
- **Decision chatbot:** explicit commands cover shortcut searches, bookmarks and hiding, feature toggles (including all features), showing filters, layouts, modifiers, source selection, opening panels, and common settings. They use deterministic parsing and actual API results without a model round trip. Ambiguous shortcut names return candidates instead of changing one arbitrarily. For other setting phrasings, start a new chat and select **Jev / Laya / Von / Custom API · System One**. A lexical shortlist finds explicitly named settings using English aliases and translated UI labels. A single model request selects from predefined values for those settings, with an unchanged option for each. Choice IDs use actual values, such as `dark` and `16`, rather than numeric positions. Vague requests without a recognised setting name abstain. It also distinguishes commands from questions. High-probability selections pass through the running app's validated batch API; the reply prints actual applied values and the selected decisions. No generated prose or generated tool arguments are required. An uncertain selection prevents the entire batch from running. Each turn uses the current explicit request, without conversational reference resolution.

Supported chatbot settings: theme, compact layout, app/action icons, shortcut tooltips, system typography, font size (9–28), window/in-app animations, keyboard snippets, snippet vignette, and guide side preview. It does not change desktop bindings, model connections, or arbitrary configuration. Memory and token tracking can only be enabled by explicit commands naming those settings; “all features” does not enable either. More settings can be added by extending the explicit action catalog and its tests.

The 0.85 threshold is an application policy, not a measured correctness guarantee. Model probability calibration varies; evaluate real requests in the intended language. Typed output guarantees neither truth nor appropriate action selection.

## Candidates and hardware fit

The inspected development laptop has a Ryzen 5 5600H, approximately 38 GiB RAM, and an RTX 3060 Laptop GPU with 6 GiB VRAM. About 1.8 GiB VRAM was free during inspection. Weight sizes below are not total runtime memory requirements; fitting a model depends on input length, batches, precision, and other GPU users.

| Model | Local feasibility | Integration |
| --- | --- | --- |
| Laya English / typed-decisions (421M) | Good CPU candidate; likely GPU candidate with sufficient free memory | Bundled optional Laya bridge |
| Laya multilingual (322M) | Good candidate for non-English input; assess Hungarian on real requests | Same bridge with a checkpoint subfolder |
| Von (395M) | Plausible on CPU or GPU; published weights approximately 1.5 GB | Native System One server, Von preset |
| Decider 0.8B | Plausible small alternative; published bf16 weights approximately 1.4 GB | Native System One server, Custom API |
| Decider 2B | Approximately 3.5 GB bf16 weights; free GPU memory first, and allow overhead | Native System One server, Custom API |
| Qwen3.5 4B System One scorer | Approximately 8 GB for bf16 parameters alone; needs quantization/offload on this GPU | Different inference wrapper; not a verified drop-in; noncommercial weights |
| Jev | Hosted API; no public local weights identified | Jev preset, `TYPESAFE_API_KEY` |

Laya documents short per-question input budgets and reduced performance with large option sets. Multilingual and typed-decisions checkpoints serve different purposes. Von and other new releases change rapidly; compare them on the same Bindlume fixtures rather than comparing publisher benchmark headlines. Larger Decider 35B variants are not a practical first choice for this laptop.

Primary references:

- [TypeSafe API quickstart](https://docs.typesafe.ai/introduction/quickstart): endpoint, authentication, request and answer schemas.
- [Laya model card](https://huggingface.co/convaiinnovations/laya): checkpoint family, memory sizes, language support, limits and calibration notes.
- [Laya SDK source](https://github.com/NandhaKishorM/laya): `load` and `predict` used by the bridge.
- [Von source and server instructions](https://github.com/wfzyx/von).
- [Decider family](https://huggingface.co/Mapika/decider-2b): sizes, requirements and System One interface.
- [Qwen3.5 4B scorer](https://huggingface.co/pngwn/system-one-qwen3.5-4b-scorer): implementation and noncommercial licence.

## Local Laya setup

Keep ML dependencies in a separate environment. For example, from the source directory:

```sh
uv venv --python 3.12 .venv-laya
uv pip install --python .venv-laya/bin/python laya --torch-backend cpu
.venv-laya/bin/python system_one_server.py --device cpu
```

The server binds only to `127.0.0.1:8001`, loads one checkpoint at startup, and does not log request contents. First startup downloads model weights. Select the Laya preset with model `convaiinnovations/laya`. To use its multilingual checkpoint:

```sh
.venv-laya/bin/python system_one_server.py --device cpu --subfolder multilingual
```

The bridge model identifier remains `convaiinnovations/laya`; the startup subfolder selects the weights. For GPU use, install an appropriate CUDA-enabled PyTorch build in that environment and pass `--device cuda`. GPU performance has not been established by a CPU smoke test. Bindlume does not launch or download models just because a settings window opens.

Von supplies its own server (`von serve --host 127.0.0.1 --port 8000`). For Decider, run its documented `decider.serve` server and enter its base URL and accepted model ID in Custom API. Do not assume standard Ollama chat completions expose these specialised decision heads.

## Agent API

The same typed interface is available through the existing control CLI/MCP operation:

```sh
python agent_control.py request '{"operation":"decision","arguments":{"provider":"laya","state":{"request":"Use dark mode"},"questions":{"theme":{"type":"choice","instructions":"Which theme is explicitly requested?","criteria":{"dark":"Dark mode","light":"Light mode","keep":"No change"}}}}}'
```

This returns a decision without applying it. The `decision_apply` operation accepts only the supported setting IDs and values and validates the whole batch before any mutation. Decision I/O runs off GTK's main thread with a 60-second socket timeout. No hosted API is contacted unless that connection is explicitly enabled and selected.

## Validation

Tests exercise the actual HTTP bridge with a deterministic model stub, typed requests and responses, invalid answers, payload limits, credential handling, disabled connections, cancellation, uncertain decisions, routing, ranking, chat persistence, and atomic validation of setting batches. GTK tests and screenshots run on a private Broadway display. Publisher latency numbers are not laptop measurements; live-model findings should be recorded separately from protocol tests.

### Local smoke results

With Laya 0.3.5, the English checkpoint, CPU execution using four threads, and the final HTTP bridge:

- `Switch to dark theme.` selected and passed `theme=dark` to a simulated control API in 1.39 s.
- `Change font size to 16.` selected and passed `font_size=16` in 3.71 s.
- `Enable compact layout.` and `Turn off tooltips.` abstained under the 0.85 policy despite being clear requests. This checkpoint is sensitive to phrasing; support does not imply reliable automatic settings changes for every request.
- Explanation and negation requests changed nothing (1.2–1.4 s).
- A two-shortcut ranking put terminal above browser for `open a terminal` in 1.22 s.
- Routing the single-setting phrase retained the general assistant in 1.02 s; an earlier two-setting phrase routed to the decision chatbot. Routing is also conservative and phrasing-sensitive.

These are individual smoke observations, not latency percentiles or accuracy benchmarks. The control API was simulated to leave the user's settings intact; separate private GTK tests verify actual batch application. Jev, Von, Decider, CUDA execution, and multilingual checkpoint quality were not live-tested. The Laya SDK warned about calibration for choice questions with 11+ options; font-size results need particular caution. Thresholds were not lowered to force examples to pass.

## Command and Auto regressions

The initial settings-only implementation rejected ordinary app requests before inference. Explicit commands now include `show themes shortcut`, `enable filters`, `disable filters`, `enable all features`, `bookmark screenshot`, `show hidden shortcuts`, `filter by ctrl shift`, `use keyboard layout`, `open settings`, and `switch to Chromium source`. Clear setting commands also avoid the earlier phrasing-sensitive classifier. Auto starts with enabled local decision connections and hands unsupported or uncertain requests to an available general assistant. The earlier smoke timings above describe model inference, not the new deterministic command paths.

## Activity history

The local SQLite activity log defaults to the latest 1,000 operations with no age
expiry. Open it from Settings → Activity log, or ask to show the last ten
operations, show operations of yesterday, undo, or redo. Exact commands read the
journal directly without running model inference. `make activity log store
indefinitely` removes both retention limits. Zero means unlimited; deleted history
cannot be recovered by changing the retention policy back.

App API operations and direct preference, feature, bookmark, hidden-mark and source
changes are recorded. Undo/redo restores recorded app state and verifies that it
has not changed since the operation. Desktop bindings, external commands, deleted
conversations, resets, and guide changes are not reversible. The journal starts
when this version is installed; it cannot reconstruct earlier actions.
