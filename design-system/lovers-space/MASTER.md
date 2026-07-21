# Lovers Space — 轻手账拼贴设计系统

## Experience

- Product: 两个人使用的私密情侣手账，不是 dashboard、统计工具或任务管理器。
- Mood: 温暖、亲密、手作、克制、耐看；内容像故事章节自然展开。
- Density: spacious（2/10）；每屏最多一个主要动作、1–2处装饰。
- Motion: subtle（3/10）；180–300ms，仅使用 opacity/transform，并尊重 reduced-motion。
- Navigation: 垂直阅读，不使用横向旅程；手机底部导航最多5项。

## Tokens

| Role | Value |
|---|---|
| Canvas | `#F7EBDD` |
| Paper | `#FFFDF8` |
| Paper muted | `#F2E3D2` |
| Terracotta primary | `#9A4F3D` |
| Terracotta dark | `#743729` |
| Apricot | `#E7B58F` |
| Dusty rose | `#C98B87` |
| Sage | `#8B9275` |
| Kraft | `#D8C09D` |
| Ink | `#342821` |
| Ink muted | `#6F5B50` |
| Border | `rgba(91, 62, 48, .16)` |
| Destructive | `#A63F3F` |

## Typography

- Display: `Noto Serif SC`, `Songti SC`, `STSong`, serif; 600–700 weight.
- Body/UI: `Noto Sans SC`, `PingFang SC`, `Microsoft YaHei`, sans-serif; 16px minimum, 1.65 line height.
- Handwritten accents: `KaiTi`, `STKaiti`, serif; only dates, signatures and short labels.
- Type scale: 13 / 15 / 16 / 18 / 24 / 32 / 42. Long text max 68ch.

## Components

- Paper sheet: borderless warm surface, soft shadow, optional torn edge; never rotate form controls.
- Collage note: decorative content only, maximum ±1deg rotation.
- Primary action: terracotta filled, one per view. Secondary actions are text or quiet icon buttons.
- Bottom sheet: paper surface, 52% scrim, focus trap, escape route, iPhone safe-area padding.
- Icons: local Lucide outline icons, 20–22px, consistent 1.75–2px stroke; no structural emoji.
- Inputs: visible label, cream-white fill, underline or subtle border, inline status/error.
- Empty state: an inviting sentence plus one contextual action; never a blank admin card.

## Page Rules

- Home: vertical “今日手账”; question is the hero, check-in is two signature notes, fridge uses sticky notes.
- Question: one exchange-letter surface; feedback and AI settings live in overflow/settings sheets.
- Journal: borderless calendar on paper; day opens a writing sheet; preserve drafts and save state.
- Memories: editorial timeline; photos are small paper fragments, not full-screen heroes.
- Wishlist: flowing wish notes; completed wishes become a quiet second chapter.
- Recipes: family cookbook index with bookmark tabs; no accordion dashboard.
- Utility/settings: grouped prose rows and progressive disclosure, not exposed forms.

## Accessibility & Delivery

- Contrast ≥4.5:1 for body text; focus-visible ring always present.
- Touch targets ≥44×44px with ≥8px separation.
- No hover-only actions, horizontal overflow, hidden labels or color-only state.
- Test 375 / 768 / 1024 / 1440px, landscape, large text, keyboard and reduced motion.
