import json
import os
import tempfile

from loguru import logger

from api.db import db_client
from api.db.models import (
    KnowledgeBaseChunkModel,
    KnowledgeBaseNodeModel,
    KnowledgeBaseRelationshipModel,
)
from api.services.configuration.registry import ServiceProviders
from api.services.gen_ai import AzureOpenAIEmbeddingService, OpenAIEmbeddingService
from api.services.mps_service_key_client import mps_service_key_client
from api.services.storage import storage_fs

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024


def get_langchain_chat_model(user_config):
    """Initialize a LangChain chat model based on the user's configuration."""
    if not user_config.llm:
        raise ValueError(
            "LLM configuration not found. Please configure your LLM settings "
            "under Model Configurations > LLM to process Knowledge Graph documents."
        )

    provider = user_config.llm.provider
    api_key = user_config.llm.api_key
    model = user_config.llm.model
    base_url = getattr(user_config.llm, "base_url", None)
    endpoint = getattr(user_config.llm, "endpoint", None)
    api_version = getattr(user_config.llm, "api_version", None)
    max_tokens = getattr(user_config.llm, "max_tokens", None) or 4096

    if not api_key:
        raise ValueError(
            f"LLM API key not configured for provider '{provider}'. "
            "Please configure your LLM settings under Model Configurations > LLM."
        )

    if provider == "azure":
        from langchain_openai import AzureChatOpenAI
        return AzureChatOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version or "2024-02-15-preview",
            azure_deployment=model,
            temperature=0,
            max_tokens=max_tokens,
        )
    else:
        # Default to ChatOpenAI (handles OpenAI, Groq, OpenRouter, Speaches etc.)
        from langchain_openai import ChatOpenAI
        kwargs = {}
        if base_url:
            kwargs["base_url"] = base_url
        return ChatOpenAI(
            api_key=api_key,
            model=model or "gpt-4o-mini",
            temperature=0,
            max_tokens=max_tokens,
            **kwargs,
        )



