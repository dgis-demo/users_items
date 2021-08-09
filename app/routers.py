from typing import List

from fastapi import APIRouter, HTTPException
from starlette import status
from starlette.responses import JSONResponse

from .settings import HOST, PORT

from .models import ItemModel, SendingModel, SendingStatus, UserModel
import app.schemas as sc

router = APIRouter()


@router.post(
    '/registration',
    status_code=status.HTTP_201_CREATED,
    response_model=sc.RegisterUserResponse,
    description='''
    Create a user.
    '''
)
async def register_user(request: sc.RegisterUserRequest) -> sc.RegisterUserResponse:
    already_registered = await UserModel.is_registered(request.login)
    if not already_registered:
        await UserModel.create(request.login, request.password)

        registration_succeeded = await UserModel.is_registered(request.login)
        if registration_succeeded:
            return sc.RegisterUserResponse(message='User has been registered')

    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail='User already exists'
    )


@router.post(
    '/login',
    status_code=status.HTTP_201_CREATED,
    response_model=sc.AuthorizeUserResponse,
    description='''
    Authorize a user, return a token. Token expiration time is 24 hours.
    '''
)
async def login_user(request: sc.AuthorizeUserRequest) -> sc.AuthorizeUserResponse:
    token = await UserModel.authorize(request.login, request.password)
    if token:
        return sc.AuthorizeUserResponse(token=token)

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='User has not been found')


@router.post(
    '/items/new',
    status_code=status.HTTP_201_CREATED,
    response_model=sc.CreateItemResponse,
    description='''
    Create an item for an authorized user.
    '''
)
async def create_item(request: sc.CreateItemRequest) -> sc.CreateItemResponse:
    user = await UserModel.get_authorized(request.token)
    if user:
        item_id = await ItemModel.create(name=request.name, user_id=user['id'])
        return sc.CreateItemResponse(id=item_id, name=request.name, message='Item has been created')

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Token has not been authorized',
    )


@router.delete(
    '/items/{id}',
    response_model=sc.DeleteItemResponse,
    description='''
    Remove a particular item.
    '''
)
async def delete_item(request: sc.DeleteItemRequest) -> JSONResponse:
    user = await UserModel.get_authorized(request.token)
    if user:
        item_id = await ItemModel.delete(request.id)
        if item_id:
            return JSONResponse(
                status_code=status.HTTP_200_OK,
                content=sc.DeleteItemResponse(message='Item has been removed').dict(),
            )

        return JSONResponse(
            status_code=status.HTTP_204_NO_CONTENT,
            content=sc.DeleteItemResponse(message='Item has not been found').dict(),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Token has not been authorized',
    )


@router.get(
    '/items',
    status_code=status.HTTP_200_OK,
    response_model=List[sc.ItemSchema],
    description='''
    Return a list of items for an authorized user.
    '''
)
async def list_items(token: str) -> List[sc.ItemSchema]:
    user = await UserModel.get_authorized(token)
    if user:
        items = await ItemModel.list(user_id=user['id'])
        return items

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail='Provided token has not been authorized',
    )


@router.post(
    '/send',
    status_code=status.HTTP_201_CREATED,
    response_model=sc.SendItemResponse,
    description='''
    Send an item, return confirmation URL.
    ''',
)
async def send_item(request: sc.SendItemRequest) -> sc.SendItemResponse:
    sender = await UserModel.get_authorized(request.token)
    if not sender:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token has not been authorized',
        )
    if sender['login'] == request.recipient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Cannot send an item to yourself',
        )

    item = await ItemModel.get(request.id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Item has not been found',
        )

    recipient = await UserModel.get_by_login(request.recipient)
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Recipient has not been found',
        )

    item_token = await SendingModel.initiate_sending(
        from_user_id=sender['id'], to_user_id=recipient['id'], item_id=request.id
    )
    url = f'http://{HOST}:{PORT}/get/{item_token}/{recipient["token"]}'
    return sc.SendItemResponse(confirmation_url=url)


@router.get(
    '/get/{item_token}/{recipient_token}',
    status_code=status.HTTP_200_OK,
    description='''
    Reassign an item to an authorized user using confirmation URL.
    ''',
)
async def get_item(item_token: str, recipient_token: str) -> JSONResponse:
    user = await UserModel.get_authorized(recipient_token)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail='Token has not been authorized',
        )

    sending_status = await SendingModel.complete_sending(item_token=item_token)
    if sending_status == SendingStatus.NO_SENDING:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail='Sending has not been found',
        )

    if sending_status == sending_status.COMPLETED:
        return JSONResponse(content={'message': 'Item has been received'})

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail='Internal server error',
    )
