import os
import redis

from .model import PurchaseRequest, RequestStatus


class PurchaseRepo:
    ADMIN_KEY = "purchase:admin"
    ID_KEY = "purchase:request:id"
    ITEM_KEY = "purchase:request:{}"
    ITEM_ADMIN_KEY = "purchase:request:{}:approver"
    NEW_KEY = "purchase:request:new"
    APPROVED_KEY = "purchase:request:approved"
    DENIED_KEY = "purchase:request:denied"

    def __init__(self):
        host = os.environ.get("REDIS_HOST", "localhost")
        port = os.environ.get("REDIS_PORT", 6379)
        db = os.environ.get("REDIS_DB", 0)
        self._redis = redis.StrictRedis(host=host, port=port, db=db, decode_responses=True)
        # Redis の起動確認
        self._redis.info()

    def get_id(self):
        return self._redis.incr(self.ID_KEY)

    @staticmethod
    def get_id_from_key(key):
        return key.split(":")[-1]

    def create_or_update(self, request, new=True):
        """ リクエストを登録

        :param PurchaseRequest request:
        :param bool new: 新規リクエストの場合は True
        """
        key = self.ITEM_KEY.format(request.id)
        value = request.to_str()
        self._redis.set(key, value)
        if new:
            self._redis.sadd(self.NEW_KEY, key)

    def get_list(self, keys, status):
        """ 特定の key の list に対応するリクエスト一覧を返す
        
        :param list[str] keys: 取得したいリクエストの Redis 登録キーのリスト
        :param RequestStatus status: リクエストの承認状況
        :rtype: list[PurchaseRequest]
        """
        requests = []
        for key in keys:
            value = self._redis.get(key)
            approver = self.get_approver(self.get_id_from_key(key))
            request = PurchaseRequest.from_str(value, status, approver)
            requests.append(request)
        return sorted(requests, key=lambda x: x.id)

    def get_new(self):
        """ 未処理のリクエスト一覧を返す """
        keys = self._redis.smembers(self.NEW_KEY)
        return self.get_list(keys, RequestStatus.new)

    def get_approved(self):
        """ 承認済みのリクエスト一覧を返す """
        keys = self._redis.smembers(self.APPROVED_KEY)
        return self.get_list(keys, RequestStatus.approved)

    def get_denied(self):
        """ 却下済みのリクエスト一覧を返す """
        keys = self._redis.smembers(self.DENIED_KEY)
        return self.get_list(keys, RequestStatus.denied)

    def get_all(self):
        """ 全リクエスト一覧を返す
         
        :rtype: list[PurchaseRequest]
        """
        requests = self.get_new() + self.get_approved() + self.get_denied()
        return sorted(requests, key=lambda x: x.id)

    def get(self, request_id):
        """ 特定のリクエストを取得

         :rtype: (PurchaseRequest|None), bool
         :return: リクエストインスタンス と 未承認ならば True
         """
        key = self.ITEM_KEY.format(request_id)
        value = self._redis.get(key)
        if not value:
            return None, False
        request = PurchaseRequest.from_str(value)
        if self._redis.sismember(self.NEW_KEY, key):
            return request, True
        return request, False

    def update(self, username, prev_text, new_text):
        """ リクエストを更新 """
        keys = self._redis.smembers(self.NEW_KEY)
        for key in keys:
            value = self._redis.get(key)
            request = PurchaseRequest.from_str(value)
            if request.text == prev_text and request.username == username:
                request.text = new_text
                key = self.ITEM_KEY.format(request.id)
                value = request.to_str()
                self._redis.set(key, value)
                return True
        return False

    def delete(self, username, prev_text):
        """ リクエストを削除 """
        keys = self._redis.smembers(self.NEW_KEY)
        for key in keys:
            value = self._redis.get(key)
            request = PurchaseRequest.from_str(value)
            if request.text == prev_text and request.username == username:
                key = self.ITEM_KEY.format(request.id)
                self._redis.delete(key)
                self._redis.srem(self.NEW_KEY, key)
                return True
        return False

    def set_approver(self, request_id, username):
        """ 特定IDのリクエストの承認者を登録 """
        key = self.ITEM_ADMIN_KEY.format(request_id)
        self._redis.set(key, username)

    def get_approver(self, request_id):
        """ 特定IDのリクエストの承認者を登録 """
        key = self.ITEM_ADMIN_KEY.format(request_id)
        return self._redis.get(key)

    def approve(self, request_id, username):
        """ 特定IDのリクエストを承認 """
        key = self.ITEM_KEY.format(request_id)
        self._redis.srem(self.NEW_KEY, key)
        self._redis.sadd(self.APPROVED_KEY, key)
        self.set_approver(request_id, username)

    def deny(self, request_id, username):
        """ 特定IDのリクエストを却下 """
        key = self.ITEM_KEY.format(request_id)
        self._redis.srem(self.NEW_KEY, key)
        self._redis.sadd(self.DENIED_KEY, key)
        self.set_approver(request_id, username)

    @property
    def admin(self):
        """ 承認者ユーザ一覧を取得 """
        return self._redis.smembers(self.ADMIN_KEY)

    def add_admin(self, user):
        """ 承認者ユーザ一覧を追加 """
        self._redis.sadd(self.ADMIN_KEY, user)

    def remove_admin(self, user):
        """ 承認者ユーザ一覧から削除 """
        self._redis.srem(self.ADMIN_KEY, user)