async def process_knowledge_base_document(
    ctx,
    document_id: int,
    s3_key: str,
    organization_id: int,
    created_by_provider_id: str,
    max_tokens: int = 128,
    retrieval_mode: str = "chunked",
):
    """Process a knowledge base document via MPS: download, call MPS, embed, store.

    Args:
        ctx: ARQ context
        document_id: Database ID of the document
        s3_key: S3 key where the file is stored
        organization_id: Organization ID
        created_by_provider_id: Uploading user's provider ID (for OSS-mode auth to MPS)
        max_tokens: Maximum number of tokens per chunk (default: 128)
        retrieval_mode: "chunked" for vector search or "full_document" for full text
    """
    logger.info(
        f"Processing knowledge base document: document_id={document_id}, "
        f"s3_key={s3_key}, org={organization_id}, mode={retrieval_mode}"
    )

    temp_file_path = None

    try:
        await db_client.update_document_status(document_id, "processing")

        filename = s3_key.split("/")[-1]
        file_extension = os.path.splitext(filename)[1] or ".bin"

        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        temp_file_path = temp_file.name
        temp_file.close()

        logger.info(f"Downloading file from S3: {s3_key}")
        download_success = await storage_fs.adownload_file(s3_key, temp_file_path)
        if not download_success:
            raise Exception(f"Failed to download file from S3: {s3_key}")
        if not os.path.exists(temp_file_path):
            raise FileNotFoundError(f"Downloaded file not found: {temp_file_path}")

        file_size = os.path.getsize(temp_file_path)
        logger.info(f"Downloaded file size: {file_size} bytes")

        if file_size > MAX_FILE_SIZE_BYTES:
            error_message = (
                f"File size ({file_size / (1024 * 1024):.1f}MB) exceeds the "
                f"maximum allowed size of {MAX_FILE_SIZE_BYTES // (1024 * 1024)}MB."
            )
            logger.warning(f"Document {document_id}: {error_message}")
            await db_client.update_document_status(
                document_id, "failed", error_message=error_message
            )
            return

        file_hash = db_client.compute_file_hash(temp_file_path)
        mime_type = db_client.get_mime_type(temp_file_path)

        document = await db_client.get_document_by_id(document_id)
        if not document:
            raise Exception(f"Document {document_id} not found")

        # Reject duplicates (same hash already ingested for this org).
        existing_doc = await db_client.get_document_by_hash(file_hash, organization_id)
        if existing_doc and existing_doc.id != document_id:
            error_message = (
                f"This file is a duplicate of '{existing_doc.filename}'. "
                f"Please delete the duplicate files and consolidate them into a "
                f"single unique file before uploading."
            )
            logger.warning(
                f"Duplicate document detected: {document_id} is duplicate of "
                f"{existing_doc.id} ({existing_doc.filename})"
            )
            await db_client.update_document_metadata(
                document_id,
                file_size_bytes=file_size,
                file_hash=file_hash,
                mime_type=mime_type,
            )
            await db_client.update_document_status(
                document_id,
                "failed",
                error_message=error_message,
                docling_metadata={
                    "duplicate_of": existing_doc.document_uuid,
                    "duplicate_filename": existing_doc.filename,
                },
            )
            return

        await db_client.update_document_metadata(
            document_id,
            file_size_bytes=file_size,
            file_hash=file_hash,
            mime_type=mime_type,
        )

        # Map retrieval_mode for MPS. MPS does not have a native knowledge_graph mode,
        # so we ask it to parse as chunked, and we extract entities/relations locally.
        mps_mode = "chunked" if retrieval_mode == "knowledge_graph" else retrieval_mode
        logger.info(f"Delegating document processing to MPS (mode={mps_mode})")
        mps_response = await mps_service_key_client.process_document(
            file_path=temp_file_path,
            filename=filename,
            content_type=mime_type or "application/octet-stream",
            retrieval_mode=mps_mode,
            max_tokens=max_tokens,
            organization_id=organization_id,
            created_by=created_by_provider_id,
        )

        docling_metadata = mps_response.get("docling_metadata", {})

        if retrieval_mode == "full_document":
            full_text = mps_response.get("full_text") or ""
            await db_client.update_document_full_text(document_id, full_text)
            await db_client.update_document_status(
                document_id,
                "completed",
                total_chunks=0,
                docling_metadata=docling_metadata,
            )
            logger.info(
                f"Successfully processed full_document {document_id}. "
                f"Text length: {len(full_text)} chars"
            )
            return

        elif retrieval_mode == "knowledge_graph":
            # Knowledge Graph mode: fetch LLM configurations and embedding configuration.
            embeddings_provider = None
            embeddings_api_key = None
            embeddings_model = None
            embeddings_base_url = None
            embeddings_endpoint = None
            embeddings_api_version = None
            user_config = None

            if document.created_by:
                user_config = await db_client.get_user_configurations(document.created_by)
                if user_config.embeddings:
                    embeddings_provider = getattr(user_config.embeddings, "provider", None)
                    embeddings_api_key = user_config.embeddings.api_key
                    embeddings_model = user_config.embeddings.model
                    embeddings_base_url = getattr(user_config.embeddings, "base_url", None)
                    embeddings_endpoint = getattr(user_config.embeddings, "endpoint", None)
                    embeddings_api_version = getattr(
                        user_config.embeddings, "api_version", None
                    )

            if not embeddings_api_key:
                error_message = (
                    "API key not configured. Please set your API key in "
                    "Model Configurations > Embedding to process documents."
                )
                logger.warning(f"Document {document_id}: {error_message}")
                await db_client.update_document_status(
                    document_id, "failed", error_message=error_message
                )
                return

            if embeddings_provider == ServiceProviders.AZURE.value and embeddings_endpoint:
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

            # Initialize LangChain LLM and Transformer
            try:
                llm = get_langchain_chat_model(user_config)
            except Exception as e:
                error_message = f"Failed to initialize LLM for Knowledge Graph: {str(e)}"
                logger.error(f"Document {document_id}: {error_message}")
                await db_client.update_document_status(
                    document_id, "failed", error_message=error_message
                )
                return

            from langchain_experimental.graph_transformers import LLMGraphTransformer
            transformer = LLMGraphTransformer(llm=llm)

            mps_chunks = mps_response.get("chunks", [])
            if not mps_chunks:
                logger.warning(f"Document {document_id}: MPS returned zero chunks")

            # Convert chunks to langchain documents
            from langchain_core.documents import Document as LangchainDocument
            docs = [
                LangchainDocument(
                    page_content=chunk.get("contextualized_text") or chunk["chunk_text"]
                )
                for chunk in mps_chunks
            ]

            logger.info(f"Extracting Knowledge Graph from {len(docs)} chunks...")
            try:
                graph_documents = await transformer.aconvert_to_graph_documents(docs)
            except Exception as e:
                error_message = f"Knowledge Graph extraction failed: {str(e)}"
                logger.error(f"Document {document_id}: {error_message}")
                await db_client.update_document_status(
                    document_id, "failed", error_message=error_message
                )
                return

            # Extract unique nodes and relationships
            seen_nodes = {}
            relationships_to_insert = []

            for graph_doc in graph_documents:
                # Merge and deduplicate nodes
                for node in graph_doc.nodes:
                    node_name = str(node.id).strip()
                    node_key = node_name.lower()

                    if node_key in seen_nodes:
                        if node.properties:
                            seen_nodes[node_key]["properties"].update(node.properties)
                        if node.type and not seen_nodes[node_key]["type"]:
                            seen_nodes[node_key]["type"] = str(node.type)
                    else:
                        seen_nodes[node_key] = {
                            "name": node_name,
                            "type": str(node.type) if node.type else None,
                            "properties": dict(node.properties) if node.properties else {},
                        }

                # Cache relationships
                for rel in graph_doc.relationships:
                    relationships_to_insert.append(
                        {
                            "source": str(rel.source.id).strip(),
                            "target": str(rel.target.id).strip(),
                            "type": str(rel.type).strip(),
                            "properties": rel.properties or {},
                        }
                    )

            node_records = []
            node_texts_to_embed = []

            # Format node text representation for semantic embeddings
            for key, node_data in seen_nodes.items():
                rep = f"Name: {node_data['name']}"
                if node_data["type"]:
                    rep += f" | Type: {node_data['type']}"
                if node_data["properties"]:
                    rep += f" | Properties: {json.dumps(node_data['properties'])}"
                node_texts_to_embed.append((node_data, rep))

            if node_texts_to_embed:
                logger.info(f"Generating embeddings for {len(node_texts_to_embed)} unique nodes...")
                embeddings = await embedding_service.embed_texts([item[1] for item in node_texts_to_embed])
                for (node_data, rep), embedding in zip(node_texts_to_embed, embeddings):
                    node_records.append(
                        KnowledgeBaseNodeModel(
                            document_id=document_id,
                            organization_id=organization_id,
                            name=node_data["name"],
                            type=node_data["type"],
                            properties=node_data["properties"],
                            embedding=embedding,
                        )
                    )

                logger.info("Storing nodes in database")
                await db_client.create_nodes_batch(node_records)

            relationship_records = []
            for rel_data in relationships_to_insert:
                relationship_records.append(
                    KnowledgeBaseRelationshipModel(
                        document_id=document_id,
                        organization_id=organization_id,
                        source=rel_data["source"],
                        target=rel_data["target"],
                        type=rel_data["type"],
                        properties=rel_data["properties"],
                    )
                )

            if relationship_records:
                logger.info("Storing relationships in database")
                await db_client.create_relationships_batch(relationship_records)

            await db_client.update_document_status(
                document_id,
                "completed",
                total_chunks=len(node_records),
                docling_metadata=docling_metadata,
            )

            logger.info(
                f"Successfully processed Knowledge Graph for document {document_id}. "
                f"Nodes: {len(node_records)}, Relationships: {len(relationship_records)}"
            )
            return

        # Chunked mode: fetch user embedding config, embed, and persist chunks.
        embeddings_provider = None
        embeddings_api_key = None
        embeddings_model = None
        embeddings_base_url = None
        embeddings_endpoint = None
        embeddings_api_version = None
        if document.created_by:
            user_config = await db_client.get_user_configurations(document.created_by)
            if user_config.embeddings:
                embeddings_provider = getattr(user_config.embeddings, "provider", None)
                embeddings_api_key = user_config.embeddings.api_key
                embeddings_model = user_config.embeddings.model
                embeddings_base_url = getattr(user_config.embeddings, "base_url", None)
                embeddings_endpoint = getattr(user_config.embeddings, "endpoint", None)
                embeddings_api_version = getattr(
                    user_config.embeddings, "api_version", None
                )
                logger.info(
                    f"Using user embeddings config: provider={embeddings_provider}, "
                    f"model={embeddings_model}"
                )

        if not embeddings_api_key:
            error_message = (
                "API key not configured. Please set your API key in "
                "Model Configurations > Embedding to process documents."
            )
            logger.warning(f"Document {document_id}: {error_message}")
            await db_client.update_document_status(
                document_id, "failed", error_message=error_message
            )
            return

        if embeddings_provider == ServiceProviders.AZURE.value and embeddings_endpoint:
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

        mps_chunks = mps_response.get("chunks", [])
        if not mps_chunks:
            logger.warning(f"Document {document_id}: MPS returned zero chunks")

        chunk_records = []
        chunk_texts = []
        for chunk in mps_chunks:
            contextualized = chunk.get("contextualized_text") or chunk["chunk_text"]
            chunk_records.append(
                KnowledgeBaseChunkModel(
                    document_id=document_id,
                    organization_id=organization_id,
                    chunk_text=chunk["chunk_text"],
                    contextualized_text=contextualized,
                    chunk_index=chunk["chunk_index"],
                    chunk_metadata=chunk.get("chunk_metadata") or {},
                    embedding_model=embedding_service.get_model_id(),
                    embedding_dimension=embedding_service.get_embedding_dimension(),
                    token_count=chunk.get("token_count", 0),
                )
            )
            chunk_texts.append(contextualized)

        logger.info(
            f"Generating embeddings for {len(chunk_texts)} chunks "
            f"using {embedding_service.get_model_id()}"
        )
        embeddings = await embedding_service.embed_texts(chunk_texts)
        for chunk_record, embedding in zip(chunk_records, embeddings):
            chunk_record.embedding = embedding

        logger.info("Storing chunks in database")
        await db_client.create_chunks_batch(chunk_records)

        await db_client.update_document_status(
            document_id,
            "completed",
            total_chunks=len(chunk_records),
            docling_metadata=docling_metadata,
        )

        logger.info(
            f"Successfully processed knowledge base document {document_id}. "
            f"Total chunks: {len(chunk_records)}"
        )

    except Exception as e:
        logger.error(
            f"Error processing knowledge base document {document_id}: {e}",
            exc_info=True,
        )
        await db_client.update_document_status(
            document_id, "failed", error_message=str(e)
        )
        raise

    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logger.debug(f"Cleaned up temp file: {temp_file_path}")
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {temp_file_path}: {e}")
