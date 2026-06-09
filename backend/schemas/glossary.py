from pydantic import BaseModel


class GlossaryTermResponse(BaseModel):
    name: str
    definition: str
    how_it_works: str
    example: str

    model_config = {"from_attributes": True}
