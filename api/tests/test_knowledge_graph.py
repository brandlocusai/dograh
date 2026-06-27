import pytest
import json
from api.db.models import (
    KnowledgeBaseNodeModel,
    KnowledgeBaseRelationshipModel,
    KnowledgeBaseDocumentModel,
    UserModel,
)
from api.services.workflow.tools.knowledge_base import retrieve_from_knowledge_base
from sqlalchemy import select


@pytest.mark.asyncio
async def test_knowledge_graph_db_operations(db_session):
    # 1. Setup user and organization
    user, _ = await db_session.get_or_create_user_by_provider_id("test-graph-user")
    org, _ = await db_session.get_or_create_organization_by_provider_id("test-graph-org", user.id)

    async with db_session.async_session() as session:
        res = await session.execute(select(UserModel).where(UserModel.id == user.id))
        db_user = res.scalar_one()
        db_user.selected_organization_id = org.id
        await session.commit()

    # 2. Create document record with "knowledge_graph" mode
    doc = await db_session.create_document(
        organization_id=org.id,
        created_by=user.id,
        filename="test_graph.txt",
        file_size_bytes=100,
        file_hash="hash123",
        mime_type="text/plain",
        retrieval_mode="knowledge_graph"
    )

    assert doc.id is not None
    assert doc.retrieval_mode == "knowledge_graph"

    # Set document status to completed
    await db_session.update_document_status(doc.id, "completed")

    # 3. Create unique nodes
    node1 = KnowledgeBaseNodeModel(
        document_id=doc.id,
        organization_id=org.id,
        name="Tesla",
        type="Company",
        properties={"industry": "Automotive"},
        embedding=[1.0] + [0.0] * 1535
    )
    node2 = KnowledgeBaseNodeModel(
        document_id=doc.id,
        organization_id=org.id,
        name="Elon Musk",
        type="Person",
        properties={"role": "CEO"},
        embedding=[0.0] + [1.0] * 1535
    )

    await db_session.create_nodes_batch([node1, node2])

    # 4. Create relationship
    rel = KnowledgeBaseRelationshipModel(
        document_id=doc.id,
        organization_id=org.id,
        source="Elon Musk",
        target="Tesla",
        type="CEO_OF",
        properties={"since": "2008"}
    )

    await db_session.create_relationships_batch([rel])

    # 5. Search nodes and fetch relationships
    graph_res = await db_session.search_graph_nodes_and_relationships(
        query_embedding=[0.0] + [1.0] * 1535,
        organization_id=org.id,
        document_uuids=[doc.document_uuid],
        limit=5
    )

    assert len(graph_res["nodes"]) > 0
    # The first node returned should be Elon Musk because its embedding is [0.2]*1536
    assert graph_res["nodes"][0]["name"] == "Elon Musk"

    assert len(graph_res["relationships"]) == 1
    assert graph_res["relationships"][0]["source"] == "Elon Musk"
    assert graph_res["relationships"][0]["target"] == "Tesla"
    assert graph_res["relationships"][0]["type"] == "CEO_OF"

    # 6. Test high-level retrieval tool execution
    from unittest.mock import patch
    with patch("api.services.gen_ai.OpenAIEmbeddingService.embed_texts") as mock_embed:
        mock_embed.return_value = [[0.0] + [1.0] * 1535]
        
        retrieved_data = await retrieve_from_knowledge_base(
            query="Elon Musk",
            organization_id=org.id,
            document_uuids=[doc.document_uuid],
            limit=5,
            embeddings_api_key="mock-key",
            embeddings_model="mock-model",
        )

    assert "error" not in retrieved_data
    assert len(retrieved_data["chunks"]) == 1
    chunk_text = retrieved_data["chunks"][0]["text"]
    assert "Identified entities" in chunk_text
    assert "Elon Musk" in chunk_text
    assert "CEO_OF" in chunk_text

    # 7. Test hard delete and cascade behavior
    delete_success = await db_session.delete_document(
        document_uuid=doc.document_uuid,
        organization_id=org.id,
    )
    assert delete_success is True

    # Verify that the document, nodes, and relationships are deleted from the database
    async with db_session.async_session() as session:
        # Document should be gone
        doc_res = await session.execute(
            select(KnowledgeBaseDocumentModel).where(KnowledgeBaseDocumentModel.id == doc.id)
        )
        assert doc_res.scalar_one_or_none() is None

        # Nodes should be cascade deleted
        nodes_res = await session.execute(
            select(KnowledgeBaseNodeModel).where(KnowledgeBaseNodeModel.document_id == doc.id)
        )
        assert len(list(nodes_res.scalars().all())) == 0

        # Relationships should be cascade deleted
        rels_res = await session.execute(
            select(KnowledgeBaseRelationshipModel).where(KnowledgeBaseRelationshipModel.document_id == doc.id)
        )
        assert len(list(rels_res.scalars().all())) == 0

