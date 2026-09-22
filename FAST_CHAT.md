# Bindlume: a faster desktop companion

Research and implementation review, 21 September 2026.

## Recommendation

Use a small, tool-capable model over a direct API for ordinary shortcut searches and app preferences. Keep installed coding-agent CLIs available for users who want their existing subscription or broader reasoning. Make the provider an explicit user choice; do not silently switch a subscription conversation to a metered API.

There is no universal fastest model. Measure first visible text, first successful app action, total completion, and errors on the actual machine. A smaller model that needs three corrective tool calls can be slower than a larger model that succeeds once. No live hosted-model speed claim has been established in this review.

## What was making the current path inefficient

The app spawned a coding CLI on each turn, inherited its globally configured model, and sent a lengthy control instruction block. Automatic selection also waited for fresh subscription quota calls; those have 10–12 second timeouts. A newly selected provider received conversation history including the just-added user message, followed by that same request again.

The changes remove the quota wait from sending, retain asynchronous usage refresh, avoid that duplicated user message, and cap transferred conversation history. A direct streaming adapter bypasses CLI startup and MCP process startup. Streaming UI updates are coalesced every 50 ms instead of rebuilding rich content for every token. It calls the same running-app API, so changes still update the UI immediately and pass its validation.

“App updated” was not a reload notification. The old Codex event parser emitted it for every completed MCP call, including read-only searches. Status now distinguishes working, finished, and failed tool calls without asserting that a setting changed.

## Provider options

| Path | Good fit | Tradeoff |
| --- | --- | --- |
| Gemini API / Flash-Lite | Small, frequent searches and structured app actions | Separate API credentials/billing; test tool accuracy |
| OpenRouter | Comparing hosted models and provider routes behind one API | Extra routing layer, provider-dependent latency/privacy |
| Ollama | Local inference and a persistent local model server | Cold model loading, RAM/VRAM and CPU/GPU limits |
| LM Studio or compatible server | A local GUI-managed model or an existing endpoint | Compatibility and tool quality vary by model/server |
| Installed Codex/Claude/Gemini/OpenCode CLI | Existing authenticated account and harness workflow | Process/context overhead; global model may be oversized |

Google describes Gemini 2.5 Flash-Lite as intended for economical, low-latency work and documents function calling. It is a configurable starting point, not a claim that it is the newest or always the best model. [Model documentation](https://ai.google.dev/gemini-api/docs/models/gemini-2.5-flash-lite).

Gemini offers an OpenAI-compatible endpoint supporting streaming and function calls. Its reasoning controls differ by model generation: some models can disable thinking, while others support only reduced effort. Gemini 3 tool conversations also need thought-signature handling. The initial preset uses 2.5 Flash-Lite; changing to another model requires testing its tool protocol and reasoning defaults. [Compatibility documentation](https://ai.google.dev/gemini-api/docs/openai).

OpenRouter separates gateway overhead from provider/model inference. Its provider routing offers latency/throughput preferences and restrictions. For a desktop assistant, time to first token and successful tool round-trip matter more than bulk tokens per second. Choose a concrete model; avoid an unexamined automatic fallback when cost or data destination matters. The current Bindlume adapter uses the normal provider routing defaults rather than asserting a particular latency guarantee. [Performance](https://openrouter.ai/docs/guides/best-practices/latency-and-performance), [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

Ollama supports a subset of the compatible API, including chat completions and tool calling for supported models. A model’s presence alone does not establish tool competence. Its compatible interface can serve the same app adapter without a cloud key. [API compatibility](https://docs.ollama.com/api/openai-compatibility).

Ollama documents preloading and keeping models resident. Use `ollama ps` to inspect whether a model is on GPU or CPU; test cold and warm requests separately. Do not preload a large model automatically just because the shortcut browser opened. Local-only mode can disable Ollama’s cloud features; a localhost endpoint alone is not proof that the selected model runs locally. [Ollama FAQ](https://docs.ollama.com/faq).

LM Studio exposes compatible chat endpoints on its local server. Set Bindlume’s Custom API base URL to the server’s `/v1` address and enter the loaded model ID. Confirm the chosen model supports tools, not only plain text chat. [LM Studio compatibility](https://lmstudio.ai/docs/developer/openai-compat).

## Configuration in Bindlume

Open **AI companion settings → Direct model connections**. Expand the provider, set its model and base URL, and enable it. Start a new conversation and choose that provider in the chat selector.

- Gemini API: `https://generativelanguage.googleapis.com/v1beta/openai`, key variable `GEMINI_API_KEY`.
- OpenRouter: `https://openrouter.ai/api/v1`, key variable `OPENROUTER_API_KEY`.
- Ollama: `http://localhost:11434/v1`; install a tool-capable model separately. The editable example is `qwen3:4b`.
- Custom API: for example `http://localhost:1234/v1` for LM Studio; enter the exact model ID. Optional key variable `BINDLUME_API_KEY`.

Fields store the **environment variable name**, not the API secret. The app process must inherit that variable; restart the app after setting it. A CLI subscription does not automatically grant API credits. Connections are disabled by default. HTTP is accepted only on localhost; remote endpoints require HTTPS. Redirects are rejected to avoid forwarding credentials to a different destination.

The adapter streams visible output and exposes one app-control function. It does not grant a local shell or a file-writing tool. Calls have bounded response/context sizes and an eight-round tool limit; errors are returned to the model and shown to the user. Persistent memory and token display remain optional. Cancellation stops further tool actions; a silent HTTP read can take up to the socket timeout to return.

## Validation and next measurements

Regression tests cover fragmented streamed arguments, validated app-tool dispatch, failures, cancellation before sending, URL restrictions, and private cache permissions. The UI suite checks the visible composer and empty queue button. Hosted providers were not called with paid credentials, and a local model was not installed as part of this change. Test each configured endpoint before treating it as production-ready.

Use a small evaluation set: find the theme shortcut, filter Chromium tabs, bookmark one known shortcut, change light/dark mode, undo a change, reject an unknown setting, and resolve an ambiguous shortcut. Run at least 20 warm turns and several cold starts per provider. Record median and p95 latency, number of tool calls, correct final state, token usage when reported, and cost. Separate model time from app API and rendering time. Avoid showing an estimated quota as provider-reported usage.

## Native startup and interaction fixes

Removed an unnecessary compositor reload during launch. Window and keyboard-device discovery move off GTK’s UI thread. A private, versioned shortcut cache displays saved rows while live data refreshes; uncached sources show a loading skeleton. Invalid or week-old caches are ignored. The launcher’s existing-instance D-Bus probe gets a one-second timeout.

Keyboard selection no longer changes on pointer-motion events. Scroll scrims suppress GTK’s competing edge effects. Shortcut capture requests temporary OS shortcut inhibition and restores normal handling after completion, Escape, or closing the picker. The original test invoked the handler directly; new coverage exercises the controller and cancellation lifecycle. Broadway tests cannot establish whether a particular compositor grants inhibition.

The Gemini 2.5 Flash-Lite and Ollama Qwen3 4B presets request `reasoning_effort: none` for short app tasks; other models retain their own defaults. Ollama documents this compatibility field and lists Qwen3 4B as supporting tools and thinking. Benchmark tool accuracy as well as latency when disabling reasoning. [Ollama compatibility](https://docs.ollama.com/api/openai-compatibility), [Qwen3 4B](https://ollama.com/library/qwen3:4b).
