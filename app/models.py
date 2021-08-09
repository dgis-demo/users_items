import uuid
import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, List, Mapping, Optional

import sqlalchemy
from sqlalchemy import ForeignKey, and_, select
from sqlalchemy.ext.declarative import declarative_base

from .settings import database, metadata, TOKEN_TTL
from .schemas import ItemSchema

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'
    id = sqlalchemy.Column(sqlalchemy.Integer, primary_key=True, index=True)
    login = sqlalchemy.Column(sqlalchemy.String, nullable=False, unique=True)
    password = sqlalchemy.Column(sqlalchemy.String, nullable=False)
    token = sqlalchemy.Column(sqlalchemy.String, unique=True)
    token_expired_at = sqlalchemy.Column(sqlalchemy.DateTime)


users = sqlalchemy.Table(
    'users',
    metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True, index=True),
    sqlalchemy.Column('login', sqlalchemy.String, nullable=False, unique=True),
    sqlalchemy.Column('password', sqlalchemy.String, nullable=False),
    sqlalchemy.Column('token', sqlalchemy.String, unique=True),
    sqlalchemy.Column('token_expired_at', sqlalchemy.DateTime),
)


class UserModel:
    @classmethod
    async def create(cls, login: str, password: str) -> int:
        insert_user_query = users.insert().values(login=login, password=password)
        user_id = await database.execute(insert_user_query)
        return user_id

    @classmethod
    async def is_registered(cls, login: str) -> bool:
        select_user_query = users.select().where(users.c.login == login)
        user = await database.fetch_one(select_user_query)
        return bool(user)

    @classmethod
    async def authorize(cls, login: str, password: str) -> Optional[str]:
        token = hashlib.md5(uuid.uuid4().hex.encode()).hexdigest()
        token_expired_at = datetime.now() + timedelta(seconds=TOKEN_TTL)

        select_user_query = users.select().where(
            and_(users.c.login == login, users.c.password == password)
        )
        user = await database.execute(select_user_query)
        if user:

            set_token_query = (
                users.update()
                .where(and_(users.c.login == login, users.c.password == password))
                .values(token=token, token_expired_at=token_expired_at)
            )
            await database.execute(set_token_query)
            return token

    @classmethod
    async def get_authorized(cls, token: str) -> Optional[Mapping[str, Any]]:
        select_user_query = users.select().where(
            and_(users.c.token == token, datetime.now() < users.c.token_expired_at)
        )
        user = await database.fetch_one(select_user_query)
        return user

    @classmethod
    async def get_by_login(cls, login: str) -> Optional[Mapping[str, Any]]:
        select_user_query = users.select().where(users.c.login == login)
        user = await database.fetch_one(select_user_query)
        return user


class Item(Base):
    __tablename__ = 'items'
    id = sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True, index=True)
    user_id = sqlalchemy.Column('user_id', sqlalchemy.Integer, ForeignKey('users.id'), nullable=False)
    name = sqlalchemy.Column('name', sqlalchemy.String, nullable=False)


items = sqlalchemy.Table(
    'items',
    metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True, index=True),
    sqlalchemy.Column('user_id', sqlalchemy.Integer, ForeignKey('users.id'), nullable=False),
    sqlalchemy.Column('name', sqlalchemy.String, nullable=False),
)


class Sending(Base):
    __tablename__ = 'sendings'
    id = sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True, index=True)
    item_id = sqlalchemy.Column('item_id', sqlalchemy.Integer, ForeignKey('items.id'), nullable=False)
    from_user_id = sqlalchemy.Column('from_user_id', sqlalchemy.Integer, ForeignKey('users.id'), nullable=False)
    to_user_id = sqlalchemy.Column('to_user_id', sqlalchemy.Integer, ForeignKey('users.id'), nullable=False)
    item_token = sqlalchemy.Column('item_token', sqlalchemy.String, nullable=False)


sendings = sqlalchemy.Table(
    'sendings',
    metadata,
    sqlalchemy.Column('id', sqlalchemy.Integer, primary_key=True, index=True),
    sqlalchemy.Column('item_id', sqlalchemy.Integer, ForeignKey('items.id'), nullable=False),
    sqlalchemy.Column('from_user_id', sqlalchemy.Integer, ForeignKey('users.id'),nullable=False),
    sqlalchemy.Column('to_user_id', sqlalchemy.Integer, ForeignKey('users.id'), nullable=False,),
    sqlalchemy.Column('item_token', sqlalchemy.String, nullable=False),
)


