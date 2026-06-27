"""Knowledge Base retrieval tool for workflow execution.

This module provides vector similarity search capabilities for retrieving
relevant information from the knowledge base during conversations.

Implements OpenTelemetry tracing for observability in Langfuse.
"""

import json
from typing import Any, Dict, List, Optional

from loguru import logger
from opentelemetry import trace

from api.db import db_client
from api.services.configuration.registry import ServiceProviders
from api.services.gen_ai import AzureOpenAIEmbeddingService, OpenAIEmbeddingService
from api.services.pipecat.tracing_config import ensure_tracing


async def retrieve_from_knowledge_base(
    query: str,
    organization_id: int,
    document_uuids: Optional[List[str]] = None,
    limit: int = 3,
    embeddings_api_key: Optional[str] = None,
    embeddings_model: Optional[str] = None,
    embeddings_base_url: Optional[str] = None,
    embeddings_provider: Optional[str] = None,
    embeddings_endpoint: Optional[str] = None,
    embeddings_api_version: Optional[str] = None,
    tracing_context=None,
) -> Dict[str, Any]:
    """Retrieve relevant information from the knowledge base using vector similarity search.

    Uses OpenAI text-embedding-3-small for embeddings by default. This provides
    high-quality 1536-dimensional embeddings for accurate retrieval.

    This function includes OpenTelemetry tracing for Langfuse observability.

    Args:
        query: The search query to find relevant information
        organization_id: Organization ID for scoping the search
        document_uuids: Optional list of document UUIDs to filter by
        limit: Maximum number of chunks to return (default: 3)
        embeddings_api_key: Optional API key for embedding service
        embeddings_model: Optional model ID for embedding service
        embeddings_base_url: Optional base URL for embedding service
        tracing_context: Optional OpenTelemetry context for tracing

    Returns:
        Dictionary containing:
        - chunks: List of relevant text chunks with metadata
        - query: The original query
        - total_results: Number of results returned
    """
    # Create span for retrieval operation if tracing is enabled
    if ensure_tracing():
        try:
            parent_context = tracing_context

            # Get tracer
            tracer = trace.get_tracer("pipecat")
        except Exception as e:
            logger.debug(f"Failed to setup tracing context: {e}")
            # Fall back to non-traced execution
            return await _perform_retrieval(
                query,
                organization_id,
                document_uuids,
                limit,
                embeddings_api_key,
                embeddings_model,
                embeddings_base_url,
                embeddings_provider,
                embeddings_endpoint,
                embeddings_api_version,
            )

        # Create span with parent context
        if parent_context:
            with tracer.start_as_current_span(
                "knowledge_base_retrieval", context=parent_context
            ) as span:
                try:
                    # Mark trace as public for Langfuse
                    span.set_attribute("langfuse.trace.public", True)

                    # Add operation metadata
                    span.set_attribute(
                        "gen_ai.operation.name", "knowledge_base_retrieval"
                    )
                    span.set_attribute("retrieval.query", query)
                    span.set_attribute("retrieval.limit", limit)
                    span.set_attribute("retrieval.organization_id", organization_id)

                    # Add document filter info
                    if document_uuids:
                        span.set_attribute(
                            "retrieval.document_count", len(document_uuids)
                        )
                        span.set_attribute(
                            "retrieval.document_uuids", json.dumps(document_uuids)
                        )

                    # Perform the actual retrieval
                    result = await _perform_retrieval(
                        query,
                        organization_id,
                        document_uuids,
                        limit,
                        embeddings_api_key,
                        embeddings_model,
                        embeddings_base_url,
                        embeddings_provider,
                        embeddings_endpoint,
                        embeddings_api_version,
                    )

                    # Add result metadata to span
                    span.set_attribute(
                        "retrieval.results_count", result["total_results"]
                    )

                    if result.get("error"):
                        span.set_attribute("retrieval.error", result["error"])
                        span.set_status(
                            trace.Status(trace.StatusCode.ERROR, result["error"])
                        )
                    else:
                        # Add similarity scores
                        if result["chunks"]:
                            similarities = [
                                chunk["similarity"] for chunk in result["chunks"]
                            ]
                            span.set_attribute(
                                "retrieval.avg_similarity",
                                round(sum(similarities) / len(similarities), 4),
                            )
                            span.set_attribute(
                                "retrieval.max_similarity", max(similarities)
                            )
                            span.set_attribute(
                                "retrieval.min_similarity", min(similarities)
                            )

                        # Add retrieved documents info
                        filenames = list(
                            set(chunk["filename"] for chunk in result["chunks"])
                        )
                        span.set_attribute(
                            "retrieval.source_files", json.dumps(filenames)
                        )

                        # Add output as JSON for Langfuse
                        output_data = {
                            "query": query,
                            "chunks_retrieved": len(result["chunks"]),
                            "chunks": [
                                {
                                    "text": chunk["text"][:200] + "..."
                                    if len(chunk["text"]) > 200
                                    else chunk["text"],
                                    "filename": chunk["filename"],
                                    "similarity": chunk["similarity"],
                                }
                                for chunk in result["chunks"]
                            ],
                        }
                        span.set_attribute("output", json.dumps(output_data))

                    return result

                except Exception as e:
                    logger.error(f"Error in traced retrieval: {e}")
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
        else:
            # No parent context - perform retrieval without tracing
            logger.debug(
                "No parent context available for knowledge base retrieval tracing"
            )
            return await _perform_retrieval(
                query,
                organization_id,
                document_uuids,
                limit,
                embeddings_api_key,
                embeddings_model,
                embeddings_base_url,
                embeddings_provider,
                embeddings_endpoint,
                embeddings_api_version,
            )
    else:
        # Tracing is disabled - perform retrieval without tracing
        return await _perform_retrieval(
            query,
            organization_id,
            document_uuids,
            limit,
            embeddings_api_key,
            embeddings_model,
            embeddings_base_url,
            embeddings_provider,
            embeddings_endpoint,
            embeddings_api_version,
        )


