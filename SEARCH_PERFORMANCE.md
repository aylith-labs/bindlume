# Search timing — 2026-09-19

Measured the installed app on the current desktop, with 229 shortcuts, List view, Columns enabled, grouping enabled, no type/bookmark/visibility filter, and the existing saved category expansion state. Five repetitions used synthetic Wayland keyboard input with 400 ms between steps: empty → t → te → tem → te → t. Search was cleared afterwards.

| Transition | Matches | Median render handler | Median key event → GTK paint | Worst key event → GTK paint |
| --- | ---: | ---: | ---: | ---: |
| empty → t | 229 | 164.5 ms | 214.6 ms | 224.7 ms |
| t → te | 56 | 80.6 ms | 95.9 ms | 104.0 ms |
| te → tem | 41 | 21.6 ms | 31.1 ms | 33.7 ms |
| tem → te | 56 | 29.2 ms | 40.9 ms | 44.3 ms |
| te → t | 229 | 180.7 ms | 224.1 ms | 231.2 ms |

Filtering takes 0.6–1.0 ms. The main cost is the synchronous GTK list-model splice and resulting row creation/rebinding: median 153.2 ms for empty → t and 169.9 ms for te → t. Keyboard/extras updates still run in List view and add about 4–11 ms. Search expands matching categories, so t exposes many rows, including categories previously collapsed.

Timing begins when GTK receives the key event. It excludes input-device/compositor delivery before that event and physical display scanout after GTK's after-paint signal. No performance optimization was applied during this measurement.

Profiling is opt-in: start a fresh process with `SHORTCUTS_PROFILE_SEARCH=/tmp/search.jsonl python app.py`. Stop the resident instance first; activating an existing instance does not change its environment. The log contains search queries and phase timings, so enable it only for an intentional diagnostic session.

## Clean defaults: repeated `f → fi → fil → fi → f → empty`

Measured before and after the row reuse change on 2026-09-19, using 229 live Hyprland shortcuts, fresh default features, flat list and columns. Three repetitions used Wayland keyboard input (`wtype`), with 300 ms between steps, and GTK's `after-paint` signal. Temporary preferences isolated the probe from the user's saved state.

| Transition | Before render | After render | Before key → paint | After key → paint |
| --- | ---: | ---: | ---: | ---: |
| empty → f | 81.5 ms | 10.0 ms | 106.8 ms | 21.3 ms |
| f → fi | 9.5 ms | 6.6 ms | 13.9 ms | 9.2 ms |
| fi → fil | 1.0 ms | 1.1 ms | 2.9 ms | 3.1 ms |
| fil → fi | 4.1 ms | 1.6 ms | 7.7 ms | 4.8 ms |
| fi → f | 75.0 ms | 15.4 ms | 100.6 ms | 27.1 ms |
| f → empty | 101.5 ms | 10.3 ms | 134.9 ms | 24.9 ms |

Values are medians; the worst observed key-to-paint time fell from 137.3 to 28.9 ms. These are local measurements, not guarantees for every source or machine. GTK paint excludes physical scanout.

Result reconciliation now preserves unchanged entries throughout the list, rather than replacing the middle span. A bounded pool of 256 detached rows reuses widgets during repeated searches and backspacing. Widgets are still created lazily by the virtualized list. Cache keys include item content, appearance and bookmark/visibility feature flags; reused rows refresh their marks and hover state. Regression coverage checks virtualization, repeated filtering, correct actions, selection, marks, and scroll preservation.
