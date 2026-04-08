"""Fetch book cover images, upload to R2, and store the URL in cover_url.

For each book without a cover_url, navigates to its URL, extracts the cover
image src from the page, downloads it, uploads to Cloudflare R2, and saves
the public URL in book.cover_url.

Usage:
    python -m app.scripts.fetch_covers [--dry-run] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import logging
import mimetypes
import re
from typing import Any

import httpx
import lxml.html as lxml_html
from botocore.config import Config
from sqlmodel import select

from app.config import settings
from app.database import SessionLocal
from app.models.book import Book

logger = logging.getLogger(__name__)


def _build_r2_client() -> Any:
    import boto3

    endpoint_url = f"https://{settings.cloudflare_r2_account_id}.r2.cloudflarestorage.com"
    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        region_name="auto",
        aws_access_key_id=settings.cloudflare_r2_access_key_id,
        aws_secret_access_key=settings.cloudflare_r2_secret_access_key,
        config=Config(signature_version="s3v4"),
    )


async def _fetch_cover_url(book_url: str) -> str | None:
    """Fetch the book page and return the cover image src URL."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(book_url)
            resp.raise_for_status()
        doc = lxml_html.fromstring(resp.content)
        # Cover is in an <img> inside a div with class "aspect-book"
        imgs = doc.xpath('//div[contains(@class,"aspect-book")]//img/@src')
        if imgs:
            return str(imgs[0])
        return None
    except Exception as exc:
        logger.warning("Failed to fetch page %s: %s", book_url, exc)
        return None


async def _download_image(url: str) -> tuple[bytes, str] | None:
    """Download image bytes and return (data, content_type)."""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        return resp.content, content_type
    except Exception as exc:
        logger.warning("Failed to download image %s: %s", url, exc)
        return None


BOOK_URL_RE = re.compile(r"/books/(?P<method>[^/]+)/(?P<book>[^/?#]+)")


def _slugs_from_url(url: str) -> tuple[str, str]:
    """Return (method_slug, book_slug) extracted from a book URL."""
    m = BOOK_URL_RE.search(url)
    if m:
        return m.group("method"), m.group("book")
    return "unknown", "unknown"


def _extension_for(content_type: str, url: str) -> str:
    ext = mimetypes.guess_extension(content_type)
    if ext in (".jpe", None):
        ext = ".jpg"
    if not ext:
        m = re.search(r"\.(jpe?g|png|webp|gif)(?:[?#]|$)", url, re.IGNORECASE)
        ext = f".{m.group(1).lower()}" if m else ".jpg"
    return ext


def _upload_to_r2(client: Any, key: str, data: bytes, content_type: str) -> str:
    client.put_object(
        Bucket=settings.cloudflare_r2_bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
    )
    return f"{settings.cloudflare_r2_public_url.rstrip('/')}/{key}"


async def run(dry_run: bool = False, limit: int | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")

    r2 = None if dry_run else _build_r2_client()

    async with SessionLocal() as session:
        result = await session.execute(
            select(Book).where(Book.cover_url.is_(None))  # type: ignore[union-attr]
        )
        books: list[Book] = list(result.scalars().all())

    logger.info("Found %d books without cover_url", len(books))
    if limit:
        books = books[:limit]
        logger.info("Limited to %d books", len(books))

    for i, book in enumerate(books, 1):
        logger.info("[%d/%d] %s  (%s)", i, len(books), book.slug, book.url)

        cover_src = await _fetch_cover_url(book.url)
        if not cover_src:
            logger.warning("  No cover image found on page")
            continue
        logger.info("  Cover src: %s", cover_src)

        if dry_run:
            logger.info("  [dry-run] Would upload and set cover_url")
            continue

        result = await _download_image(cover_src)
        if not result:
            logger.warning("  Failed to download cover image")
            continue
        data, content_type = result

        ext = _extension_for(content_type, cover_src)
        image_hash = hashlib.sha256(data).hexdigest()[:8]
        method_slug, book_slug = _slugs_from_url(book.url)
        key = f"covers/{method_slug}/{book_slug}-{image_hash}{ext}"

        try:
            public_url = _upload_to_r2(r2, key, data, content_type)
        except Exception as exc:
            logger.error("  R2 upload failed: %s", exc)
            continue

        async with SessionLocal() as session:
            result2 = await session.execute(select(Book).where(Book.id == book.id))
            b = result2.scalars().first()
            if b:
                b.cover_url = public_url  # type: ignore[assignment]
                await session.commit()

        logger.info("  Saved cover_url: %s", public_url)

    logger.info("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch and store book cover images in R2")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing to DB or R2")
    parser.add_argument("--limit", type=int, default=None, help="Process only N books")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run, limit=args.limit))


if __name__ == "__main__":
    main()
