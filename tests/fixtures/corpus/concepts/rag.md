---
title: Retrieval Augmented Generation
type: concept
tags: [ai, retrieval]
---

# Retrieval Augmented Generation

RAG combines a retriever over a document store with a generator. The retriever
finds relevant passages; the generator conditions its answer on them.

## Hybrid retrieval

Dense vector search and lexical BM25 search are often combined with reciprocal
rank fusion to improve recall.

![retrieval diagram](../../attachments/diagram.png)
