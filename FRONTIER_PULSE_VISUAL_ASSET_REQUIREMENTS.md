# Frontier Pulse Visual Asset System — Development Requirements

## 1. Purpose

Upgrade Frontier Pulse's weekly LinkedIn podcast visuals so that a viewer can immediately recognize the format, understand the week's relevance, and identify a clear listening action while scrolling on a mobile feed.

The upgrade must replace the current generic dark blue/neon AI aesthetic with a recognizable editorial visual system. It must preserve deterministic text rendering and add a fourth visual asset for the remaining stories in each episode.

This document defines the approved product and engineering requirements. It does not require implementation in this phase.

## 2. Goals

- Establish a consistent, non-generic visual identity for Frontier Pulse.
- Make podcast format, episode topic, duration, and CTA readable at mobile-feed size.
- Introduce an original recurring character, **Pulse**, that turns weekly news into a recognizable visual narrative.
- Produce exactly four 1080 × 1350 PNG assets for every edition.
- Replace free-form visual prompting with structured editorial decisions plus deterministic visual rules.
- Avoid generated typography, illegible overlays, and repeated use of the opening cover during the remainder of the video.

## 3. Non-goals

- This work does not guarantee a specific LinkedIn impressions or click-through result; it improves creative clarity and brand consistency.
- The system must not reproduce the supplied robot reference or use it as a color reference.
- The image model must not generate headlines, labels, CTA text, watermarks, logos, or interface copy.
- The system must not rely on a single large prompt to enforce layout, typography, palette, character, and editorial selection simultaneously.

## 4. Current-State Constraints

The existing pipeline creates a cover and one or two insight cards. It uses an LLM to plan card copy and free-form abstract visual prompts, then renders text in Pillow over an AI-generated background.

The new system must retain the valuable current behavior:

- Output size: 1080 × 1350 px (4:5 portrait).
- Text is rendered deterministically after image generation.
- Safe margins are respected.
- A visual-asset manifest is produced.
- Existing `podcast_cover.jpg` compatibility behavior must remain intact unless a separately approved migration removes it.

## 5. Approved Visual Identity

### 5.1 Visual direction

The approved direction is **Editorial Earth Tactile**. It should feel like a contemporary technology publication with a human, handmade layer—not like a generic futuristic AI dashboard.

The generated illustration is the scene. Typography, cards, texture marks, and brand elements are controlled design layers.

### 5.2 Color palette

| Token | Role | Hex |
|---|---|---|
| `COLOR_BG_CHARCOAL` | Main background and dark scrim | `#1B1715` |
| `COLOR_SURFACE_INK` | Near-opaque card surfaces | `#2A2320` |
| `COLOR_TEXT_IVORY` | Primary text and light surfaces | `#F5EBDD` |
| `COLOR_TEXT_SAND` | Secondary text and metadata | `#C8B9AC` |
| `COLOR_ACCENT_TERRACOTTA` | Primary brand accent and CTA | `#C9573D` |
| `COLOR_ACCENT_APRICOT` | Highlight and emphasis accent | `#F0A35B` |
| `COLOR_ACCENT_SAGE` | Supporting category/state accent | `#718A78` |

Requirements:

- Replace cyan, emerald, amber, and violet as the default visual identity colors.
- Do not introduce blue or neon as a default accent. A story-specific exception requires explicit editorial configuration and must not change the brand system.
- Use ivory text on charcoal/ink surfaces for primary reading content.
- Do not use terracotta, apricot, or sage for small body text unless contrast validation passes.
- Keep palette tokens centralized and configurable; do not scatter raw color tuples through rendering functions.

### 5.3 Organic tactile texture system

The design layer must provide configurable, deterministic texture marks that imitate a brush, marker, and subtle paper grain.

Allowed texture primitives:

- Rough terracotta brush strokes.
- Apricot marker underlines.
- Sage irregular blocks, arrows, circles, or emphasis marks.
- Low-intensity paper grain.

Constraints:

