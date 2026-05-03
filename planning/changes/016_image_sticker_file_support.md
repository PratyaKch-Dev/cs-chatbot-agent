# 016 — Image, Sticker & File Message Support

**Date:** 2026-05-03
**Type:** feature
**Phase:** 2

---

## Summary
Added vision-based image understanding for LINE and Gradio: user-sent images are described by Gemini and passed to the pipeline as context. Stickers receive a greeting reply; file attachments receive an unsupported message.

## Added
- `llm/vision.py` — `describe_image(bytes, media_type)` using Gemini vision; returns Thai description of image content including key problems/amounts visible on screen
- `llm/templates.py` — `FILE_NOT_SUPPORTED` constant + template (Thai/English), `IMAGE_CAPTION_PREFIX` constant

## Changed
- `interface/fastapi_app.py` — handles `StickerMessageContent` (greeting reply), `FileMessageContent` (unsupported reply), `ImageMessageContent` (download via LINE blob API → vision → buffer); added `_push_text()` and `_handle_image()` helpers
- `interface/gradio_app.py` — added `gr.Image` upload component; when image + text sent together, combined into one message (`[ภาพ] <description>\nคำถาม: <text>`) so pipeline sees image as context for the question

## Removed
- nothing

## Notes
- Vision prompt instructs Gemini to extract key status/amounts (e.g. ค่าธรรมเนียมค้างชำระ ฿149.99) so the FAQ/troubleshooting pipeline can answer correctly
- Image-only sends push description as standalone message; image+text combines into one to preserve intent
