from fastapi import APIRouter, Depends

from ..database import notes_collection
from ..dependencies import get_current_user
from ..models import GraphOut, GraphNode, GraphEdge

router = APIRouter(prefix="/api/graph", tags=["graph"])


@router.get("", response_model=GraphOut)
async def get_graph(current_user: dict = Depends(get_current_user)):
    owner_id = str(current_user["_id"])
    docs = [
        doc
        async for doc in notes_collection.find(
            {"owner_id": owner_id}, {"title": 1, "links": 1, "folder_path": 1}
        )
    ]
    title_to_id = {doc["title"]: str(doc["_id"]) for doc in docs}

    nodes = [
        GraphNode(id=str(doc["_id"]), label=doc["title"], folder_path=doc.get("folder_path", ""))
        for doc in docs
    ]

    edges = []
    for doc in docs:
        source_id = str(doc["_id"])
        for linked_title in doc.get("links", []):
            target_id = title_to_id.get(linked_title)
            if target_id:
                edges.append(GraphEdge(source=source_id, target=target_id))

    return GraphOut(nodes=nodes, edges=edges)