class ItemModel:
    @classmethod
    async def create(cls, name: str, user_id: int) -> int:
        insert_item_query = items.insert().values(name=name, user_id=user_id)
        item_id = await database.execute(insert_item_query)
        return item_id

    @classmethod
    async def get(cls, item_id: int) -> Optional[Mapping[str, Any]]:
        select_item_query = items.select().where(items.c.id == item_id)
        item = await database.fetch_one(select_item_query)
        return item

    @classmethod
    @database.transaction()
    async def delete(cls, item_id: int) -> Optional[int]:
        delete_item_query = (
            items.delete().where(items.c.id == item_id).returning(items.c.id)
        )
        deleted_item_id = await database.execute(delete_item_query)

        delete_item_sending_query = (
            sendings.delete().where(items.c.id == item_id).returning(items.c.id)
        )
        await database.execute(delete_item_sending_query)

        return deleted_item_id

    @classmethod
    async def list(cls, user_id: int) -> List[ItemSchema]:
        list_items_query = (
            select([items.c.id, items.c.name])
            .where(items.c.user_id == user_id)
            .order_by('id')
        )
        items_ = await database.fetch_all(list_items_query)
        return list(Item(**item) for item in items_)

    @classmethod
    async def transfer(
        cls, from_user_id: int, to_user_id: int, item_id: int
    ) -> Optional[int]:
        update_items_query = (
            items.update()
            .returning(items.c.id)
            .where(
                and_(
                    items.c.id == item_id,
                    items.c.user_id == from_user_id,
                )
            )
            .values(user_id=to_user_id)
        )
        transferred_item_id = await database.execute(update_items_query)
        return transferred_item_id


class SendingStatus(Enum):
    NO_SENDING = 0
    COMPLETED = 1
    FAILED = 2


class SendingModel:
    @classmethod
    async def initiate_sending(
        cls, from_user_id: int, to_user_id: int, item_id: int
    ) -> str:
        item_token = await cls.get_item_token(
            from_user_id, to_user_id, item_id
        )
        if item_token:
            return item_token

        url = uuid.uuid4().hex
        item_token = await cls.create(from_user_id, to_user_id, item_id, url)

        return item_token

    @classmethod
    async def complete_sending(cls, item_token: str) -> SendingStatus:
        transaction = await database.transaction()

        sending = await cls.get(item_token)
        if not sending:
            await transaction.rollback()
            return SendingStatus.NO_SENDING

        item_id = sending['item_id']

        transferred_item_id = await ItemModel.transfer(
            from_user_id=sending['from_user_id'],
            to_user_id=sending['to_user_id'],
            item_id=sending['item_id'],
        )
        deleted_sending_id = await cls.delete(sending['item_id'])

        if transferred_item_id == item_id and deleted_sending_id:
            await transaction.commit()
            return SendingStatus.COMPLETED

        await transaction.rollback()
        return SendingStatus.FAILED

    @classmethod
    async def get_item_token(
        cls, from_user_id: int, to_user_id: int, item_id: int
    ) -> Optional[str]:
        select_url_query = select([sendings.c.item_token]).where(
            and_(
                sendings.c.from_user_id == from_user_id,
                sendings.c.to_user_id == to_user_id,
                sendings.c.item_id == item_id,
            )
        )
        item_token = await database.fetch_val(select_url_query)
        return item_token

    @classmethod
    async def create(
        cls, from_user_id: int, to_user_id: int, item_id: int, item_token: str
    ) -> str:
        insert_url_query = (
            sendings.insert()
            .values(
                item_id=item_id,
                from_user_id=from_user_id,
                to_user_id=to_user_id,
                item_token=item_token,
            )
            .returning(sendings.c.item_token)
        )
        item_token = await database.execute(insert_url_query)
        return item_token

    @classmethod
    async def get(
        cls, item_token: str
    ) -> Optional[Mapping[str, Any]]:

        select_sending_query = sendings.select().where(
            and_(
                sendings.c.item_token == item_token,
            )
        )

        sending = await database.fetch_one(select_sending_query)
        return sending

    @classmethod
    async def delete(cls, item_id: int) -> int:

        delete_sending_query = (
            sendings.delete()
            .returning(sendings.c.id)
            .where(sendings.c.item_id == item_id)
        )

        deleted_sending_id = await database.execute(delete_sending_query)
        return deleted_sending_id