- Apply at most two meaningful tactile gestures per asset.
- Never place texture behind a paragraph, metadata, or CTA.
- Keep a minimum 12 px visual separation between a texture mark and text it is not intentionally emphasizing.
- An intentional underline may sit beneath a single key word only; it must not reduce text contrast.
- Texture must not resemble a glitch, random noise, graffiti, or generated UI decoration.
- Texture is rendered as a controlled design layer, never requested from the image model.

## 6. Mobile Readability Requirements

### 6.1 Reading hierarchy

Every opening cover must communicate the following in under one second:

1. It is a Frontier Pulse podcast.
2. Why this week's episode matters.
3. What action to take.

Each asset must communicate one dominant idea. Multiple headlines of equal visual weight are not allowed.

### 6.2 Typography and density

| Element | Minimum size | Content limit |
|---|---:|---|
| Cover headline | 76 px, bold | 8 words; maximum 3 lines |
| Insight headline | 64 px, bold | 8 words; maximum 3 lines |
| Supporting text | 30 px | Must fit without crowding or clipping |
| Short label | 24 px | Brief label only |
| Episode/duration metadata | 28 px | One line |
| CTA | 30 px, bold | One concise action |

Additional requirements:

- Use one configured sans-serif font family with predictable cross-platform fallbacks.
- Use a headline line-height between 1.05 and 1.12.
- Use Spanish-only labels in Spanish editions. For example, use `HECHO CLAVE`, not bilingual labels such as `HECHO CLAVE / KEY FACT`.
- Do not shrink text below the stated sizes to force copy into the layout. Condense or regenerate copy instead.
- The planner must enforce the word limits before rendering.

### 6.3 Contrast and background control

- All primary text must be placed on a near-opaque controlled surface or an equivalently controlled scrim; it must not sit directly on busy artwork.
- Normal text must meet a minimum contrast ratio of 4.5:1. The target contrast for headlines and supporting text is 7:1.
- Replace glass-like/translucent text cards with predominantly opaque ink surfaces where needed for reading reliability.
- CTA text and CTA background must pass contrast validation at the configured CTA font size and weight.
- Illustration prompts must reserve the required text-safe zone as low-detail negative space.

### 6.4 Visual acceptance test

An asset passes visual QA only if all of the following are true:

- At 25% scale, the opening cover is recognizable as a podcast.
- The headline is readable without zooming.
- The CTA can be located immediately.
- No character, texture, or illustration detail competes with reading content.
- No text is clipped, overlaps another element, or extends beyond safe margins.

## 7. Pulse Character System

### 7.1 Character definition

Pulse is an original compact broadcast robot and Frontier Pulse's recurring visual host.

| Attribute | Requirement |
|---|---|
| Silhouette | Small, compact, rounded-asymmetric head and short body; not humanoid |
| Face | Ivory visor with two expressive geometric eyes; no mouth |
| Signature feature | Small terracotta signal fin on top |
| Materials | Matte warm charcoal shell, ivory visor, terracotta joints/details |
| Style | Soft editorial 3D object with simple shadows and tactile accents |
| Emotional language | Eye shape, head tilt, arms, and posture—not a mouth or generated text |

Pulse must not use headphones, cyan eyes, violet accessories, chrome materials, neon lighting, holographic interfaces, visible logos, or circuit-board scenery as a default identity.

### 7.2 Narrative modes

The planner may select only one of these modes per scene:

- `analyst`: inspecting, comparing, or understanding a technical advance.
- `alert`: reacting to a disruptive, regulatory, or market-changing event.
- `orchestrator`: arranging modules, notes, or connections for agents and automation.
- `builder`: testing or assembling pieces for a launch or product story.
- `narrator`: presenting at a microphone; reserved for the closing radar asset.

Use up to three symbolic props per scene, such as cards, blocks, notes, signals, or hand-drawn arrows. Do not use fake dashboards, readable screens, or data-heavy interface elements.

### 7.3 Composition constraints

- Pulse may occupy no more than 35% of the canvas.
- Pulse must never enter the text-safe zone.
- Character and text must be separated by side or depth plane.
- Generated scenes must use the approved palette direction and tactile editorial tone.

### 7.4 Identity consistency: approved implementation strategy

Create and use a curated library of approved, transparent-background Pulse pose assets. The first release must include at least these six poses:

