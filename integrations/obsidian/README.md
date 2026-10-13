# Lingguang Knowledge

Desktop-only Obsidian connector for the local Lingguang Knowledge Studio worker. Version 0.1.0 beta, not yet listed in the official community directory.

## Install

Start the local backend using its README, configure your own Agent/API and speech model. Copy main.js, manifest.json and styles.css into your vault's `.obsidian/plugins/lingguang-knowledge/`. Enable the plugin through Obsidian Community plugins settings (manual installation). Run the command “Lingguang Knowledge: 收集B站或YouTube视频”. Pending jobs are checked every 5 seconds while Obsidian is open. Completed Markdown and PNG/JPG/SVG assets are imported to the configured folder; existing notes are not overwritten.

RSS collection remains in the backend webpage for this first release. Only jobs submitted through this plugin are imported. Video/audio/transcript bulk downloads remain available in the backend history page. The plugin does not itself execute FFmpeg or ship speech models.

## Required disclosures

Plugin code is MIT and currently has no paywall. It connects over HTTP only to a user-configured localhost/127.0.0.1 backend; no telemetry. The backend may send transcript text to the user's configured external Agent/API and sources to Bilibili/YouTube/RSS providers. API providers may charge fees: classify as Optional payments when submitting to the community directory. This plugin does not collect API keys, add advertisements, or implement checkout. Credentials belong in the backend, not the vault.

The local worker must be online; mobile is not supported. Failed jobs produce a notice and are retained in the local backend. Import images only, not original media. The generated note may contain the backend's default article style; personalize backend prompts for learning notes.

## Verification and release status

Node tests mock Obsidian requestUrl and vault writes. Real Obsidian desktop installation and cross-version compatibility have not been tested. Do not claim official approval. Community submission needs a standalone plugin repository, release assets, required metadata and Obsidian review. Built package has no bundler dependency; main.js uses the provided Obsidian API runtime.

Official policies: https://docs.obsidian.md/community-directory/developer-policies
Payments/disclosure: https://docs.obsidian.md/community-directory/faq
Submission: https://docs.obsidian.md/Plugins/Releasing/Submit%20your%20plugin
