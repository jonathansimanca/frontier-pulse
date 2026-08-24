# Frontier Pulse — Multi-Image Asset Generation Requirements

## 1. Purpose

Improve the existing weekly AI-news podcast generation system. The system already researches relevant, non-repeated AI news, creates a podcast script, converts it to voice audio, and generates one image.

The system **must not generate or edit a video**. Instead, it must generate a small, consistent set of visual assets that the creator can use to manually edit and publish a LinkedIn video.

The goal is to make the podcast instantly understandable while a viewer scrolls on mobile: what the episode is, what it covers, and why it is worth listening to.

## 2. Scope

For every episode, generate:

- One **cover / opening card**.
- One **news insight card** by default.
- An optional second **news insight card** when the episode contains two clearly distinct, high-value stories.

The output therefore contains **two assets by default** and a maximum of **three assets**. All assets are still images for use in a manually edited video.

## 3. Input Data

The visual-asset generator must consume the existing episode output:

- Episode number
- Podcast title or weekly headline
- Estimated audio duration
- Selected news stories
- Key fact or development for each story
- Practical implication for a professional audience
- Script opening hook

## 4. Output Contract

For each episode, create the following files:

```text
episode-[number]-01-cover.png
episode-[number]-02-insight-[topic-a].png
episode-[number]-03-insight-[topic-b].png   # Only when required
episode-[number]-assets.json
```

All PNG files must use the same portrait aspect ratio and dimensions, optimized for LinkedIn mobile video editing (recommended: **1080 × 1350 px**, 4:5).

The JSON manifest must include the exact text, image purpose, story source reference, and suggested display order for each image.

## 5. Asset Requirements

### AR-01 — Cover / Opening Card

**Purpose:** Stop the scroll and make the podcast format and episode value clear before the audio begins.

**Required text layout:**

| Visual area | Exact content requirement |
|---|---|
| Top label | `FRONTIER PULSE` |
| Supporting label | `WEEKLY AI NEWS PODCAST` |
| Main headline | One benefit-led headline, maximum 10 words, summarizing why this week matters. Example: `3 AI developments you should understand this week` |
| Metadata line | `Episode [number] · [duration] min` |
| CTA | `▶ Listen now` |

**Design requirements:**

- The main headline is the largest element and must remain readable on a mobile screen.
- Use an AI/technology visual that supports the episode's dominant theme, but never obscure the text.
- Reserve a calm, high-contrast text area; do not place important text over a busy image region.
- Keep the brand style consistent across episodes: modern, credible, energetic, and professional—not a generic sci-fi poster.
- Include no more than one main illustration or visual focal point.

### AR-02 — News Insight Card A

**Purpose:** Introduce the most important story and immediately explain its relevance.

**Required text layout:**

| Visual area | Exact content requirement |
|---|---|
| Top label | `THIS WEEK IN AI` |
| Story title | A plain-language headline, maximum 9 words. Do not use clickbait. |
| Key fact | One verifiable sentence, maximum 20 words, describing what happened. |
| Why it matters | A short practical implication, maximum 16 words, prefixed with `WHY IT MATTERS:` |
| Footer | `FRONTIER PULSE · EPISODE [number]` |

**Design requirements:**

- Use an image directly related to the story: the company/product, an enterprise-use metaphor, or a relevant technology concept.
- The image must clarify the story, not be a generic glowing AI orb.
- Prioritize title and `WHY IT MATTERS` readability over decoration.

### AR-03 — Optional News Insight Card B

**Purpose:** Present a second story only when it adds clear value and is not merely a variation of Card A.

**Generation rule:** Create this card only if the research stage identifies a second story that is both relevant to the target audience and substantively different from the first story.

**Text and design requirements:** Same as AR-02, but using a clearly distinct visual concept, color accent, and the second selected story.

## 6. Text Generation Rules

- All text must be in the podcast's publication language.
- The story title must explain the event without assuming viewers know the company, product, or acronym.
- The key fact must be grounded in the research data. It must not introduce an unsupported claim.
- `WHY IT MATTERS` must describe a practical effect for people working with AI, data, cloud, software, or business technology.
- Avoid vague phrases such as `AI is changing everything`, `a game changer`, or `the future is here`.
- Do not repeat the full podcast script on an image.
- Do not repeat the same story, claim, or visual concept across cards.

## 7. Typography and Image Rendering Constraint

The exact text must be rendered by a deterministic graphics/compositing step after the background or illustration is generated.

The image-generation model may create the visual background, but it must **not** be relied upon to render the final headline, facts, labels, or CTA. This prevents misspellings, distorted characters, and unreadable typography.

The graphics step must use a fixed, high-contrast typography template and place the exact generated text into the areas specified above.

## 8. Visual Consistency Rules

- Use the same font family, logo/series label position, footer style, margins, and overall hierarchy across all assets.
- Use a consistent dark technology-inspired base style with one accent color per story card.
- Maintain safe margins of at least 80 px on every side.
- Ensure the visual remains understandable if it is shown for only 2–4 seconds during editing.
- Do not include watermarks, fake UI screenshots, excessive logos, or text that cannot be read at mobile size.

## 9. Manifest Example

```json
{
  "episode_number": 4,
  "assets": [
    {
      "file": "episode-4-01-cover.png",
      "type": "cover",
      "display_order": 1,
      "suggested_screen_time_seconds": 3,
      "text": {
        "series": "FRONTIER PULSE",
        "format": "WEEKLY AI NEWS PODCAST",
        "headline": "3 AI developments you should understand this week",
        "metadata": "Episode 4 · 4 min",
        "cta": "▶ Listen now"
      }
    },
    {
      "file": "episode-4-02-insight-enterprise-agents.png",
      "type": "news_insight",
      "display_order": 2,
      "suggested_screen_time_seconds": 5,
      "text": {
        "label": "THIS WEEK IN AI",
        "title": "Enterprise agents become more actionable",
        "key_fact": "[Fact grounded in the selected source]",
        "why_it_matters": "WHY IT MATTERS: [Practical implication]",
        "footer": "FRONTIER PULSE · EPISODE 4"
      },
      "source_reference": "[URL or source identifier]"
    }
  ]
}
```

## 10. Acceptance Criteria

- Each episode produces a cover and one or two news insight cards.
- A viewer can identify the content as a weekly AI-news podcast from the cover alone.
- A viewer can understand each news card's event and practical relevance within 3 seconds.
- Every visible word matches the text provided in the asset manifest exactly.
- The system creates no duplicate or substantially overlapping stories.
- Every factual claim on a news card is traceable to the research output.
- All generated files have the required dimensions, consistent layout, and safe margins.
- The generated assets can be imported directly into a manual video-editing workflow without resizing or redesigning them.

## 11. Success Metrics

Evaluate the new visual format over at least 6–8 episodes:

- Video plays divided by LinkedIn impressions
- Average watch time and early retention
- Comments that mention a story or answer the discussion question
- Reposts, saves, profile views, and followers attributed to the post

The expected result is that more viewers understand the episode immediately, resulting in improved play rate and early retention.