async def _perform_retrieval(
    query: str,
    organization_id: int,
    document_uuids: Optional[List[str]],
    limit: int,
    embeddings_api_key: Optional[str] = None,
    embeddings_model: Optional[str] = None,
    embeddings_base_url: Optional[str] = None,
    embeddings_provider: Optional[str] = None,
    embeddings_endpoint: Optional[str] = None,
    embeddings_api_version: Optional[str] = None,
) -> Dict[str, Any]:
    """Internal function to perform the actual retrieval operation.

    Separated from tracing logic for cleaner code organization.
    Handles both chunked (vector search) and full_document (full text) modes.
    """
    try:
        chunks = []

        kg_uuids = []
        chunked_uuids = []
        full_text_docs = []

        # Separating document types by retrieval_mode
        if document_uuids:
            async with db_client.async_session() as session:
                from sqlalchemy import select
                from api.db.models import KnowledgeBaseDocumentModel
                stmt = select(KnowledgeBaseDocumentModel).where(
                    KnowledgeBaseDocumentModel.document_uuid.in_(document_uuids),
                    KnowledgeBaseDocumentModel.organization_id == organization_id,
                    KnowledgeBaseDocumentModel.is_active == True,
                    KnowledgeBaseDocumentModel.processing_status == "completed",
                )
                res = await session.execute(stmt)
                docs = list(res.scalars().all())

            for doc in docs:
                if doc.retrieval_mode == "full_document":
                    full_text_docs.append(doc)
                elif doc.retrieval_mode == "knowledge_graph":
                    kg_uuids.append(doc.document_uuid)
                else:
                    chunked_uuids.append(doc.document_uuid)
        else:
            # Fall back to None so search is performed on all organization chunked docs if no filter specified
            chunked_uuids = None

        # Check for full_document mode documents and return their full text
        for doc in full_text_docs:
            if doc.full_text:
                chunks.append(
                    {
                        "text": doc.full_text,
                        "filename": doc.filename,
                        "similarity": 1.0,
                        "chunk_index": 0,
                    }
                )

        # Build embedding service if we need to search chunked or knowledge graph documents
        if (chunked_uuids is None or len(chunked_uuids) > 0) or (kg_uuids and len(kg_uuids) > 0):
            if not embeddings_api_key:
                raise ValueError(
                    "Embeddings API key not configured. Please set your API key in "
                    "Model Configurations > Embedding."
                )

            if (
                embeddings_provider == ServiceProviders.AZURE.value
                and embeddings_endpoint
            ):
                embedding_service = AzureOpenAIEmbeddingService(
                    db_client=db_client,
                    api_key=embeddings_api_key,
                    endpoint=embeddings_endpoint,
                    model_id=embeddings_model or "text-embedding-3-small",
                    api_version=embeddings_api_version or "2024-02-15-preview",
                )
            else:
                embedding_service = OpenAIEmbeddingService(
                    db_client=db_client,
                    api_key=embeddings_api_key,
                    model_id=embeddings_model or "text-embedding-3-small",
                    base_url=embeddings_base_url,
                )

            # Perform vector similarity search on chunked documents
            if chunked_uuids is None or len(chunked_uuids) > 0:
                results = await embedding_service.search_similar_chunks(
                    query=query,
                    organization_id=organization_id,
                    limit=limit,
                    document_uuids=chunked_uuids,
                )

                for result in results:
                    chunk_info = {
                        "text": result.get("contextualized_text")
                        or result.get("chunk_text"),
                        "filename": result.get("filename"),
                        "similarity": round(result.get("similarity", 0), 4),
                        "chunk_index": result.get("chunk_index"),
                    }
                    chunks.append(chunk_info)

            # Perform Knowledge Graph search on graph documents
            if kg_uuids:
                query_embeddings = await embedding_service.embed_texts([query])
                if query_embeddings:
                    query_embedding = query_embeddings[0]
                    graph_results = await db_client.search_graph_nodes_and_relationships(
                        query_embedding=query_embedding,
                        organization_id=organization_id,
                        document_uuids=kg_uuids,
                        limit=limit,
                    )

                    matched_nodes = graph_results.get("nodes", [])
                    matched_relationships = graph_results.get("relationships", [])

                    if matched_nodes or matched_relationships:
                        matched_nodes_str = ", ".join(
                            [f"{n['name']} ({n['type'] or 'Entity'})" for n in matched_nodes]
                        )

                        rel_facts = []
                        for rel in matched_relationships:
                            prop_str = f" ({json.dumps(rel['properties'])})" if rel['properties'] else ""
                            rel_facts.append(
                                f"- {rel['source']} --[{rel['type']}]--> {rel['target']}{prop_str} (Source: {rel['filename']})"
                            )

                        fact_text = f"Identified entities: {matched_nodes_str}\n\nExtracted relationships:\n"
                        if rel_facts:
                            fact_text += "\n".join(rel_facts)
                        else:
                            fact_text += "No relationships found for these entities."

                        chunks.append(
                            {
                                "text": fact_text,
                                "filename": "Knowledge Graph",
                                "similarity": 1.0,
                                "chunk_index": 0,
                            }
                        )

        logger.info(
            f"Knowledge base retrieval: query='{query}', "
            f"results={len(chunks)}, "
            f"document_filter={document_uuids}"
        )

        return {
            "chunks": chunks,
            "query": query,
            "total_results": len(chunks),
        }

    except Exception as e:
        logger.error(f"Error retrieving from knowledge base: {e}")
        return {
            "error": str(e),
            "chunks": [],
            "query": query,
            "total_results": 0,
        }


def get_knowledge_base_tool(
    document_uuids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Get knowledge base retrieval tool definition for LLM function calling.

    Args:
        document_uuids: Optional list of document UUIDs to include in description

    Returns:
        Tool definition compatible with LLM function calling
    """
    # Build description based on whether specific documents are filtered
    if document_uuids and len(document_uuids) > 0:
        description = (
            "Retrieve relevant information from specific documents in the knowledge base. "
            "Use this tool when you need to look up facts, policies, procedures, or any information "
            "that might be stored in the available documents. The search will only look in the "
            f"documents associated with this conversation step ({len(document_uuids)} document(s) available)."
        )
    else:
        description = (
            "Retrieve relevant information from the knowledge base. "
            "Use this tool when you need to look up facts, policies, procedures, or any information "
            "that might be stored in the knowledge base documents."
        )

    return {
        "type": "function",
        "function": {
            "name": "retrieve_from_knowledge_base",
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "The search query to find relevant information. "
                            "Be specific and use natural language. "
                            "Example: 'What is the refund policy for canceled orders?'"
                        ),
                    }
                },
                "required": ["query"],
            },
        },
    }
