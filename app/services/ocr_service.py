"""
Mistral OCR Service — Extracts text from PDFs and images using
Mistral's document understanding API. Falls back to basic text
extraction if the API is unavailable.
"""

import base64
import asyncio
import httpx
from typing import Dict, Any, Optional

from ..core.config import settings
from ..core.logging_config import log


# Supported MIME types
SUPPORTED_TYPES = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "text/plain": "txt",
    "text/markdown": "md",
}

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB


class OCRService:
    """Extracts text from uploaded research documents."""

    def __init__(self):
        self.api_key = settings.MISTRAL_API_KEY
        self.base_url = "https://api.mistral.ai/v1"
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0),
                limits=httpx.Limits(
                    max_connections=5,
                    max_keepalive_connections=2,
                ),
            )
        return self._client

    async def extract_text(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> Dict[str, Any]:
        """
        Extract text from a file. Returns:
        {
            "text": "...",
            "pages": int,
            "method": "mistral_ocr" | "plaintext",
            "filename": str,
        }
        """
        if len(file_bytes) > MAX_FILE_SIZE:
            raise ValueError(
                f"File too large: {len(file_bytes)} bytes "
                f"(max {MAX_FILE_SIZE // (1024*1024)} MB)"
            )

        file_ext = SUPPORTED_TYPES.get(content_type)
        if not file_ext:
            raise ValueError(
                f"Unsupported file type: {content_type}. "
                f"Supported: {', '.join(SUPPORTED_TYPES.values())}"
            )

        # Plain text files — no OCR needed
        if content_type in ("text/plain", "text/markdown"):
            text = file_bytes.decode("utf-8", errors="replace")
            return {
                "text": text,
                "pages": 1,
                "method": "plaintext",
                "filename": filename,
            }

        # PDF/Image → Mistral OCR
        if not self.available:
            raise RuntimeError(
                "Mistral API key not configured. "
                "Set MISTRAL_API_KEY in .env to enable OCR."
            )

        return await self._mistral_ocr(
            file_bytes, filename, content_type
        )

    async def _mistral_ocr(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
    ) -> Dict[str, Any]:
        """Real-time PDF processing using local PyMuPDF for text and Groq for Vision."""
        
        # 1. Local Text Extraction (Offloaded to thread)
        log.info(f"Real-time processing: {filename}...")
        
        def _extract():
            try:
                import fitz
                text_content = ""
                page_count = 1
                file_ext = SUPPORTED_TYPES.get(content_type, "pdf")
                doc = fitz.open(stream=file_bytes, filetype=file_ext)
                
                if content_type == "application/pdf":
                    text_parts = []
                    for page in doc:
                        text_parts.append(page.get_text("text"))
                    text_content = "\n\n".join(text_parts)
                    page_count = len(doc)
                else:
                    text_content = doc[0].get_text("text") if len(doc) > 0 else ""
                return text_content, page_count
            except Exception as e:
                log.error(f"Local file extraction failed ({filename}): {e}")
                return "", 1
                
        text, pages = await asyncio.to_thread(_extract)
        log.info(f"Local extraction complete: {len(text)} chars from {pages} pages.")


        # 2. Concurrent Image Analysis via Groq Vision
        image_captions = await self._extract_images_and_caption(file_bytes, content_type)
        if image_captions:
            text += "\n" + image_captions

        return {
            "text": text,
            "pages": pages,
            "method": "hybrid_pymupdf_groq_vision",
            "filename": filename,
            "tokens_used": 0,
        }

    async def _extract_images_and_caption(self, file_bytes: bytes, content_type: str) -> str:
        """Extract images from PDF and use Groq Vision to understand them."""
        if content_type != "application/pdf":
            return ""
            
        if not settings.GROQ_API_KEY:
            log.warning("GROQ_API_KEY not set. Skipping image captioning.")
            return ""
            
        log.info("Extracting images using PyMuPDF for Groq Vision analysis...")
        def _extract_images():
            try:
                import fitz
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                imgs = []
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    image_list = page.get_images(full=True)
                    for img in image_list:
                        xref = img[0]
                        base_image = doc.extract_image(xref)
                        image_bytes = base_image["image"]
                        if len(image_bytes) > 10000:
                            b64 = base64.b64encode(image_bytes).decode("ascii")
                            imgs.append({
                                "page": page_num + 1,
                                "b64": b64,
                                "ext": base_image["ext"],
                                "size": len(image_bytes)
                            })
                return imgs
            except Exception as e:
                log.warning(f"PyMuPDF image extraction failed: {e}")
                return []

        images = await asyncio.to_thread(_extract_images)
        if not images:
            return ""

        # Limit to top 5 largest images to save time/tokens
        images = sorted(images, key=lambda x: x["size"], reverse=True)[:5]
        
        captions = []
        client = await self._get_client()
        log.info(f"Sending {len(images)} images to Groq Vision...")
        
        for i, img in enumerate(images):
            try:
                data_uri = f"data:image/{img['ext']};base64,{img['b64']}"
                payload = {
                    "model": "meta-llama/llama-4-scout-17b-16e-instruct",
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Analyze this image from an academic paper. Describe the visual content in detail. If it's a chart or graph, extract the key trends and numbers. If it's a diagram, explain the architecture or workflow."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {"url": data_uri}
                                }
                            ]
                        }
                    ],
                    "max_tokens": 500,
                    "temperature": 0.1
                }
                headers = {
                    "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                    "Content-Type": "application/json"
                }
                r = await client.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers, timeout=30.0)
                if r.status_code == 200:
                    data = r.json()
                    desc = data["choices"][0]["message"]["content"]
                    captions.append(f"### Image/Figure on Page {img['page']}\n{desc}")
                else:
                    log.warning(f"Groq Vision HTTP {r.status_code}: {r.text[:200]}")
            except Exception as e:
                log.warning(f"Groq vision failed for image {i}: {e}")
        
        if captions:
            return "\n\n## Extracted Figures & Images Analysis (via Groq Vision)\n" + "\n\n".join(captions)
        return ""

    async def close(self):
        """Cleanup HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Global singleton
ocr_service = OCRService()
