# Copyright © 2026 Lapatrada Liawpairoj. All rights reserved.
# Provided for recruitment evaluation only. See LICENSE for terms.

"""Knowledge base search tool.

Purpose:
    Rank synthetic FAQ articles using keyword overlap and ignore query stopwords.

Used with:
    Reads data/faqs.json through common.py; registered in tools/__init__.py.

Notes:
    Scores measure retrieval relevance, not answer correctness. No matches is a successful empty result.
"""

import re

from pydantic import Field, JsonValue

from tools.common import ToolArgs, ToolError, load_data

name = "search_knowledge_base"
description = "Search synthetic English FAQs. Scores measure keyword relevance, not answer correctness."

QUERY_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "my", "i", "to", "of", "and", "or",
    "for", "in", "on", "it", "this", "that", "with", "what", "how", "can",
    "do", "you",
})


class Args(ToolArgs):
    query: str = Field(min_length=1, pattern=r"\S")
    top_k: int = Field(default=3, ge=1, le=5)


def tokens(text: str) -> set[str]:
    """Extract case-insensitive whole-word tokens for keyword matching.

    Works with:
        Called by run() for the query, article titles, content, and keywords.
    """
    return set(re.findall(r"\w+", text.casefold()))


def run(query: str, top_k: int = 3) -> list[dict[str, JsonValue]]:
    """Rank matching FAQs after removing query stopwords; return an empty list for no matches.

    Works with:
        Called through execute_tool_call(); uses common.load_data() and tokens().
    """

    articles = load_data("faqs.json").get("articles")

    if not isinstance(articles, list):
        raise ToolError("data_unavailable")
    terms = tokens(query) - QUERY_STOPWORDS
    hits = []

    for article in articles:
        if not isinstance(article, dict) or any(
            not isinstance(article.get(field), str) for field in ("id", "title", "content")
        ) or not isinstance(article.get("keywords"), list) or any(
            not isinstance(word, str) for word in article["keywords"]
        ):
            raise ToolError("data_unavailable")
        title = tokens(article["title"])
        content = tokens(article["content"])
        keywords = tokens(" ".join(article["keywords"]))
        score = sum(3 * (term in title) + 2 * (term in keywords) + (term in content) for term in terms)

        if score:
            hits.append({
                "id": article["id"], "title": article["title"],
                "content": article["content"], "score": score,
                "source": "Synthetic mock FAQ",
            })

    return sorted(hits, key=lambda hit: (-hit["score"], hit["id"]))[:top_k]
