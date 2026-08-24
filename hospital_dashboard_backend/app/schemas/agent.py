from pydantic import BaseModel


class AgentQuery(BaseModel):
    query: str


class AgentResponse(BaseModel):
    response: str
    details: str
