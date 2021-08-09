from pydantic import BaseModel


class RegisterUserRequest(BaseModel):
    login: str
    password: str

    class Config:
        orm_mode = True


class RegisterUserResponse(BaseModel):
    message: str

    class Config:
        orm_mode = True


class AuthorizeUserRequest(BaseModel):
    login: str
    password: str

    class Config:
        orm_mode = True


class AuthorizeUserResponse(BaseModel):
    token: str

    class Config:
        orm_mode = True


class CreateItemRequest(BaseModel):
    name: str
    token: str

    class Config:
        orm_mode = True


class CreateItemResponse(BaseModel):
    id: int
    name: str
    message: str

    class Config:
        orm_mode = True


class DeleteItemRequest(BaseModel):
    id: int
    token: str

    class Config:
        orm_mode = True


class DeleteItemResponse(BaseModel):
    message: str

    class Config:
        orm_mode = True


class ItemSchema(BaseModel):
    id: int
    name: str

    class Config:
        orm_mode = True


class SendItemRequest(BaseModel):
    id: int
    token: str
    recipient: str

    class Config:
        orm_mode = True


class SendItemResponse(BaseModel):
    confirmation_url: str

    class Config:
        orm_mode = True
