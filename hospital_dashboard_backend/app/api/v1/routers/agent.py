from fastapi import APIRouter

from app.schemas.agent import AgentQuery, AgentResponse

router = APIRouter()


@router.post("/query", response_model=AgentResponse)
def query_agent(request: AgentQuery):
    return {
        "response": f"AI agent received query: {request.query}",
        "details": "This is a placeholder response; integrate your AI model here."
    }
