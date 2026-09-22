# Bindlume project instructions

- All user-facing application text must use the shared localization catalog in `translations.json`, including shortcut-set category headings, empty states, status text, and accessibility labels. Translate new text into every supported language. Keep stable IDs and user-authored names separate from translated labels.
- Shortcut-set plugins have a top-level `category` ID from `shortcut_sets.CATEGORIES`. This is separate from each shortcut’s category. Preserve existing IDs and support legacy sets without a category as Personal.
- App control mutations must go through the running app API. A requested operation enables its prerequisite UI features automatically, validates the whole request before changing state, and reports the actual result. Do not automatically enable optional persistent memory or token tracking without a user request.
- Verify GTK behavior on the private Broadway display (`make test`); never send synthetic desktop input to the user’s active session. Include regression coverage for reported bugs and visually inspect changed surfaces.
- Follow the Aylith handbook for website design and deployment. Preserve the site’s current audience and deploy only the validated, pushed source state.