1. Analyst.
2. Alert.
3. Orchestrator.
4. Builder.
5. Neutral/reaction.
6. Narrator at microphone.

The renderer selects a pose from this library based on `scene_mode` and composites it into the scene. This is required to maintain a stable character identity across editions; a text-only image-generation prompt is not sufficiently reliable for that purpose.

## 8. Asset Set

The system must generate exactly four ordered assets per edition.

| ID | File name | Manifest type | Purpose | Suggested screen time |
|---|---|---|---|---:|
| AR-01 | `episode-[n]-01-cover.png` | `cover` | Opening statement, podcast identification, duration, CTA | 3 seconds |
| AR-02 | `episode-[n]-02-insight-[slug].png` | `news_insight` | Primary story and practical impact | 5 seconds |
| AR-03 | `episode-[n]-03-insight-[slug].png` | `news_insight` | Secondary story and practical impact | 5 seconds |
| AR-04 | `episode-[n]-04-news-roundup.png` | `news_roundup` | Remaining stories, closing visual, full-episode CTA | 8 seconds |

### 8.1 AR-01 — Cover

Required content:

- `FRONTIER PULSE` brand identifier.
- An unmistakable Spanish podcast format label, for example `PODCAST SEMANAL DE IA`.
- Benefit-led cover headline.
- Episode number and duration.
- One CTA, for example `Escuchar ahora`.

The scene must support the week's editorial thesis. It may feature Pulse, but the brand and headline remain dominant.

### 8.2 AR-02 and AR-03 — Insight cards

Required content:

- Short category label.
- Plain-language story headline.
- One verified key fact.
- A concise practical implication beginning with `POR QUÉ IMPORTA:`.
- Episode footer.

AR-02 uses the highest-relevance story. AR-03 uses the next editorially relevant story. Both should select a scene mode appropriate to the news category and impact.

### 8.3 AR-04 — Closing radar

AR-04 is mandatory and replaces repeated use of AR-01 during the remaining stories.

Required text content:

- Top label: `RADAR DE CIERRE` or `TAMBIÉN ESTA SEMANA`.
- Fixed headline: `Más señales que debes tener en el radar`.
- Up to three remaining story titles, each limited to 7 words.
- CTA: `Escucha el episodio completo`.
- Footer: `FRONTIER PULSE · EPISODIO [n]`.

Required composition:

- Pulse is in `narrator` mode at a desktop microphone on the right side of the illustration.
- The left side remains clean for the text list.
- The list is rendered as numbered rows or small editorial cards, not as image-model typography.

Selection rules:

- Select remaining items after the AR-02 and AR-03 stories.
- Sort by editorial relevance and include at most three.
- If fewer than three remaining items exist, display the available items.
- If no remaining items exist, retain AR-04 and display a concise, non-fabricated invitation to the episode's analysis and context instead of an empty list.

### 8.4 Limited-data fallback

The pipeline must still produce four assets if the edition contains fewer than two usable stories. It must not invent a second news claim. In that condition:

- AR-02 presents the verified primary story.
- AR-03 becomes an `edition_context` card using only verified edition-level context or a neutral listening invitation.
- AR-04 follows the no-remaining-items rule above.
- The manifest must retain four ordered assets and indicate the fallback content type.

## 9. Prompt and Planning Architecture

### 9.1 Separation of responsibilities

Do not expand the current planner into a single mega-prompt. Implement the following separation:

| Layer | Responsibility |
|---|---|
| Editorial planner | Produce concise, factual copy, select stories, choose a constrained `scene_mode`, and describe a short `scene_subject` |
| Brand configuration | Own palette, texture rules, typography, safe zones, character rules, and prohibited visual traits |
| Scene-prompt builder | Combine the brand configuration, asset template, `scene_mode`, and `scene_subject` into the actual no-text image prompt |
| Asset renderer | Compose backgrounds, Pulse pose, cards, texture, typography, and CTA deterministically |

### 9.2 Planner output

The planner must return validated JSON. It must no longer return arbitrary free-form `visual_prompt` strings.

At minimum, the plan must contain:

