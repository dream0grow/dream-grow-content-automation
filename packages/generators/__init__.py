from .base import GeneratorContext, GeneratedContent
from . import thread, newsletter, reels, youtube, lead_magnet

REGISTRY = {
    "thread": thread.generate,
    "newsletter": newsletter.generate,
    "reels": reels.generate,
    "youtube": youtube.generate,
    "magnet": lead_magnet.generate,
}

__all__ = ["GeneratorContext", "GeneratedContent", "REGISTRY"]