```json
{
  "cover": {
    "headline": "string, <= 8 words",
    "scene_mode": "analyst | alert | orchestrator | builder | neutral",
    "scene_subject": "string, concise visual situation"
  },
  "story_a": {
    "slug": "string",
    "title": "string, <= 8 words",
    "key_fact": "string, factual and concise",
    "why_it_matters": "string, starts with POR QUÉ IMPORTA:",
    "source_reference": "string",
    "scene_mode": "analyst | alert | orchestrator | builder",
    "scene_subject": "string, concise visual situation"
  },
  "story_b": {
    "slug": "string",
    "title": "string, <= 8 words",
    "key_fact": "string, factual and concise",
    "why_it_matters": "string, starts with POR QUÉ IMPORTA:",
    "source_reference": "string",
    "scene_mode": "analyst | alert | orchestrator | builder",
    "scene_subject": "string, concise visual situation"
  },
  "roundup": {
    "remaining_titles": ["string, <= 7 words"],
    "scene_subject": "Pulse narrating the remaining weekly signals at a microphone"
  }
}
```

The renderer must validate content limits and use deterministic fallbacks when the planner response is invalid, incomplete, or unavailable.

### 9.3 Scene-prompt builder

The scene-prompt builder must use fixed template fragments rather than LLM-authored prompts. Each final prompt must:

- Describe only artwork without readable text.
- State the asset's reserved text-safe zone.
- State the approved visual material, color direction, and tactile tone.
- State the selected Pulse mode when a character scene is required.
- Exclude letters, words, typography, watermark, logo, UI, dashboard, neon, and generic blue cyber aesthetics.

The generated prompt should be concise and compositional. Palette values, font sizes, contrast math, and card-copy rules belong in code/configuration rather than in the image prompt.

## 10. Data Model and Rendering Changes

The implementation must introduce or update the following concepts:

- A centralized `VisualTheme` or equivalent configuration for palette tokens, typography, texture settings, and safe-zone settings.
- An approved Pulse pose registry that maps `scene_mode` to transparent pose assets.
- `RoundupCardText` (or equivalent) with label, headline, remaining titles, CTA, and footer.
- Support for `edition_context` fallback content when a secondary verified story is unavailable.
- A `news_roundup` manifest asset type.
- Manifest validation updated from a maximum of three assets to exactly four assets.
- A renderer dedicated to AR-04 rather than overloading the insight-card renderer.
- A deterministic scene-prompt builder that replaces planner-supplied `visual_prompt` values.

The existing cover and insight renderers may be refactored, but their external output contract must remain compatible with the pipeline and manifest consumers.

## 11. Test and Quality Requirements

Automated tests must cover:

- Exactly four assets are generated and ordered correctly.
- All four expected files exist, have PNG format, RGB mode, and 1080 × 1350 dimensions.
- Manifest validation accepts four assets and rejects any other asset count.
- AR-04 appears as `news_roundup`, has display order 4, and uses the expected suggested screen time.
- Planner validation enforces copy limits, valid scene modes, and Spanish `POR QUÉ IMPORTA:` prefixes.
- Fallback behavior produces four assets without inventing news claims.
- All renderers preserve safe margins and do not clip text.
- Palette and texture controls are consumed from central configuration.
- Scene prompts prohibit generated text and apply the expected text-safe zone.
- Pose selection is deterministic for a selected `scene_mode`.

Visual QA must additionally verify the acceptance criteria in Section 6.4 against rendered sample editions.

## 12. Measurement Plan

To evaluate whether the creative change improves performance, record for at least six editions before and six editions after deployment:

- LinkedIn impressions.
- Three-second video views.
- Video completion rate, when available.
- Clicks or listens attributable to the post.
- Reactions, comments, reposts, and saves.

Compare comparable publishing days and times. Treat the new visual system as a creative hypothesis; isolate copy, posting cadence, and audience changes where possible.

## 13. Delivery Criteria

The work is complete when:

1. Every edition produces the four defined assets and a valid manifest.
2. The generated visuals use Editorial Earth Tactile consistently.
3. Pulse is visibly stable across editions through the approved pose library.
4. All user-facing text is deterministic, readable, contrast-validated, and free of generated-image typography.
5. The closing radar replaces cover repetition for remaining stories.
6. Automated and visual QA requirements pass.
